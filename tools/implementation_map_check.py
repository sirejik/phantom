#!/usr/bin/env python3
"""Validate docs/PHANTOM/implementation-map.json.

The map exists so "not done" can be told apart from "forgotten": every entry
names the normative owner, the stage that owns it, the current status and the
verification that proves the status. This checker keeps it honest — the owner
section must resolve, statuses must come from the declared set, and any
verification that names a repository path must actually point at one.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAP = ROOT / "docs" / "PHANTOM" / "implementation-map.json"
SECTION_INDEX = ROOT / "docs" / "PHANTOM" / "SECTION_INDEX.md"

PATH_TOKEN = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")


def known_sections():
    text = SECTION_INDEX.read_text(encoding="utf-8")
    return set(re.findall(r"§(\d+(?:\.\d+)*)", text))


def main():
    document = json.loads(MAP.read_text(encoding="utf-8"))
    errors = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    statuses = set(document.get("statuses", []))
    if not statuses:
        errors.append("statuses must be declared")

    sections = known_sections()
    seen = set()
    for entry in document.get("entries", []):
        identifier = entry.get("id", "<missing id>")
        if identifier in seen:
            errors.append("duplicate entry id: " + identifier)
        seen.add(identifier)
        for field in ("id", "normative_owner", "stage", "status", "verification"):
            if not entry.get(field) and entry.get(field) != 0:
                errors.append("%s: missing %s" % (identifier, field))
        if entry.get("status") not in statuses:
            errors.append("%s: undeclared status %r" % (identifier, entry.get("status")))
        stage = entry.get("stage")
        if not isinstance(stage, int) or not 1 <= stage <= 10:
            errors.append("%s: stage must be 1..10" % identifier)
        # Each referenced section must exist in the generated index.
        for reference in re.findall(r"(\d+\.\d+(?:\.\d+)*)", str(entry.get("normative_owner", ""))):
            if reference not in sections:
                errors.append("%s: normative owner section §%s does not resolve" % (identifier, reference))
        for token in PATH_TOKEN.findall(str(entry.get("verification", ""))):
            if "/" not in token or token.endswith("/"):
                continue
            if not (ROOT / token).exists():
                errors.append("%s: verification names a missing path %s" % (identifier, token))

    if errors:
        print("implementation map FAIL:")
        for error in errors:
            print("  - " + error)
        return 1
    counts = {}
    for entry in document["entries"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    summary = ", ".join("%s=%d" % (name, counts[name]) for name in sorted(counts))
    print("implementation map PASS: %d entries (%s)" % (len(document["entries"]), summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
