#!/usr/bin/env python3
"""Validate authoring configs and emit canonical, self-hashed runtime artifacts."""
import argparse,hashlib,json,math,pathlib,re,sys
from tooling.common.identity import robot_id
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"protocol"))
import jcs  # noqa: E402  single RFC 8785 canonicalizer, shared with the ev3dev runtime

# Every keyword the in-tree validator understands. Anything else is a schema
# authoring mistake and must fail closed rather than silently pass.
KNOWN_KEYWORDS={"$schema","$id","$ref","$defs","title","description","type","const","enum",
                "required","properties","additionalProperties","items","minLength","maxLength",
                "pattern","minimum","maximum","minItems","maxItems"}

VARIANTS = (("ev3", "ev3"), ("ev3-network-only", "ev3"),
            ("quest", "quest"), ("quest-network-only", "quest"))


def overlay(base, changes, path="$", reject_redundant=True):
    """Recursive object overlay; arrays replace whole arrays and null remains null."""
    import copy
    if not isinstance(base, dict) or not isinstance(changes, dict):
        raise ValueError(path + ": base and profile must be objects")
    result = copy.deepcopy(base)
    for key, value in changes.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            result[key] = overlay(base[key], value, path + "." + key, reject_redundant)
        else:
            if reject_redundant and key in base and base[key] == value:
                raise ValueError(path + "." + key + ": redundant profile setting")
            result[key] = copy.deepcopy(value)
    return result


def profile_source(folder, profile, base_file="project.json"):
    base = load(ROOT / folder / base_file)
    profiles = {name: (load(ROOT / folder / (name + ".json"))
                       if (ROOT / folder / (name + ".json")).exists() else {})
                for name in ("release", "diagnostic")}
    if any(not isinstance(value, dict) for value in profiles.values()):
        raise ValueError(folder + ": profiles must be objects")
    if folder in ("config/ev3", "config/quest"):
        allowed = {"runtime"}
        for value in profiles.values():
            if set(value) - allowed:
                raise ValueError(folder + ": profile may override only consumed development runtime settings")
    def reject_common(left, right, path):
        for key in left.keys() & right.keys():
            if isinstance(left[key], dict) and isinstance(right[key], dict):
                reject_common(left[key], right[key], path + "." + key)
            elif left[key] == right[key]:
                raise ValueError(path + "." + key + ": repeated in both profiles; move to project")
    reject_common(profiles["release"], profiles["diagnostic"], folder)
    return overlay(base, profiles[profile])


def project_source(component, profile):
    value = profile_source("config/" + component, profile)
    expected = {"ev3": {"runtime"},
                "quest": {"build", "runtime"}}[component]
    if set(value) != expected:
        raise ValueError(component + ": unexpected/missing project sections")
    if not all(isinstance(item, dict) for item in value.values()):
        raise ValueError(component + ": project sections must be objects")
    validate_project_settings(component, value)
    return value


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + ": unknown or missing settings")


def validate_project_settings(component, value):
    """Reject settings for which the host tool has no consumer."""
    if component == "ev3":
        return  # EV3 build environment belongs to ev3/docker/Dockerfile.
    else:
        build = value["build"]
        exact_keys(build, ("environment", "packaging"), "quest.build")
        env = build["environment"]
        exact_keys(env, ("unity", "android", "dotnet"), "quest.build.environment")
        for name, keys in (("unity", ("override_environment_variable", "search_paths")),
                           ("android", ("override_environment_variable", "adb_relative_paths", "adb_search_paths", "apksigner_override_environment_variable")),
                           ("dotnet", ("override_environment_variable", "user_install_relative_path"))):
            exact_keys(env[name], keys, "quest.build.environment." + name)
            for key, item in env[name].items():
                if key.endswith("paths"):
                    if not isinstance(item, list) or any(not isinstance(path, str) or not path for path in item):
                        raise ValueError(name + "." + key + " must be a list of paths")
                elif not isinstance(item, str) or not item:
                    raise ValueError(name + "." + key + " must be a nonempty string")
        exact_keys(build["packaging"], ("meta_app_id", "signing_key_alias"), "quest.build.packaging")
        for key, pattern in (("meta_app_id", r"[0-9]+"), ("signing_key_alias", r"[A-Za-z0-9_.-]+")):
            if not isinstance(build["packaging"][key], str) or not re.fullmatch(pattern, build["packaging"][key]):
                raise ValueError("Invalid Quest " + key)


