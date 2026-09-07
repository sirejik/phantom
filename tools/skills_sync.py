#!/usr/bin/env python3
"""Mirror repository skills from `.agents/skills/` to `.claude/skills/`.

Codex discovers skills in `.agents/skills/`; Claude Code discovers them in
`.claude/skills/`. Rather than maintain two editable copies — which is the
duplicate-owner problem PHANTOM forbids — `.agents/skills/` is the single source
and this tool refreshes the mirror. `--check` fails when they diverge, so a skill
edited in only one place cannot ship.
"""
import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".agents" / "skills"
MIRROR = ROOT / ".claude" / "skills"
BANNER = "<!-- Mirrored from .agents/skills/ by tools/skills_sync.py. Edit the source, not this copy. -->\n"


def mirrored_text(path):
    text = path.read_text(encoding="utf-8")
    # The banner goes after the YAML frontmatter so skill discovery still sees it.
    if text.startswith("---"):
        end = text.find("\n---\n", 3)
        if end >= 0:
            head = text[:end + len("\n---\n")]
            return head + BANNER + text[end + len("\n---\n"):]
    return BANNER + text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print("no skills to mirror: " + str(SOURCE))
        return 0

    sources = sorted(SOURCE.rglob("SKILL.md"))
    problems = []
    for source in sources:
        relative = source.relative_to(SOURCE)
        target = MIRROR / relative
        expected = mirrored_text(source)
        if args.check:
            if not target.exists():
                problems.append("missing mirror: " + str(target.relative_to(ROOT)))
            elif target.read_text(encoding="utf-8") != expected:
                problems.append("stale mirror: " + str(target.relative_to(ROOT)))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(expected)

    expected_targets = {MIRROR / source.relative_to(SOURCE) for source in sources}
    if MIRROR.is_dir():
        for existing in sorted(MIRROR.rglob("SKILL.md")):
            if existing not in expected_targets:
                if args.check:
                    problems.append("orphaned mirror: " + str(existing.relative_to(ROOT)))
                else:
                    existing.unlink()
                    shutil.rmtree(existing.parent, ignore_errors=True)

    if problems:
        print("skills mirror FAIL:")
        for problem in problems:
            print("  - " + problem)
        print("run: python tools/skills_sync.py")
        return 1
    print("skills mirror %s: %d skills" % ("PASS" if args.check else "written", len(sources)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
