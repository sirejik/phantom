#!/usr/bin/env python3
"""Post-build metadata, hash, architecture, profile, and lock-file gate."""
import hashlib,json,pathlib,re,subprocess,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(path):return json.loads(path.read_text(encoding="utf-8-sig"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_hash(*paths):return subprocess.check_output([sys.executable,str(ROOT/"tools/source_hash.py"),*paths],text=True).strip()
def require(condition,message):
    if not condition:raise ValueError(message)
def compiler_matches(expected,facts):
    """Match the locked executable and Debian package revision independently.

    GCC prints the distribution revision in parentheses, so the lock's compact
    ``executable revision`` form is intentionally not a literal substring.
    """
    parts=expected.split()
    return len(parts)>=2 and facts.split()[0]==parts[0] and parts[-1] in facts
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
def main():
    quest_only="--quest-only" in sys.argv[1:]
    unknown=[arg for arg in sys.argv[1:] if arg!="--quest-only"]
    require(not unknown,"unknown arguments: "+", ".join(unknown))
    protocol=(ROOT/"protocol/generated/schema.sha256").read_text().split()[0]
    specification=sha(ROOT/"docs/PHANTOM_SPECIFICATION.md")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    lock=None if quest_only else load(ROOT/"toolchains/ev3dev-stretch.lock.json")
    if lock is not None:require(lock["cross_image_digest"]=="sha256:819ea7442bbe109d2b39c6c7766e7d1fe635bb98b86c4f6c3b636c0ce176a29f","cross image digest not pinned")
    package_manifest=load(ROOT/"PhantomQuest/Packages/manifest.json")
    package_lock=load(ROOT/"PhantomQuest/Packages/packages-lock.json")
    for package,version in package_manifest["dependencies"].items():
        if package.startswith("com.unity.modules."):continue
        require(package in package_lock["dependencies"],"package missing from lock: "+package)
        require(package_lock["dependencies"][package]["version"]==version,"package lock mismatch: "+package)
    expected_config={"quest":sha(ROOT/"config/generated/quest.generated.json"),
                     "ev3":{"release":sha(ROOT/"config/generated/ev3.generated.json"),
                            "diagnostic":sha(ROOT/"config/generated/ev3-network-only.generated.json")}}
    config_manifest=load(ROOT/"config/generated/config-manifest.json")
    expected_bundle={"release":config_manifest["artifact_hashes"]["commissioning_bundle"],
                     "diagnostic":config_manifest["artifact_hashes"]["commissioning_bundle-network-only"]}
    expected_source={"quest":source_hash("PhantomQuest/Assets/Phantom","PhantomQuest/Assets/Plugins","PhantomQuest/Packages","PhantomQuest/ProjectSettings"),"ev3":source_hash("ev3","protocol/generated")}
    for profile in ("release","diagnostic"):
        apk=ROOT/f"build/quest/PhantomQuest-{profile}.apk";manifest_path=pathlib.Path(str(apk)+".build-manifest.json")
        require(apk.is_file() and manifest_path.is_file(),"Quest artifact missing: "+profile)
        manifest=load(manifest_path)
        require(manifest.get("schema_version")==3,"Quest build manifest schema mismatch")
        require(manifest["build_profile"].lower()==profile,"Quest profile mismatch")
        require(manifest["git_commit"]==commit and manifest.get("worktree_dirty") is False,"Quest artifact is not from the clean current commit")
        require(manifest["apk_sha256"]==sha(apk),"Quest APK hash mismatch")
        require(manifest["protocol_schema_hash"]==protocol and manifest["specification_sha256"]==specification,"Quest source hash mismatch")
        require(manifest["config_hash"]==expected_config["quest"],"Quest config hash mismatch")
        require(manifest["source_tree_hash"]==expected_source["quest"],"Quest artifact was not built from current sources")
        require(manifest["package_lock_sha256"]==sha(ROOT/"PhantomQuest/Packages/packages-lock.json"),"Quest package lock hash mismatch")
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
        require(manifest.get("multimodal_required") is True,"Quest multimodal requirement missing")
        require(manifest.get("body_provider_joint_set")=="UpperBody","Quest body joint set mismatch")
        require(manifest.get("body_right_shoulder_api")=="OVRPlugin.BoneId.Body_RightShoulder","Quest right-shoulder API mismatch")
        require(manifest.get("body_multimodal_compatibility") in {"NO_EXPLICIT_SDK_GUARD_FOUND","INCOMPATIBLE_EXPLICIT_SDK_GUARD"},"Quest provider compatibility classification missing")
        with zipfile.ZipFile(apk) as archive:android_manifest=archive.read("AndroidManifest.xml")
        for permission in ("android.permission.INTERNET","com.oculus.permission.HAND_TRACKING","com.oculus.permission.BODY_TRACKING","com.oculus.permission.USE_SCENE","com.oculus.permission.USE_ANCHOR_API"):
            require(permission.encode("utf-16le") in android_manifest,"Quest APK permission missing: "+permission)
        for family in (() if quest_only else ("ev3-host","ev3-armel")):
            directory=ROOT/f"build/{family}-{profile}" if family=="ev3-host" else ROOT/f"build/{family}/{profile}"
            manifest=load(directory/"build-manifest.json")
            require(manifest["build_profile"].lower()==profile,f"{family} profile mismatch")
            require(manifest["git_commit"]==commit and manifest.get("worktree_dirty") is False,f"{family} artifact is not from the clean current commit")
            require(manifest["protocol_schema_hash"]==protocol and manifest["specification_sha256"]==specification,f"{family} source hash mismatch")
            require(manifest["config_hash"]==expected_config["ev3"][profile],f"{family} config hash mismatch")
            require(manifest.get("commissioning_bundle_hash")==expected_bundle[profile],f"{family} bundle hash mismatch")
            require(manifest["source_tree_hash"]==expected_source["ev3"],f"{family} artifact was not built from current sources")
            verify_checksum_manifest(directory)
            if family=="ev3-armel":
                require(manifest["cross_image"].endswith(lock["cross_image_digest"]),"armel image mismatch")
                require(compiler_matches(lock["cross_toolchain"],manifest["toolchain_facts"]),"armel compiler version mismatch")
                require(lock["cross_toolchain_binary_sha256"] in manifest["toolchain_facts"],"armel compiler hash mismatch")
                require(manifest["controller_sha256"]==sha(directory/"bin/phantom-controller"),"controller hash mismatch")
                require(manifest["safety_sha256"]==sha(directory/"bin/phantom-safety"),"safety hash mismatch")
    print("artifact gate PASS: "+("Quest package locks, profiles, hashes, metadata" if quest_only else "package locks, profiles, hashes, metadata, pinned armel image"))
if __name__=="__main__":
    try:main()
    except Exception as error:print("artifact gate FAIL:",error,file=sys.stderr);sys.exit(1)