def schema_path(name):
    return ROOT / {"ev3": "schemas/ev3/runtime.schema.json",
                   "quest": "schemas/quest/runtime.schema.json",
                   "commissioning_bundle": "schemas/ev3/commissioning.schema.json"}[name]


def generated_path(name):
    profile = "diagnostic" if name.endswith("-network-only") else "release"
    component = name.removesuffix("-network-only")
    if component in ("ev3", "quest"):
        return ROOT / "build/config" / component / (profile + ".json")
    raise ValueError("unknown config artifact: " + name)


def inject(obj, values, label):
    """Shared or calculated values cannot be shadowed by a component profile."""
    collision = obj.keys() & values.keys()
    if collision:
        raise ValueError(label + ": shared/derived fields overridden: " + str(sorted(collision)))
    obj.update(values)


def bootstrap_descriptor():
    """Session-local zero-authority identity; no measured robot data is fabricated."""
    schema = load(ROOT / "schemas/ev3/network-only-session.schema.json")
    return {key: spec["const"] for key, spec in schema["properties"].items()}



def bootstrap_hash():
    return hashlib.sha256(canonical(bootstrap_descriptor())).hexdigest()


def source_objects():
    pair = load(ROOT / "config/shared/pair.json")
    exact_keys(pair, ("network",), "shared.pair")
    wire = load(ROOT / "schemas/shared/protocol/wire-schema.json")
    results = {}
    for profile, suffix in (("release", ""), ("diagnostic", "-network-only")):
        ev3 = project_source("ev3", profile)["runtime"]
        # Current Diagnostic supports network-only qualification. Future scoped
        # hardware modes need a separate explicit contract, not profile overrides.
        scope_keys = ("qualification_only", "actuator_scope_mask", "safety_observation_mask")
        scope = ({key: bootstrap_descriptor()[key] for key in scope_keys}
                 if profile == "diagnostic" else
                 dict(qualification_only=False, actuator_scope_mask=15, safety_observation_mask=15))
        inject(ev3, scope, "ev3.runtime")
        for component in ("ev3", "quest"):
            obj = ev3 if component == "ev3" else project_source(component, profile)["runtime"]
            inject(obj, {"robot_id": robot_id(ROOT), "build_profile": profile.title()}, component)
            network = dict(pair["network"])
            port = network.pop("port_udp")
            key = network.pop("control_key_id")
            network["listen_port_udp" if component == "ev3" else "default_port"] = port
            if component == "ev3":
                network.update(max_packet_bytes=wire["max_datagram_bytes"],
                               max_payload_bytes=wire["max_datagram_bytes"] - wire["header_bytes"] - wire["hmac_bytes"])
            else:
                network.update(control_key_id=key, protocol_version=wire["protocol_version"])
                qualification = obj.setdefault("qualification", {})
                inject(qualification, {**scope, "required_user_inputs":
                       "NONE" if profile == "diagnostic" else "FULL_ARM"}, component)
            inject(obj["network"], network, component + ".network")
            results[component + suffix] = obj
    return results


def load_source(name):
    return source_objects()[name]

def canonical(value): return jcs.canonicalize(value)

def _reject_duplicates(pairs):
    seen={}
    for key,value in pairs:
        if key in seen: raise ValueError("duplicate mapping key: "+key)
        seen[key]=value
    return seen

def load(path):
    """Parse strict JSON. Duplicate mapping keys are a hard error, never last-key-wins."""
    def invalid_number(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates,
                      parse_constant=invalid_number)

def require(obj,keys,label):
    missing=[k for k in keys if k not in obj]
    if missing: raise ValueError("%s missing %s"%(label,missing))

def check_schema(schema):
    """Check all owned formats, including formats not materialized by BUILD."""
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object")
    unknown = set(schema) - KNOWN_KEYWORDS
    if unknown:
        raise ValueError("unsupported schema keywords " + str(sorted(unknown)))
    for key in ("properties", "$defs"):
        for child in schema.get(key, {}).values():
            check_schema(child)
    if "items" in schema:
        check_schema(schema["items"])


