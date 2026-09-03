#!/usr/bin/env python3
"""Audit the pinned Quest body provider without requiring an active XR session."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    lock = json.loads((ROOT / "PhantomQuest/Packages/packages-lock.json").read_text(encoding="utf-8-sig"))
    version = lock["dependencies"]["com.meta.xr.sdk.core"]["version"]
    candidates = list((ROOT / "PhantomQuest/Library/PackageCache").glob("com.meta.xr.sdk.core@*/Scripts/Movement/OVRBody.cs"))
    require(len(candidates) == 1, "exactly one resolved Meta XR Core OVRBody source is required")
    body_path = candidates[0]
    body_source = body_path.read_text(encoding="utf-8-sig")
    required = (
        "SimultaneousHandsAndControllersEnabled",
        "Body API and simultaneous hands and controllers cannot be enabled at the same time",
        "enabled = false",
    )
    for token in required:
        require(token in body_source, "expected explicit OVRBody compatibility guard is absent: " + token)
    editor_path = body_path.parents[1] / "Editor/Movement/OVRProjectSetupMovementSDKConfigurationTasks.cs"
    require(editor_path.is_file(), "Meta Movement project validation source is missing")
    editor_source = editor_path.read_text(encoding="utf-8-sig")
    require("Body API is not compatible with simultaneous hands and controllers" in editor_source,
            "Meta editor compatibility rule is missing")
    result = {
        "schema_version": 1,
        "audit_status": "PASS",
        "software_compatibility": "FAIL",
        "classification": "EXPLICITLY_DISABLED_OR_INCOMPATIBLE",
        "provider": "OVRBody/com.meta.xr.sdk.core",
        "version": version,
        "multimodal_required": True,
        "evidence": [
            str(body_path.relative_to(ROOT)).replace("\\", "/"),
            str(editor_path.relative_to(ROOT)).replace("\\", "/"),
        ],
        "reason": "Meta XR Core explicitly disables OVRBody when simultaneous hands and controllers are enabled",
    }
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if "--report" in sys.argv[1:]:
        report = ROOT / "results/quest/provider-compatibility-audit.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Quest provider source audit FAIL:", error, file=sys.stderr)
        sys.exit(1)
