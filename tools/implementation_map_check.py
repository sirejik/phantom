#!/usr/bin/env python3
"""Validate docs/implementation-map.json.

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
import docindex

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAP = ROOT / "docs" / "implementation-map.json"

PATH_TOKEN = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")


def known_sections():
    return {pathlib.Path(row[2]).name + "#" + row[0] for row in docindex.collect()}


def owner_reference_errors(owner, sections):
    errors = []
    for item in owner.split(";"):
        match = re.fullmatch(r"([a-z][a-z0-9-]*\.md#sec-[a-z0-9-]+)(?: \([A-Z][A-Z0-9-]*\))?", item.strip())
        if not match or match[1] not in sections:
            errors.append("normative owner reference does not resolve: " + item.strip())
    return errors


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
        # Resolve file + stable anchor directly, independently of display numbering.
        errors.extend(identifier + ": " + error for error in owner_reference_errors(
            str(entry.get("normative_owner", "")), sections))
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