def validate_schema(value,schema,path="$",root_schema=None):
    """Validate the dependency-free JSON-Schema subset used by the owned runtime schemas.

    This host validator checks the supported schema subset without an external
    package dependency. Unknown schema keywords fail closed instead of being
    silently ignored by the authoring pipeline.
    """
    if root_schema is None: root_schema=schema
    unknown=set(schema)-KNOWN_KEYWORDS
    if unknown: raise ValueError(path+": unsupported schema keywords "+str(sorted(unknown)))
    if "$ref" in schema:
        ref=schema["$ref"]
        if not ref.startswith("#/"): raise ValueError(path+": external $ref unsupported")
        target=root_schema
        for part in ref[2:].split("/"): target=target[part.replace("~1","/").replace("~0","~")]
        return validate_schema(value,target,path,root_schema)
    # JSON equality distinguishes booleans from numbers; Python's True == 1 does not.
    if "const" in schema and canonical(value)!=canonical(schema["const"]): raise ValueError(path+": const mismatch")
    if "enum" in schema and not any(canonical(value)==canonical(item) for item in schema["enum"]): raise ValueError(path+": enum mismatch")
    types=schema.get("type")
    if types:
        if not isinstance(types,list):types=[types]
        def matches(t):
            return {"object":lambda:isinstance(value,dict),"array":lambda:isinstance(value,list),
                    "string":lambda:isinstance(value,str),"integer":lambda:isinstance(value,int) and not isinstance(value,bool),
                    "number":lambda:isinstance(value,(int,float)) and not isinstance(value,bool),
                    "boolean":lambda:isinstance(value,bool),"null":lambda:value is None}[t]()
        if not any(matches(t) for t in types): raise ValueError(path+": type mismatch")
    if isinstance(value,dict):
        for key in schema.get("required",[]):
            if key not in value: raise ValueError(path+": missing "+key)
        properties=schema.get("properties",{})
        if schema.get("additionalProperties") is False:
            extra=set(value)-set(properties)
            if extra: raise ValueError(path+": additional properties "+str(sorted(extra)))
        for key,child in properties.items():
            if key in value:validate_schema(value[key],child,path+"."+key,root_schema)
    if isinstance(value,list):
        if "minItems" in schema and len(value)<schema["minItems"]:raise ValueError(path+": minItems")
        if "maxItems" in schema and len(value)>schema["maxItems"]:raise ValueError(path+": maxItems")
        if "items" in schema:
            for index,item in enumerate(value):validate_schema(item,schema["items"],"%s[%d]"%(path,index),root_schema)
    if isinstance(value,str):
        if "minLength" in schema and len(value)<schema["minLength"]:raise ValueError(path+": minLength")
        if "maxLength" in schema and len(value)>schema["maxLength"]:raise ValueError(path+": maxLength")
        if "pattern" in schema and not re.search(schema["pattern"],value):raise ValueError(path+": pattern")
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if isinstance(value,float) and not math.isfinite(value): raise ValueError(path+": non-finite number")
        if "minimum" in schema and value<schema["minimum"]:raise ValueError(path+": minimum")
        if "maximum" in schema and value>schema["maximum"]:raise ValueError(path+": maximum")

