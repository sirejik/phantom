#!/usr/bin/env python3
"""Механические проверки документации PHANTOM для CI и agent workflows."""

from pathlib import Path
import json
import re
import subprocess
import sys
import docindex

ROOT = Path(__file__).resolve().parents[1]
PH = ROOT / "docs"
SPEC_SET = PH / "spec-set.json"
SUPPORTING = [PH / "references.md"]

ANCHOR_RE = re.compile(r'<a id="(sec-[^"]+)"></a>')
SECTION_REF_RE = re.compile(r'§(\d+(?:\.\d+)*)')
MD_LINK_RE = re.compile(r'\[[^\]]*\]\(([^)]+)\)')

def norm(path):
    return path.read_text(encoding="utf-8").replace("\r\n","\n").replace("\r","\n")


def numbering_errors(text):
    """Each document has one title and a consecutive local heading hierarchy."""
    errors = []
    counts = [0] * 5
    fenced = False
    titles = 0
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if fenced:
            continue
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match:
            continue
        depth = len(match[1]) - 2
        if depth < 0:
            titles += 1
            continue
        counts[depth] += 1
        counts[depth + 1:] = [0] * (4 - depth)
        expected = ".".join(map(str, counts[:depth + 1]))
        if not all(counts[:depth + 1]) or docindex.heading_number(match[2]) != expected:
            errors.append(f"ожидался раздел {expected}: {line}")
    if titles != 1:
        errors.append(f"ожидался один заголовок документа, найдено {titles}")
    return errors

def product_traceability_errors(text):
    """Every obligation supports an existing, used acceptance criterion."""
    errors = []
    criteria = re.findall(r'^\| <a id="criterion-(c-\d{2})"></a>`(C-\d{2})` \|', text, re.M)
    declared = {identifier for _, identifier in criteria}
    if not declared or len(declared) != len(criteria):
        errors.append("criteria must be nonempty and unique")
    for anchor, identifier in criteria:
        if anchor != identifier.lower():
            errors.append("criterion anchor does not match ID: " + identifier)
    rows = re.findall(r'^\| `((?:FR|NFR)-[A-Z]+-\d+)` \| (.+)$', text, re.M)
    candidates = re.findall(r'^\| `(?:FR|NFR)-.*$', text, re.M)
    if len(candidates) != len(rows):
        errors.append("requirement rows must use one current, canonical ID")
    seen, used = set(), set()
    if not rows:
        errors.append("product requirements are missing")
    for identifier, cells in rows:
        if identifier in seen:
            errors.append("duplicate requirement ID: " + identifier)
        seen.add(identifier)
        parts = cells.split("|")
        if len(parts) != 3 or not parts[0].strip() or parts[-1].strip():
            errors.append("requirement must have text and criterion columns: " + identifier)
            continue
        links = re.findall(r'\[(C-\d{2})\]\(#criterion-(c-\d{2})\)', parts[1])
        remainder = re.sub(r'\[(C-\d{2})\]\(#criterion-(c-\d{2})\)', '', parts[1])
        if not links or remainder.strip(' ,'):
            errors.append("criterion links are missing or malformed: " + identifier)
        for criterion, anchor in links:
            if criterion not in declared or anchor != criterion.lower():
                errors.append("unknown or mismatched criterion: " + identifier)
            used.add(criterion)
    for criterion in sorted(declared - used):
        errors.append("criterion has no supporting requirements: " + criterion)
    return errors


