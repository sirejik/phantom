#!/usr/bin/env python3
"""Механические проверки документации PHANTOM для CI и agent workflows."""

from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PH = ROOT / "docs" / "PHANTOM"
SPEC_SET = PH / "spec-set.json"
SUPPORTING = [PH / "REFERENCES.md"]

ANCHOR_RE = re.compile(r'<a id="(sec-[^"]+)"></a>')
SECTION_REF_RE = re.compile(r'§(\d+(?:\.\d+)*)')
MD_LINK_RE = re.compile(r'\[[^\]]*\]\(([^)]+)\)')

def norm(path):
    return path.read_text(encoding="utf-8").replace("\r\n","\n").replace("\r","\n")

def main():
    errors = []
    cfg = json.loads(SPEC_SET.read_text(encoding="utf-8"))
    rels = cfg.get("normative_files", [])
    if not rels or len(rels) != len(set(rels)):
        errors.append("spec-set normative_files должен быть непустым и содержать уникальные значения")

    active = []
    for rel in rels:
        p = ROOT / rel
        if not p.is_file():
            errors.append(f"отсутствует нормативный документ: {rel}")
        else:
            active.append(p)
    active.extend(p for p in SUPPORTING if p.is_file())

    # Проверки generated-файлов
    for script, args in [
        ("tools/specgen.py", ["--check"]),
        ("tools/docindex.py", ["--check"]),
    ]:
        cp = subprocess.run([sys.executable, "-S", str(ROOT/script), *args],
                            cwd=ROOT, text=True, capture_output=True)
        if cp.returncode != 0:
            errors.append((cp.stdout + cp.stderr).strip() or f"проверка {script} завершилась ошибкой")

    # Баланс Markdown fenced blocks и относительные ссылки.
    all_md = list(PH.rglob("*.md"))
    all_md += [ROOT/"AGENTS.md", ROOT/"ARCHITECTURE.md"]
    for p in all_md:
        if not p.is_file():
            continue
        txt = norm(p)
        if txt.count("```") % 2:
            errors.append(f"несбалансированный fenced code block: {p.relative_to(ROOT)}")
        for m in MD_LINK_RE.finditer(txt):
            target = m.group(1).strip()
            if target.startswith(("http://","https://","mailto:","#")):
                continue
            file_part = target.split("#",1)[0]
            if not file_part:
                continue
            q = (p.parent / file_part).resolve()
            if not q.exists():
                errors.append(f"битая относительная ссылка в {p.relative_to(ROOT)}: {target}")

    # Глобальный ownership стабильных section anchors.
    owners = {}
    for p in active:
        for anchor in ANCHOR_RE.findall(norm(p)):
            if anchor in owners:
                errors.append(
                    f"дублирующий section anchor {anchor}: "
                    f"{owners[anchor].relative_to(ROOT)} and {p.relative_to(ROOT)}"
                )
            owners[anchor] = p

    # Каждая ссылка § в постоянной документации/project guidance/skills должна разрешаться.
    section_ref_files = list(all_md)
    skills_root = ROOT / ".agents" / "skills"
    if skills_root.is_dir():
        section_ref_files.extend(skills_root.rglob("SKILL.md"))
    seen_section_files = set()
    for p in section_ref_files:
        if not p.is_file():
            continue
        rp = p.resolve()
        if rp in seen_section_files:
            continue
        seen_section_files.add(rp)
        txt = norm(p)
        for m in SECTION_REF_RE.finditer(txt):
            anchor = "sec-" + m.group(1).replace(".", "-")
            if anchor not in owners:
                errors.append(
                    f"неразрешимая ссылка на раздел §{m.group(1)} в {p.relative_to(ROOT)}"
                )

    # Repo skills: обязательный frontmatter и согласованность directory/name.
    skills_root = ROOT / ".agents" / "skills"
    if skills_root.is_dir():
        for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
            sp = skill_dir / "SKILL.md"
            if not sp.is_file():
                errors.append(f"у Skill отсутствует SKILL.md: {skill_dir.relative_to(ROOT)}")
                continue
            st = norm(sp)
            fm = re.match(r"^---\n(.*?)\n---\n", st, re.S)
            if not fm:
                errors.append(f"у Skill отсутствует YAML frontmatter: {sp.relative_to(ROOT)}")
                continue
            name_m = re.search(r"^name:\s*(\S+)\s*$", fm.group(1), re.M)
            desc_m = re.search(r"^description:\s*(.+?)\s*$", fm.group(1), re.M)
            if not name_m or not desc_m:
                errors.append(f"frontmatter Skill требует name+description: {sp.relative_to(ROOT)}")
                continue
            if name_m.group(1) != skill_dir.name:
                errors.append(
                    f"несовпадение name/directory Skill: {sp.relative_to(ROOT)} "
                    f"name={name_m.group(1)!r}"
                )
            if len(desc_m.group(1)) > 600:
                errors.append(f"description Skill слишком длинный для эффективного discovery: {sp.relative_to(ROOT)}")

    # Явные относительные ссылки `#sec-*` должны указывать на anchor в целевом файле.
    for p in all_md:
        if not p.is_file():
            continue
        txt = norm(p)
        for m in MD_LINK_RE.finditer(txt):
            target = m.group(1).strip()
            if "#sec-" not in target or target.startswith(("http://", "https://")):
                continue
            file_part, anchor = target.split("#", 1)
            q = (p.parent / file_part).resolve() if file_part else p.resolve()
            if q.is_file():
                qtxt = q.read_text(encoding="utf-8", errors="strict")
                if f'<a id="{anchor}"></a>' not in qtxt:
                    errors.append(
                        f"битая ссылка на section anchor в {p.relative_to(ROOT)}: {target}"
                    )

    # Retired paths не должны снова появляться в постоянных project guidance/docs/skills.
    # Сам этот файл содержит denylist literals и намеренно исключён.
    retired = (
        "QUEST_IMPLEMENTATION_STATUS.md",
        "QUEST_UDP_PROTOCOL.md",
        "EV3_LEGACY_RISK.md",
        "PHANTOM_ROADMAP.md",
        "status/history/",
    )
    retired_scan = list(all_md)
    if skills_root.is_dir():
        retired_scan.extend(skills_root.rglob("SKILL.md"))
    seen_retired_files = set()
    for p in retired_scan:
        if not p.is_file() or p.resolve() == Path(__file__).resolve():
            continue
        rp = p.resolve()
        if rp in seen_retired_files:
            continue
        seen_retired_files.add(rp)
        txt = norm(p)
        for name in retired:
            if name in txt:
                errors.append(
                    f"retired path/name упомянут в постоянном файле {p.relative_to(ROOT)}: {name}"
                )

    # Semantic ownership anti-regressions for the split wire contract.
    protocol_spec = PH / "PROTOCOL_SPECIFICATION.md"
    if protocol_spec.is_file():
        pt = norm(protocol_spec)
        forbidden_protocol_patterns = (
            (r"\| Значение \| Сообщение \|", "hand-written numeric message-id table"),
            (r"status_flags\.bit\d+", "hand-written status flag bit position"),
            (r"\bgenerated wire codec\b", "codec incorrectly required to be generated"),
            (r"\bmirror §11\.8\b", "§11.8 incorrectly treated as numeric wire mirror"),
            (r"\| Code \| State \|", "hand-written numeric state-code table"),
            (r"\| Code \| Fault \|", "hand-written numeric fault-code table"),
        )
        for pattern, reason in forbidden_protocol_patterns:
            if re.search(pattern, pt, re.I):
                errors.append(f"protocol ownership regression ({reason}): {protocol_spec.relative_to(ROOT)}")

    # No other normative document may address telemetry status flags by hard-coded bit index.
    for p in active:
        if not p.is_file():
            continue
        if re.search(r"status_flags\.bit\d+", norm(p), re.I):
            errors.append(
                f"schema-owned status flag bit duplicated in normative prose: {p.relative_to(ROOT)}"
            )

    # Python cache/bytecode никогда не должны быть tracked. Локальные untracked caches игнорируются.
    if (ROOT / ".git").exists():
        cp = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            text=False,
            capture_output=True,
        )
        if cp.returncode == 0:
            tracked = [x.decode("utf-8", errors="replace") for x in cp.stdout.split(b"\0") if x]
            for rel in tracked:
                parts = Path(rel).parts
                if rel.endswith((".pyc", ".pyo")) or "__pycache__" in parts:
                    errors.append(f"tracked Python cache/bytecode запрещён: {rel}")

    if errors:
        print("PHANTOM DOCLINT: ОШИБКА")
        for e in errors:
            print(f"- {e}")
        return 1

    print("PHANTOM DOCLINT: PASS")
    print(f"- нормативных документов: {len(rels)}")
    print(f"- индексированных section anchors: {len(owners)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