def validate(name,obj):
    if name.startswith("commissioning_bundle"):
        require(obj,["schema_version"],name)
        if obj["schema_version"] != 1: raise ValueError(name+" schema_version")
    if name.startswith("commissioning_bundle"): require(obj,["revision","bundle_id","qualification_status","qualification_only","qualification_evidence_manifest_hash","actuator_scope_mask","safety_observation_mask","robot_geometry","drive_calibration","collision_model","joint_safe_sets","payload_profiles","safety_envelope"],name)
    else: require(obj,["robot_id","build_profile"],name)
    if "actuator_scope_mask" in obj and obj["actuator_scope_mask"] & ~obj["safety_observation_mask"]: raise ValueError(name+" actuator scope is not safety-observed")
    if name.startswith("ev3"):
        network,safety=obj["network"],obj["safety"]
        wire = load(ROOT / "schemas/shared/protocol/wire-schema.json")
        if (network["max_packet_bytes"] != wire["max_datagram_bytes"] or
                network["max_payload_bytes"] != wire["max_datagram_bytes"] - wire["header_bytes"] - wire["hmac_bytes"]):
            raise ValueError("wire bounds")
        if (network.get("discovery_service_type"),network.get("discovery_domain"),network.get("ip_family"))!=("_phantom-ev3._udp","local.","IPV4"): raise ValueError("DNS-SD contract")
        ports=[obj["axes"][x]["motor_port"] for x in ("base","shoulder","elbow","gripper")]
        if ports!=["outA","outB","outC","outD"] or obj["local_stop"]["sensor_port"]!="in4" or obj["gripper_home"]["sensor_port"]!="in3": raise ValueError("EV3 port contract")
        # Two-level loop policy: the SAFE_HOLD threshold must fire strictly before the fault threshold.
        if not safety["loop_safe_hold_ms"] < safety["loop_fault_ms"]: raise ValueError("loop_safe_hold_ms must be below loop_fault_ms")
        if safety["loop_safe_hold_ms"] > 60 or safety["loop_fault_ms"] > 100: raise ValueError("loop thresholds exceed safety deadlines")
        if safety["controller_heartbeat_timeout_ms"]*safety["controller_heartbeat_rate_hz"] < 1000: raise ValueError("heartbeat timeout is shorter than one heartbeat period")
        if obj.get("build_profile")=="Release" and (obj.get("qualification_only",False) or obj.get("actuator_scope_mask")!=15 or obj.get("safety_observation_mask")!=15): raise ValueError("Release scope contract")
        if obj.get("build_profile")=="Diagnostic" and (obj.get("qualification_only") is not True or obj.get("actuator_scope_mask")!=0 or obj.get("safety_observation_mask")!=0): raise ValueError("Diagnostic network-only qualification contract")
    if name.startswith("quest"):
        qualification=obj["qualification"]
        if qualification["actuator_scope_mask"] & ~qualification["safety_observation_mask"]: raise ValueError("Quest actuator scope is not safety-observed")
        if (obj["network"].get("discovery_service_type"),obj["network"].get("discovery_domain"),obj["network"].get("ip_family"))!=("_phantom-ev3._udp","local.","IPV4"): raise ValueError("Quest DNS-SD contract")
        if obj["network"]["ping_timeout_ms"]>obj["network"]["ping_interval_ms"]*obj["network"]["max_missed_pongs"]+obj["network"]["ping_interval_ms"]: raise ValueError("Quest ping timeout exceeds its own liveness budget")
        if obj["build_profile"]=="Release" and (qualification["qualification_only"] or qualification["actuator_scope_mask"]!=15 or qualification["safety_observation_mask"]!=15 or qualification["required_user_inputs"]!="FULL_ARM"):raise ValueError("Quest Release qualification contract")
        if name.endswith("network-only") and (obj["build_profile"]!="Diagnostic" or not qualification["qualification_only"] or qualification["actuator_scope_mask"]!=0 or qualification["safety_observation_mask"]!=0 or qualification["required_user_inputs"]!="NONE"):raise ValueError("Quest network-only qualification contract")

def measured_paths(name,value,path=""):
    found=[]
    if value is None and path in ("/network/commissioning_key_id",):return found
    if value is None or isinstance(value,str) and "MEASURED_REQUIRED" in value:found.append(name+".json#"+path)
    elif isinstance(value,dict):
        for key,child in value.items():found.extend(measured_paths(name,child,path+"/"+key))
    elif isinstance(value,list):
        for index,child in enumerate(value):found.extend(measured_paths(name,child,path+"/"+str(index)))
    return found

