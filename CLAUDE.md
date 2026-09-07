# CLAUDE.md

@AGENTS.md

`AGENTS.md` is the canonical, single set of project rules for every AI agent working in this
repository. This file exists only so Claude Code loads it automatically; it deliberately adds
no rules of its own, because two independently editable rule sets would be exactly the kind of
competing source of truth PHANTOM forbids.

Repository skills live in `.agents/skills/` and are mirrored to `.claude/skills/` for Claude
Code discovery. Edit `.agents/skills/` only, then run `python tools/skills_sync.py` to refresh
the mirror; `python tools/skills_sync.py --check` fails if the two ever diverge.
