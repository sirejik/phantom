#!/usr/bin/env python3
"""Post-build metadata, hash, architecture, profile, and lock-file gate."""
import argparse,hashlib,json,pathlib,re,struct,subprocess,sys,tarfile,zipfile
from build_identity import identity
from source_hash import QUEST_SOURCE_INPUTS
from tooling.common.environment import quest_package
from configgen import compile_configs, generated_path
ROOT=pathlib.Path(__file__).resolve().parents[2]
def load(path):return json.loads(path.read_text(encoding="utf-8-sig"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_hash(*paths):return subprocess.check_output([sys.executable,str(ROOT/"tooling/internal/source_hash.py"),*paths],text=True).strip()
def require(condition,message):
    if not condition:raise ValueError(message)
def ev3_package_name(build_id):
    return f"phantom-{build_id}.tar.gz"
def verify_checksum_manifest(directory):
    manifest_path=directory/"SHA256SUMS"
    require(manifest_path.is_file(),f"SHA256SUMS missing: {directory}")
    raw=manifest_path.read_bytes()
    require(b"\r" not in raw,f"SHA256SUMS must be LF-only: {directory}")
    listed=set()
    for line in raw.decode("ascii").splitlines():
        match=re.fullmatch(r"([0-9a-f]{64})  (.+)",line)
        require(match is not None,f"invalid SHA256SUMS line: {line!r}")
        relative=match.group(2)
        require(relative not in listed,f"duplicate SHA256SUMS entry: {relative}")
        require(not pathlib.PurePosixPath(relative).is_absolute() and ".." not in pathlib.PurePosixPath(relative).parts,f"unsafe SHA256SUMS path: {relative}")
        artifact=directory/pathlib.PurePosixPath(relative)
        require(artifact.is_file(),f"SHA256SUMS file missing: {relative}")
        require(sha(artifact)==match.group(1),f"SHA256SUMS mismatch: {relative}")
        listed.add(relative)
    expected={path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.name!="SHA256SUMS"}
    require(listed==expected,f"SHA256SUMS inventory mismatch: {directory}")
def verify_quest_embedded_identity(apk,manifest):
    marker=manifest["build_id"].encode("ascii")
    with zipfile.ZipFile(apk) as archive:
        entries=[]
        for item in archive.infolist():
            data=archive.read(item)
            if marker in data:entries.append((item.filename,data))
        require(len(entries)==1,"Quest embedded build identity is missing or ambiguous")
        name,data=entries[0]
        start=data.rfind(b'{\"schema_version\":',0,data.index(marker))
        require(start>=0,"Quest embedded identity JSON start missing")
        lf=data.find(b"\n",data.index(marker))
        line_end=lf-1 if lf>=0 and data[lf-1:lf]==b"\r" else lf
        require(lf>=0 and data[line_end-1:line_end]==b"}","Quest embedded identity JSON terminator missing")
        end=lf+1;identity_bytes=data[start:end]
        require(sha_bytes(identity_bytes)==manifest["embedded_identity_sha256"],"Quest embedded identity SHA-256 mismatch")
        embedded=json.loads(identity_bytes.decode("utf-8-sig"))
        for field,value in embedded.items():require(manifest.get(field)==value,f"Quest embedded/sidecar mismatch: {field}")
        for provenance in ("apk_sha256","embedded_identity_sha256","signing_key_id","apk_signing_certificate_sha256","created_at"):
            require(provenance not in embedded,f"Quest external provenance embedded in APK: {provenance}")
        forbidden=(b".secrets/quest-release",b".secrets\\quest-release",b"keystore.pass")
        for item in archive.infolist():
            blob=archive.read(item)
            require(not any(value in blob for value in forbidden),f"Quest local signing path leaked into APK: {item.filename}")
        password=ROOT/".secrets/quest-release/keystore.pass"
        if password.is_file():
            secret=password.read_bytes().strip()
            if len(secret)>=4:
                for item in archive.infolist():require(secret not in archive.read(item),f"Quest signing password leaked into APK: {item.filename}")
def sha_bytes(data):return hashlib.sha256(data).hexdigest()
def verify_ev3_elf(path):
    with path.open("rb") as stream:header=stream.read(52)
    require(len(header)==52 and header[:7]==b"\x7fELF\x01\x01\x01","EV3 runtime must be ELF32 little-endian: "+str(path))
    require(struct.unpack_from("<H",header,18)[0]==40,"EV3 runtime must target ARM: "+str(path))
    require(not struct.unpack_from("<I",header,36)[0]&0x400,"EV3 runtime must not use hard-float ABI: "+str(path))
def verify_ev3_archive(package, directory=None):
    with tarfile.open(package,"r:gz") as archive:
        members=archive.getmembers()
        require(bool(members),"EV3 package is empty")
        members_by_name={}
        for member in members:
            path=pathlib.PurePosixPath(member.name)
            normalized=path.as_posix()
            require(normalized not in ("", ".") and not path.is_absolute() and ".." not in path.parts,"unsafe EV3 archive path: "+member.name)
            require(normalized not in members_by_name,"duplicate EV3 archive member: "+member.name)
            members_by_name[normalized]=member
            require(not (member.issym() or member.islnk()),"EV3 package must not contain links: "+member.name)
            require(member.isfile() or member.isdir(),"unsupported EV3 archive member: "+member.name)
            require(not member.name.endswith(('.py', '.pyc', '.pyo')), "EV3 package must not ship Python: " + member.name)
        required={"build-manifest.json","SHA256SUMS","bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom-maintenance"}
        require(required.issubset(members_by_name),"EV3 package inventory is incomplete")
        executables={"bin/phantom-controller","bin/phantom-safety","bin/phantom-network","bin/phantom-mdns","bin/phantom-device-integration-test","bin/phantom-maintenance"}
        for name in executables:
            member=members_by_name[name]
            require(member.isfile() and member.mode & 0o111,"EV3 runtime entry is not executable: "+name)
        if directory is not None:
            expected={path.relative_to(directory).as_posix():path for path in directory.rglob("*") if path.is_file()}
            actual={name:member for name,member in members_by_name.items() if member.isfile()}
            require(set(actual)==set(expected),"EV3 archive/file inventory mismatch")
            for name,member in actual.items():
                require(member.size==expected[name].stat().st_size,"EV3 archive size mismatch: "+name)
                digest=hashlib.sha256()
                with archive.extractfile(member) as stream:
                    for chunk in iter(lambda:stream.read(65536),b""):digest.update(chunk)
                require(digest.hexdigest()==sha(expected[name]),"EV3 archive content mismatch: "+name)
def main():
    parser=argparse.ArgumentParser(description="Validate one BUILD artifact")
    parser.add_argument("--component",required=True,choices=("QUEST","EV3"))
    parser.add_argument("--profile",default="Diagnostic",choices=("Release","Diagnostic"))
    parser.add_argument("--artifact",help="exact Quest APK or EV3 package path")
    parser.add_argument("--ev3-directory",help="exact unpacked EV3 BUILD directory")
    args=parser.parse_args()
    quest=args.component=="QUEST"
    profile=args.profile.lower()
    protocol_schema=(ROOT/"protocol/generated/schema.sha256").read_text().split()[0]
    protocol_semantics=(ROOT/"protocol/generated/semantics.sha256").read_text().split()[0]
    protocol_contract=(ROOT/"protocol/generated/contract.sha256").read_text().split()[0]
    outputs, config_manifest = compile_configs()
    expected_config = {
        component: {profile: hashlib.sha256(outputs[generated_path(
            component + ("-network-only" if profile == "diagnostic" else ""))]).hexdigest()
                    for profile in ("release", "diagnostic")}
        for component in ("ev3", "quest")}
    require(profile != "release", "Release publication requires external qualification evidence")
    expected_bundle = {"release": "0" * 64,
                       "diagnostic": config_manifest["bootstrap_descriptor_hash"]}
    if quest:
        package_manifest=load(ROOT/"PhantomQuest/Packages/manifest.json")
        package_lock=load(ROOT/"PhantomQuest/Packages/packages-lock.json")
        for package,version in package_manifest["dependencies"].items():
            if package.startswith("com.unity.modules."):continue
            require(package in package_lock["dependencies"],"package missing from lock: "+package)
            require(package_lock["dependencies"][package]["version"]==version,"package lock mismatch: "+package)
        expected_source=source_hash(*QUEST_SOURCE_INPUTS)
        apk=pathlib.Path(args.artifact).resolve() if args.artifact else ROOT/f"build/quest/PhantomQuest-{profile}.apk";manifest_path=pathlib.Path(str(apk)+".build-manifest.json")
        require(apk.is_file() and manifest_path.is_file(),"Quest artifact missing: "+profile)
        manifest=load(manifest_path)
        require(manifest.get("schema_version")==8 and manifest.get("build_identity_schema")=="PHANTOM-BUILD-V4" and manifest.get("component")=="QUEST","Quest build manifest schema mismatch")
        require(manifest["build_profile"].lower()==profile,"Quest profile mismatch")
        require(manifest["apk_sha256"]==sha(apk),"Quest APK hash mismatch")
        require(manifest["protocol_schema_hash"]==protocol_schema and manifest["protocol_semantics_hash"]==protocol_semantics and manifest["protocol_contract_hash"]==protocol_contract,"Quest source/contract hash mismatch")
        require(manifest["config_hash"]==expected_config["quest"][profile],"Quest config hash mismatch")
        require(manifest.get("commissioning_bundle_hash")==expected_bundle[profile],"Quest bundle hash mismatch")
        require(manifest["source_tree_hash"]==expected_source,"Quest artifact was not built from current sources")
        require(manifest["package_lock_sha256"]==sha(ROOT/"PhantomQuest/Packages/packages-lock.json"),"Quest package lock hash mismatch")
        require(manifest.get("toolchain_or_package_lock_hash")==manifest["package_lock_sha256"],"Quest identity lock hash mismatch")
        expected_build_id,_=identity("QUEST",manifest["build_profile"],expected_source,protocol_contract,
                                     expected_config["quest"][profile],manifest["package_lock_sha256"])
        require(manifest.get("build_id")==expected_build_id,"Quest build_id mismatch")
        require(re.fullmatch(r"[0-9a-f]{64}",manifest.get("embedded_identity_sha256","")) is not None,"Quest embedded identity hash missing")
        verify_quest_embedded_identity(apk,manifest)
        expected_versions={
            "meta_xr_core_version":package_lock["dependencies"]["com.meta.xr.sdk.core"]["version"],
            "movement_sdk_version":package_lock["dependencies"]["com.meta.xr.sdk.core"]["version"],
            "mruk_version":package_lock["dependencies"]["com.meta.xr.mrutilitykit"]["version"],
            "openxr_plugin_version":package_lock["dependencies"]["com.unity.xr.openxr"]["version"],
            "meta_openxr_version":package_lock["dependencies"]["com.unity.xr.meta-openxr"]["version"],
            "xr_hands_version":package_lock["dependencies"]["com.unity.xr.hands"]["version"],
        }
        for field,version in expected_versions.items():require(manifest.get(field)==version,f"Quest {field} mismatch")
        require(manifest.get("body_tracking_provider")=="OVRBody/com.meta.xr.sdk.core","Quest body tracking provider mismatch")
        require(manifest.get("multimodal_required") is (profile=="release"),"Quest multimodal requirement/profile mismatch")
        require(manifest.get("qualification_eligible") is True,"Quest qualification eligibility/profile mismatch")
        require(manifest.get("signing_key_id")=="phantom-quest-release","Quest signing identity is missing")
        require(re.fullmatch(r"[0-9a-f]{64}",manifest.get("apk_signing_certificate_sha256","")) is not None,"Quest signing certificate SHA-256 is missing")
        require(manifest.get("body_provider_joint_set")=="UpperBody","Quest body joint set mismatch")
        require(manifest.get("body_right_shoulder_api")=="OVRPlugin.BoneId.Body_RightShoulder","Quest right-shoulder API mismatch")
        require(manifest.get("body_multimodal_compatibility") in {"NO_EXPLICIT_SDK_GUARD_FOUND","INCOMPATIBLE_EXPLICIT_SDK_GUARD"},"Quest provider compatibility classification missing")
        with zipfile.ZipFile(apk) as archive:
            names=set()
            for item in archive.infolist():
                path=pathlib.PurePosixPath(item.filename)
                require(not path.is_absolute() and ".." not in path.parts,"unsafe Quest APK path: "+item.filename)
                require(item.filename not in names,"duplicate Quest APK entry: "+item.filename)
                names.add(item.filename)
            require("AndroidManifest.xml" in names and "classes.dex" in names,"Quest APK structure is incomplete")
            android_manifest=archive.read("AndroidManifest.xml")
        require(quest_package().encode("utf-16le") in android_manifest,"Quest APK application id mismatch")
        for permission in ("android.permission.INTERNET","com.oculus.permission.HAND_TRACKING","com.oculus.permission.BODY_TRACKING","com.oculus.permission.USE_SCENE","com.oculus.permission.USE_ANCHOR_API"):
            require(permission.encode("utf-16le") in android_manifest,"Quest APK permission missing: "+permission)
    else:
        from tooling.common.environment import toolchain_hash, cross_recipe, compiler_target
        _, base_image, recipe_hash = cross_recipe()
        expected_source=source_hash("--component","EV3")
        directory=pathlib.Path(args.ev3_directory).resolve() if args.ev3_directory else ROOT/f"build/ev3-armel/{profile}"
        manifest=load(directory/"build-manifest.json")
        require(manifest.get("schema_version")==5 and manifest.get("build_identity_schema")=="PHANTOM-BUILD-V4" and manifest.get("component")=="EV3","EV3 build manifest schema mismatch")
        require(manifest["build_profile"].lower()==profile,"EV3 profile mismatch")
        require(manifest["protocol_schema_hash"]==protocol_schema and manifest["protocol_semantics_hash"]==protocol_semantics and manifest["protocol_contract_hash"]==protocol_contract,"EV3 source/contract hash mismatch")
        require(manifest["config_hash"]==expected_config["ev3"][profile],"EV3 config hash mismatch")
        require(manifest.get("commissioning_bundle_hash")==expected_bundle[profile],"EV3 bundle hash mismatch")
        require(manifest["source_tree_hash"]==expected_source,"EV3 artifact was not built from current sources")
        require(manifest.get("toolchain_or_package_lock_hash")==toolchain_hash(manifest["cross_image"]),"EV3 identity lock hash mismatch")
        expected_build_id,_=identity("EV3",manifest["build_profile"],expected_source,protocol_contract,expected_config["ev3"][profile],manifest["toolchain_or_package_lock_hash"])
        require(manifest.get("build_id")==expected_build_id,"EV3 build_id mismatch")
        require(manifest.get("qualification_eligible") is True,"EV3 qualification eligibility/profile mismatch")
        require(not (directory / "commissioning-bundle.generated.json").exists(),
                "software package must not contain per-robot calibration data")
        verify_checksum_manifest(directory)
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", manifest.get("cross_image", "")) is not None,
                "prepared image ID must be immutable")
        require(manifest.get("cross_image_base") == base_image, "base image mismatch")
        require(manifest.get("cross_image_recipe_sha256") == recipe_hash, "Dockerfile recipe mismatch")
        require(manifest.get("compiler_target") == compiler_target(manifest["toolchain_facts"]),
                "observed compiler target mismatch")
        require(manifest["controller_sha256"]==sha(directory/"bin/phantom-controller"),"controller hash mismatch")
        require(manifest["safety_sha256"]==sha(directory/"bin/phantom-safety"),"safety hash mismatch")
        for name in ("phantom-controller","phantom-safety","phantom-network","phantom-mdns","phantom-maintenance","phantom-device-integration-test"):verify_ev3_elf(directory/"bin"/name)
        ev3_manifest=manifest
        package=pathlib.Path(args.artifact).resolve() if args.artifact else ROOT/"build/ev3-packages"/ev3_package_name(ev3_manifest["build_id"])
        provenance=pathlib.Path(str(package)+".build-manifest.json")
        require(package.is_file() and provenance.is_file(),"EV3 Diagnostic package/provenance missing")
        package_manifest=load(provenance)
        require(package_manifest.get("component")=="EV3" and package_manifest.get("build_profile").lower()==profile,"EV3 package profile mismatch")
        require(package_manifest.get("build_id")==ev3_manifest["build_id"],"EV3 package build_id mismatch")
        require(package_manifest.get("source_tree_hash")==ev3_manifest["source_tree_hash"],"EV3 package source hash mismatch")
        require(package_manifest.get("artifact_sha256")==sha(package),"EV3 package SHA-256 mismatch")
        verify_ev3_archive(package,directory)
    print("BUILD artifact validation PASS: component=%s profile=%s"%(args.component,args.profile))
if __name__=="__main__":
    try:main()
    except Exception as error:print("artifact gate FAIL:",error,file=sys.stderr);sys.exit(1)