def qualification_blockers(bundle):
    """Validate actual per-robot data at admission, never during software BUILD."""
    validate_schema(bundle, load(schema_path("commissioning_bundle")))
    validate("commissioning_bundle", bundle)
    blocked = measured_paths("commissioning_bundle", bundle)
    if bundle["qualification_status"] != "QUALIFIED":
        blocked.append("commissioning_bundle.json#/qualification_status")
    if bundle["qualification_evidence_manifest_hash"] == "0" * 64:
        blocked.append("commissioning_bundle.json#/qualification_evidence_manifest_hash")
    for key in ("external_power_cut_present", "external_power_cut_tested"):
        if bundle["safety_envelope"][key] is not True:
            blocked.append("commissioning_bundle.json#/safety_envelope/" + key)
    for section in ("drive_calibration", "collision_model", "joint_safe_sets", "payload_profiles"):
        if bundle[section]["status"] != "QUALIFIED":
            blocked.append("commissioning_bundle.json#/" + section + "/status")
    for axis, curve in bundle["drive_calibration"]["axes"].items():
        if not curve:
            blocked.append("commissioning_bundle.json#/drive_calibration/axes/" + axis)
    for section, key in (("collision_model", "primitives"), ("joint_safe_sets", "profiles"),
                         ("payload_profiles", "profiles")):
        if not bundle[section][key]:
            blocked.append("commissioning_bundle.json#/" + section + "/" + key)
    mounts = bundle["robot_geometry"]["marker_mounts"]
    if not isinstance(mounts, (dict, list)) or len(mounts) != 10:
        blocked.append("commissioning_bundle.json#/robot_geometry/marker_mounts")
    return sorted(set(blocked))


def compile_configs():
    """Validate all candidates in memory before publishing any build files."""
    protocol_hash=(ROOT/"protocol"/"generated"/"schema.sha256").read_text().split()[0]
    protocol_semantics_hash=(ROOT/"protocol"/"generated"/"semantics.sha256").read_text().split()[0]
    protocol_contract_hash=(ROOT/"protocol"/"generated"/"contract.sha256").read_text().split()[0]
    ipc_hash=(ROOT/"protocol"/"generated"/"ipc_schema.sha256").read_text().split()[0]
    results={};objects=source_objects(); outputs={}
    for name,schema_name in VARIANTS:
        obj=objects[name];validate_schema(obj,load(schema_path(schema_name)));validate(name,obj)
        artifact=canonical(obj);results[name]=hashlib.sha256(artifact).hexdigest()
        outputs[generated_path(name)]=artifact+b"\n"
    for suffix in ("", "-network-only"):
        ev3 = objects["ev3" + suffix]
        quest = objects["quest" + suffix]["qualification"]
        for field in ("qualification_only", "actuator_scope_mask", "safety_observation_mask"):
            if ev3[field] != quest[field]:
                raise ValueError("development scope mismatch" + suffix)
        if objects["quest" + suffix]["network"]["telemetry_max_age_ms"] > ev3["network"]["session_stale_ms"]:
            raise ValueError("Quest telemetry budget exceeds EV3 session staleness" + suffix)
    validate_schema(bootstrap_descriptor(), load(ROOT / "schemas/ev3/network-only-session.schema.json"))
    # All robot-owned formats remain checkable without a real robot or its data.
    for path in (ROOT / "schemas").rglob("*.schema.json"):
        check_schema(load(path))
    manifest = {"schema_version": 4, "protocol_schema_hash": protocol_hash,
                "protocol_semantics_hash": protocol_semantics_hash,
                "protocol_contract_hash": protocol_contract_hash,
                "ipc_schema_hash": ipc_hash, "artifact_hashes": results,
                "bootstrap_descriptor_hash": bootstrap_hash(),
                "runtime_admission": "ROBOT_DATA_REQUIRED_FOR_MOTION"}
    outputs[ROOT / "build/config/manifest.json"]=canonical(manifest)+b"\n"
    return outputs, manifest


def prepare(for_tests=False):
    outputs, manifest = compile_configs()
    if for_tests:
        outputs[ROOT / "build/config/test-fixtures/network-only-session.json"] = canonical(bootstrap_descriptor()) + b"\n"
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_bytes() == data:
            continue
        import os, tempfile
        # A concurrently running test must not observe a truncated JSON file.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(data)
        try:
            try:
                os.replace(temporary, path)
            except PermissionError:
                # Windows may keep a file open in a fixture/IDE while another
                # command has already published the identical candidate.
                # Never ignore an error when the existing bytes differ.
                if not path.is_file() or path.read_bytes() != data:
                    raise
        finally:
            temporary.unlink(missing_ok=True)
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");args=parser.parse_args()
    if args.check:
        _, manifest = compile_configs()
    else:
        manifest = prepare()
    print("development config/schema contracts ok; motion admission uses external robot data")
if __name__=="__main__":main()
