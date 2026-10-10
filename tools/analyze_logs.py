"""One host entry point for collected Quest captures and EV3 service journals."""
import argparse
import json
from pathlib import Path

from quest_validation import analyze as quest


def ev3_summary(paths):
    counts = {}
    warnings = 0
    total = 0
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"{path}:{number}: expected journal object")
            unit = event.get("_SYSTEMD_UNIT", "unknown")
            if not isinstance(unit, str):
                raise ValueError(f"{path}:{number}: invalid unit")
            total += 1
            counts[unit] = counts.get(unit, 0) + 1
            priority = event.get("PRIORITY")
            if priority is not None and int(priority) <= 4:
                warnings += 1
    return {"component": "EV3", "records": total, "by_service": counts,
            "warning_or_error_records": warnings, "hardware_verdict": "NOT_MEASURED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=("EV3", "QUEST"))
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    paths = []
    for item in args.inputs:
        if not item.exists():
            parser.error(f"input does not exist: {item}")
        paths.extend(sorted(item.rglob("*.jsonl")) if item.is_dir() else [item])
    # Prevent generated summaries from becoming inputs on the next invocation.
    paths = [path for path in paths if args.out.resolve() not in path.resolve().parents]
    args.out.mkdir(parents=True, exist_ok=True)
    if args.component == "QUEST":
        quest.write_reports(quest.load(paths), args.out)
    else:
        summary = ev3_summary(paths)
        (args.out / "ev3-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.component}: analyzed {len(paths)} files -> {args.out}")


if __name__ == "__main__":
    main()
