#!/usr/bin/env python3
"""Validate authoring configs and emit canonical, self-hashed runtime artifacts."""
import argparse,hashlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"protocol"))
import jcs  # noqa: E402  single RFC 8785 canonicalizer, shared with the ev3dev runtime

# Every keyword the in-tree validator understands. Anything else is a schema
# authoring mistake and must fail closed rather than silently pass.
KNOWN_KEYWORDS={"$schema","$id","$ref","$defs","title","description","type","const","enum",
                "required","properties","additionalProperties","items","minLength","maxLength",
                "pattern","minimum","maximum","minItems","maxItems"}
STAGE_ORDER=("BUILD","HIL","READY")

def canonical(value): return jcs.canonicalize(value)

def _reject_duplicates(pairs):
    seen={}
    for key,value in pairs:
        if key in seen: raise ValueError("duplicate mapping key: "+key)
        seen[key]=value
    return seen

def load(path):
    """Parse strict JSON. Duplicate mapping keys are a hard error, never last-key-wins."""
    return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=_reject_duplicates)

def require(obj,keys,label):
    missing=[k for k in keys if k not in obj]
    if missing: raise ValueError("%s missing %s"%(label,missing))

def validate_schema(value,schema,path="$",root_schema=None):
    """Validate the dependency-free JSON-Schema subset used by config/schema.

    Keeping this tiny validator in-tree makes TEST and BUILD validation reproducible on the
    legacy EV3 toolchain. Unknown schema keywords fail closed instead of being
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
    if "const" in schema and value!=schema["const"]: raise ValueError(path+": const mismatch")
    if "enum" in schema and value not in schema["enum"]: raise ValueError(path+": enum mismatch")
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
        if "minimum" in schema and value<schema["minimum"]:raise ValueError(path+": minimum")
        if "maximum" in schema and value>schema["maximum"]:raise ValueError(path+": maximum")

def validate(name,obj):
    require(obj,["schema_version"],name)
    if obj["schema_version"]!=1: raise ValueError(name+" schema_version")
    if name.startswith("commissioning_bundle"): require(obj,["revision","bundle_id","qualification_status","qualification_only","qualification_evidence_manifest_hash","actuator_scope_mask","safety_observation_mask","robot_geometry","drive_calibration","collision_model","joint_safe_sets","payload_profiles","safety_envelope"],name)
    else: require(obj,["robot_id","build_profile"],name)
    if "actuator_scope_mask" in obj and obj["actuator_scope_mask"] & ~obj["safety_observation_mask"]: raise ValueError(name+" actuator scope is not safety-observed")
    if name.startswith("ev3"):
        network,safety=obj["network"],obj["safety"]
        if network["max_packet_bytes"]!=1024 or network["max_payload_bytes"]!=928: raise ValueError("wire bounds")
        if (network.get("discovery_service_type"),network.get("discovery_domain"),network.get("ip_family"))!=("_phantom-ev3._udp","local.","IPV4"): raise ValueError("DNS-SD contract")
        ports=[obj["axes"][x]["motor_port"] for x in ("base","shoulder","elbow","gripper")]
        if ports!=["outA","outB","outC","outD"] or obj["local_stop"]["sensor_port"]!="in4" or obj["gripper_home"]["sensor_port"]!="in3": raise ValueError("EV3 port contract")
        # Two-level loop policy: the SAFE_HOLD threshold must fire strictly before the fault threshold.
        if not safety["loop_safe_hold_ms"] < safety["loop_fault_ms"]: raise ValueError("loop_safe_hold_ms must be below loop_fault_ms")
        if safety["controller_heartbeat_timeout_ms"]*safety["controller_heartbeat_rate_hz"] < 1000: raise ValueError("heartbeat timeout is shorter than one heartbeat period")
        if obj.get("build_profile")=="Release" and (obj.get("qualification_only",False) or obj.get("actuator_scope_mask")!=15 or obj.get("safety_observation_mask")!=15): raise ValueError("Release scope contract")
        if obj.get("build_profile")=="Diagnostic" and (obj.get("qualification_only") is not True or obj.get("actuator_scope_mask")!=0 or obj.get("safety_observation_mask")!=0): raise ValueError("Diagnostic network-only qualification contract")
    if name.startswith("quest"):
        if obj["space"].get("require_current_room"): raise ValueError("room mesh cannot gate core path")
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

def check_measured_registry(source_objects,measured):
    """Enforce the MEASURED lifecycle instead of freezing every value at null.

    A registered parameter may hold a real measurement together with its
    evidence.  What is forbidden is a half-resolved entry, an unregistered
    placeholder, and an unresolved parameter whose `required_before` gate is the
    build itself.
    """
    placeholders=set()
    for name,obj in source_objects.items():
        if "network-only" not in name:placeholders.update(measured_paths(name,obj))
    registered=set(measured["parameters"])
    if placeholders!=registered:raise ValueError("MEASURED registry mismatch missing=%s stale=%s"%(sorted(placeholders-registered),sorted(registered-placeholders)))
    blocked={stage:[] for stage in STAGE_ORDER}
    for key,metadata in sorted(measured["parameters"].items()):
        require(metadata,["owner","measurement_procedure","required_before","units","validity_range","value","evidence"],key)
        if metadata["required_before"] not in STAGE_ORDER:raise ValueError(key+" required_before")
        resolved=metadata["value"] is not None
        if resolved != (metadata["evidence"] is not None):
            raise ValueError(key+" must carry value and evidence together")
        if not resolved: blocked[metadata["required_before"]].append(key)
    if blocked["BUILD"]:
        raise ValueError("unresolved MEASURED parameters already required at BUILD: %s"%blocked["BUILD"])
    gates={stage:("RESOLVED" if not blocked[stage] else "BLOCKED_UNQUALIFIED_MEASURED_VALUES") for stage in STAGE_ORDER}
    return gates,blocked

def check_prose_measured_contract(source_objects):
    """Every `MEASURED` field named by normative prose must exist in canonical config.

    Without this the prose can declare a safety-relevant measured parameter that
    never reaches the registry, which would silently defeat the READY gate.
    """
    documented={
        "docs/PHANTOM/QUEST_SPECIFICATION.md":{
            "max_mapping_scale":"quest#/human_mapping/max_mapping_scale",
            "arm_reach_min_technical_m":"quest#/human_mapping/arm_reach_min_technical_m",
            "arm_reach_max_technical_m":"quest#/human_mapping/arm_reach_max_technical_m",
        },
    }
    flat={}
    for name,obj in source_objects.items():
        for path in measured_paths(name,obj): flat[path.split("#",1)[0].replace(".json","")+"#"+path.split("#",1)[1]]=path
    for document,mapping in documented.items():
        text=(ROOT/document).read_text(encoding="utf-8")
        for field,expected in mapping.items():
            if field not in text: raise ValueError("%s no longer declares %s"%(document,field))
            if expected not in flat: raise ValueError("prose MEASURED field %s is absent from canonical config (%s)"%(field,expected))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");args=parser.parse_args()
    out=ROOT/"config"/"generated";out.mkdir(parents=True,exist_ok=True)
    protocol_hash=(ROOT/"protocol"/"generated"/"schema.sha256").read_text().split()[0]
    protocol_semantics_hash=(ROOT/"protocol"/"generated"/"semantics.sha256").read_text().split()[0]
    protocol_contract_hash=(ROOT/"protocol"/"generated"/"contract.sha256").read_text().split()[0]
    ipc_hash=(ROOT/"protocol"/"generated"/"ipc_schema.sha256").read_text().split()[0]
    spec_hash=hashlib.sha256((ROOT/"docs"/"PHANTOM_SPECIFICATION.md").read_bytes()).hexdigest()
    results={};source_objects={}
    variants=(("commissioning_bundle","commissioning_bundle"),("commissioning_bundle-network-only","commissioning_bundle"),("ev3","ev3"),("ev3-network-only","ev3"),("quest","quest"),("quest-network-only","quest"))
    for name,schema_name in variants:
        obj=load(ROOT/"config"/"source"/(name+".json"));source_objects[name]=obj;schema=load(ROOT/"config"/"schema"/(schema_name+".schema.json"));validate_schema(obj,schema);validate(name,obj);artifact=canonical(obj);digest=hashlib.sha256(artifact).hexdigest();results[name]=digest
        path=out/(name+".generated.json")
        if args.check:
            if not path.exists() or path.read_bytes()!=artifact+b"\n": raise SystemExit("generated config stale: "+str(path))
        else: path.write_bytes(artifact+b"\n")
    if source_objects["quest"]["commissioning_bundle"]["expected_hash"]!=results["commissioning_bundle"]:raise ValueError("Quest Release expected bundle hash mismatch")
    if source_objects["quest-network-only"]["commissioning_bundle"]["expected_hash"]!=results["commissioning_bundle-network-only"]:raise ValueError("Quest network-only expected bundle hash mismatch")
    for suffix in ("","-network-only"):
        bundle=source_objects["commissioning_bundle"+suffix]
        ev3=source_objects["ev3"+suffix]
        quest=source_objects["quest"+suffix]["qualification"]
        expected=(bundle["qualification_only"],bundle["qualification_evidence_manifest_hash"],bundle["actuator_scope_mask"],bundle["safety_observation_mask"])
        if (ev3["qualification_only"],ev3["qualification_evidence_manifest_hash"],ev3["actuator_scope_mask"],ev3["safety_observation_mask"])!=expected:raise ValueError("EV3/bundle qualification mismatch"+suffix)
        if (quest["qualification_only"],quest["qualification_evidence_manifest_hash"],quest["actuator_scope_mask"],quest["safety_observation_mask"])!=expected:raise ValueError("Quest/bundle qualification mismatch"+suffix)
        # The EV3 command-freshness budget and the Quest telemetry budget must be
        # compatible: a Quest that still calls telemetry fresh after EV3 already
        # dropped the command would show a stale robot as healthy.
        if source_objects["quest"+suffix]["network"]["telemetry_max_age_ms"]>ev3["network"]["session_stale_ms"]:raise ValueError("Quest telemetry budget exceeds EV3 session staleness"+suffix)
    measured=load(ROOT/"config"/"source"/"measured_parameters.json");validate_schema(measured,load(ROOT/"config"/"schema"/"measured_parameters.schema.json"))
    gates,blocked=check_measured_registry(source_objects,measured)
    check_prose_measured_contract(source_objects)
    artifact=canonical(measured);results["measured_parameters"]=hashlib.sha256(artifact).hexdigest();path=out/"measured_parameters.generated.json"
    if args.check:
        if not path.exists() or path.read_bytes()!=artifact+b"\n":raise SystemExit("generated measured registry stale")
    else:path.write_bytes(artifact+b"\n")
    manifest={"schema_version":1,"specification_sha256":spec_hash,"protocol_schema_hash":protocol_hash,
              "protocol_semantics_hash":protocol_semantics_hash,"protocol_contract_hash":protocol_contract_hash,
              "ipc_schema_hash":ipc_hash,"artifact_hashes":results,
              "measured_gates":gates,"ready_gate":gates["READY"]}
    data=canonical(manifest)+b"\n";path=out/"config-manifest.json"
    if args.check:
        if not path.exists() or path.read_bytes()!=data: raise SystemExit("generated manifest stale")
    else:path.write_bytes(data)
    print("config schema/contracts ok; READY gate=%s (%d unresolved MEASURED)"%(manifest["ready_gate"],sum(len(v) for v in blocked.values())))
if __name__=="__main__":main()