def acceptance_traceability_errors(product, acceptance):
    """Require explicit owner/procedure coverage; this does not prove test PASS."""
    errors = []
    requirements = set(re.findall(r'^\| `((?:FR|NFR)-[A-Z]+-\d+)` \|', product, re.M))
    criteria = set(re.findall(r'^\| <a id="criterion-c-\d{2}"></a>`(C-\d{2})` \|', product, re.M))
    sections = {}
    for number in (1, 2):
        match = re.search(
            r'<a id="sec-test-plan-25-' + str(number) + r'"></a>(.*?)'
            r'(?=<a id="sec-test-plan-25-' + str(number + 1) + r'"></a>)',
            acceptance, re.S)
        if not match:
            errors.append("missing acceptance traceability section: 25." + str(number))
        sections[number] = match[1] if match else ""
    seen_criteria = set()
    for line in sections[1].splitlines():
        if not line.startswith("| [C-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        match = re.fullmatch(r'\[(C-\d{2})\]\(product-requirements\.md#criterion-(c-\d{2})\)', cells[0])
        if not match or len(cells) != 3:
            errors.append("malformed acceptance criterion row: " + line)
            continue
        identifier = match[1]
        if identifier not in criteria or match[2] != identifier.lower():
            errors.append("unknown or mismatched acceptance criterion: " + identifier)
        if identifier in seen_criteria:
            errors.append("duplicate acceptance criterion: " + identifier)
        seen_criteria.add(identifier)
        if not cells[1] or not re.search(r'\]\(#sec-[^)]+\)', cells[2]):
            errors.append("criterion has no outcome/procedure: " + identifier)
    for identifier in sorted(criteria - seen_criteria):
        errors.append("criterion missing from acceptance matrix: " + identifier)
    seen_requirements = set()
    for line in sections[2].splitlines():
        if not line.startswith("|") or not re.search(r'`(?:FR|NFR)-', line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4:
            errors.append("malformed requirement coverage row: " + line)
            continue
        identifiers = re.findall(r'`((?:FR|NFR)-[A-Z]+-\d+)`', cells[1])
        remainder = re.sub(r'`(?:FR|NFR)-[A-Z]+-\d+`', '', cells[1])
        if not identifiers or remainder.strip(' ,'):
            errors.append("coverage requires explicit canonical IDs: " + cells[1])
        owner_links = re.findall(r'\]\(([a-z0-9-]+\.md)#sec-[^)]+\)', cells[2])
        if (not owner_links or any(owner in ('product-requirements.md', 'test-plan.md')
                                   for owner in owner_links)
                or not re.search(r'\]\(#sec-[^)]+\)', cells[3])):
            errors.append("requirement coverage has no component owner/procedure: " + cells[1])
        for identifier in identifiers:
            if identifier not in requirements:
                errors.append("unknown acceptance requirement ID: " + identifier)
            if identifier in seen_requirements:
                errors.append("duplicate acceptance requirement coverage: " + identifier)
            seen_requirements.add(identifier)
    for identifier in sorted(requirements - seen_requirements):
        errors.append("requirement missing from acceptance matrix: " + identifier)
    return errors


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
    for p in active:
        errors.extend(f"{p.relative_to(ROOT)}: {error}" for error in numbering_errors(norm(p)))
    product = PH / "product-requirements.md"
    if product.is_file():
        errors.extend("product traceability: " + error for error in product_traceability_errors(norm(product)))
        acceptance = PH / "test-plan.md"
        if acceptance.is_file():
            errors.extend("acceptance traceability: " + error
                          for error in acceptance_traceability_errors(norm(product), norm(acceptance)))
        requirement_ids = set(re.findall(r'^\| `((?:FR|NFR)-[A-Z]+-\d+)` \|', norm(product), re.M))
        for path in active:
            unknown = set(re.findall(r'\b(?:FR|NFR)-[A-Z]+-\d+\b', norm(path))) - requirement_ids
            errors.extend("unknown requirement reference in {}: {}".format(path.relative_to(ROOT), identifier)
                          for identifier in sorted(unknown))
    for rel in rels:
        if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.md', Path(rel).name):
            errors.append("specification filename must use lower-kebab-case: " + rel)

    # Проверки generated-файлов
    for script, args in [
        ("tools/protocolgen.py", ["--check", "--include-docs"]),
        ("tools/docindex.py", ["--check"]),
    ]:
        cp = subprocess.run([sys.executable, "-X", "utf8", "-S", str(ROOT/script), *args],
                            cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
        if cp.returncode != 0:
            errors.append((cp.stdout + cp.stderr).strip() or f"проверка {script} завершилась ошибкой")

    # Баланс Markdown fenced blocks и относительные ссылки.
    all_md = list(PH.rglob("*.md"))
    all_md += [ROOT/"AGENTS.md"]
    all_md.extend((ROOT / ".agents" / "skills").rglob("*.md"))
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

    # Current references use a file/anchor, not an ambiguous global section number.
    indexed = {row[0]: row for row in docindex.collect()}
    section_ref_files = list(all_md)
    skills_root = ROOT / ".agents" / "skills"
    if skills_root.is_dir():
        section_ref_files.extend(skills_root.rglob("*.md"))
    seen_section_files = set()
    for p in section_ref_files:
        if not p.is_file():
            continue
        rp = p.resolve()
        if rp in seen_section_files:
            continue
        seen_section_files.add(rp)
        txt = norm(p)
        fenced = False
        for line in txt.splitlines():
            if line.startswith("```"):
                fenced = not fenced
            for link in MD_LINK_RE.finditer(line):
                target = link[1].strip()
                if "#sec-" not in target or target.startswith(("http://", "https://")):
                    continue
                anchor = target.split("#", 1)[1]
                row = indexed.get(anchor)
                if row is None:
                    errors.append(f"неизвестный section anchor в {p.relative_to(ROOT)}: {target}")
                    continue
                label = link[0].split("](", 1)[0]
                for number in SECTION_REF_RE.findall(label):
                    if number != docindex.heading_number(row[3]):
                        errors.append(f"устаревший номер в {p.relative_to(ROOT)}: {link[0]}")
            if not fenced:
                prose = MD_LINK_RE.sub("", line)
                prose = re.sub(r"`[^`]*`", "", prose)
                if SECTION_REF_RE.search(prose):
                    errors.append(f"раздел без Markdown-ссылки в {p.relative_to(ROOT)}: {line}")

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
        "decisions/",
        "risks/",
        "CHANGELOG.md",
    )
    retired_scan = list(all_md)
    if skills_root.is_dir():
        retired_scan.extend(skills_root.rglob("*.md"))
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
    protocol_spec = PH / "protocol-specification.md"
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
