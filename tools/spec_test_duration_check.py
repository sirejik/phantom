#!/usr/bin/env python3
"""Reject normative test cases whose single-case duration exceeds 60 seconds."""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/PHANTOM_SPECIFICATION.md"
PATTERNS = (
    re.compile(r"30[- ]?минут", re.IGNORECASE),
    re.compile(r">=?\s*30\s*min", re.IGNORECASE),
    re.compile(r"не менее\s+`?30\s*min", re.IGNORECASE),
    re.compile(r"длительн\w*\s+(?:тест|прогон|использован|поток|HOLD)", re.IGNORECASE),
)


def main():
    violations = []
    for number, line in enumerate(SPEC.read_text(encoding="utf-8-sig").splitlines(), 1):
        if any(pattern.search(line) for pattern in PATTERNS):
            violations.append({"line": number, "text": line.strip()})
    report = {
        "schema_version": 1,
        "test_case_limit_seconds": 60,
        "preferred_case_duration_seconds": "5..30",
        "mandatory_test_cases_longer_than_60_seconds": len(violations),
        "status": "PASS" if not violations else "FAIL",
        "violations": violations,
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if "--report" in sys.argv[1:]:
        path = ROOT / "results/quest/spec-duration-audit.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    if violations:
        sys.exit(1)


if __name__ == "__main__":
    main()
