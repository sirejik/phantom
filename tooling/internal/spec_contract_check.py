#!/usr/bin/env python3
"""Check split-spec ownership, contextual wire semantics, and source hashes."""

import hashlib
import json
import pathlib
import re
import sys
import configgen


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL_SPEC = ROOT / "docs/protocol-specification.md"
SCHEMA = ROOT / "config/shared/protocol/wire-schema.json"


def fail(message):
    print("spec contract FAIL: " + message, file=sys.stderr)
    raise SystemExit(1)


def exact_utf8_lf(path):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        fail("%s has UTF-8 BOM" % path.relative_to(ROOT))
    if b"\r" in raw:
        fail("%s must use LF line endings" % path.relative_to(ROOT))
    try:
        return raw, raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("%s is not UTF-8" % path.relative_to(ROOT))


def check_prose_measured_contract(source_objects):
    """Every `MEASURED` field named by normative prose must exist in canonical config.

    Without this the prose can declare a safety-relevant measured parameter that
    never reaches the registry, which would silently defeat the READY gate.
    """
    documented={
        "docs/quest-specification.md":{
            "max_mapping_scale":"quest#/human_mapping/max_mapping_scale",
            "arm_reach_min_technical_m":"quest#/human_mapping/arm_reach_min_technical_m",
            "arm_reach_max_technical_m":"quest#/human_mapping/arm_reach_max_technical_m",
        },
    }
    flat={}
    for name,obj in source_objects.items():
        for path in configgen.measured_paths(name,obj): flat[path.split("#",1)[0].replace(".json","")+"#"+path.split("#",1)[1]]=path
    for document,mapping in documented.items():
        text=(ROOT/document).read_text(encoding="utf-8")
        for field,expected in mapping.items():
            if field not in text: raise ValueError("%s no longer declares %s"%(document,field))
            if expected not in flat: raise ValueError("prose MEASURED field %s is absent from canonical config (%s)"%(field,expected))


def main():
    source_objects = configgen.source_objects()
    check_prose_measured_contract(source_objects)
    _, protocol_text = exact_utf8_lf(PROTOCOL_SPEC)

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    canonical = json.dumps(
        schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    generated = (ROOT / "protocol/generated/wire_schema.canonical.json").read_bytes()
    if generated != canonical + b"\n":
        fail("canonical schema artifact is stale")
    structural = (ROOT / "protocol/generated/wire_schema.structural.json").read_bytes()
    if not structural.endswith(b"\n"):
        fail("structural schema artifact must be LF-terminated")
    digest = hashlib.sha256(structural[:-1]).hexdigest()
    recorded = (ROOT / "protocol/generated/schema.sha256").read_text(
        encoding="ascii"
    ).split()[0]
    if digest != recorded:
        fail("protocol schema hash does not cover structural canonical JSON")
    for artifact, digest_file, label in (
        ("protocol_semantics.canonical.json", "semantics.sha256", "protocol semantics"),
        ("protocol_contract.canonical.json", "contract.sha256", "protocol contract"),
    ):
        data = (ROOT / "protocol/generated" / artifact).read_bytes()
        expected = hashlib.sha256(data[:-1] if data.endswith(b"\n") else data).hexdigest()
        actual = (ROOT / "protocol/generated" / digest_file).read_text(encoding="ascii").split()[0]
        if expected != actual:
            fail(label + " hash does not cover its canonical JSON")

    required_semantics = (
        "config/shared/protocol/wire-schema.json",
        "config/shared/protocol/semantics.json",
        "docs/protocol-wire-reference.md",
        "HELLO.capabilities_requested",
        "ERR_UNSUPPORTED",
        "session_id=0",
        "hand-written",
    )
    for value in required_semantics:
        if value not in protocol_text:
            fail("contextual protocol semantics missing %s" % value)

    legacy_layout = re.compile(
        r"^0x[0-9A-Fa-f]{4}\s+\w+\s+—\s+\d+ bytes\n(?:  .+\n)+",
        re.MULTILINE,
    )
    if legacy_layout.search(protocol_text):
        fail("hand-written protocol prose contains a competing exact wire layout")

    print(
        "spec contract PASS: schema/prose ownership, "
        "%d schema messages, structural/semantic/contract identities" % len(schema["messages"])
    )


if __name__ == "__main__":
    main()
