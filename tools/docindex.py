#!/usr/bin/env python3
"""Локальные оглавления и поиск стабильных ссылок на разделы PHANTOM."""

from pathlib import Path
import argparse
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PH = ROOT / "docs"
SPEC_SET = PH / "spec-set.json"
SUPPORTING = [PH / "references.md"]  # владеет навигацией legacy §11.5, но не является нормативным
TOC_RE = re.compile(r'<!-- BEGIN GENERATED TOC -->.*?<!-- END GENERATED TOC -->\n*', re.S)

ANCHOR_RE = re.compile(r'<a id="(sec-[^"]+)"></a>')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')

def active_files():
    cfg = json.loads(SPEC_SET.read_text(encoding="utf-8"))
    files = [ROOT / p for p in cfg["normative_files"]]
    files.extend(p for p in SUPPORTING if p.exists())
    return files

def sections(path: Path):
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    result = []
    for i, line in enumerate(lines):
        m = ANCHOR_RE.search(line)
        if not m:
            continue
        anchor = m.group(1)
        heading = None
        heading_line = None
        for j in range(i + 1, min(i + 8, len(lines))):
            hm = HEADING_RE.match(lines[j])
            if hm:
                heading = hm.group(2)
                heading_line = j + 1
                break
            if lines[j].strip() and not lines[j].startswith("<"):
                break
        if heading is None:
            raise SystemExit(
                f"у section anchor {anchor} в {path.relative_to(ROOT)} нет ближайшего heading"
            )
        result.append((anchor, heading, heading_line))
    return result


def collect():
    rows = []
    seen = {}
    for path in active_files():
        rel = path.relative_to(ROOT).as_posix()
        for anchor, heading, heading_line in sections(path):
            if anchor in seen:
                raise SystemExit(f"дублирующий section anchor {anchor}: {seen[anchor]} и {rel}")
            seen[anchor] = rel
            section_id = anchor[len("sec-") :] if anchor.startswith("sec-") else anchor
            sec = "§" + section_id.replace("-", ".")
            rows.append((anchor, sec, rel, heading, heading_line))
    return rows

def heading_number(heading):
    match = re.match(r"^(\d+(?:\.\d+)*)\.\s", heading)
    return match.group(1) if match else None


def document_toc(rows, rel):
    lines = ["<!-- BEGIN GENERATED TOC -->", "<details>", "<summary>Оглавление</summary>", ""]
    seen = set()
    for anchor, _, path, heading, _ in rows:
        number = heading_number(heading)
        if path != rel or number is None or heading in seen:
            continue
        seen.add(heading)
        lines.append("  " * number.count(".") + f"- [{heading}](#{anchor})")
    lines.extend(["", "</details>", "<!-- END GENERATED TOC -->", "", ""])
    return "\n".join(lines)


def with_document_toc(text, toc):
    text = TOC_RE.sub("", text)
    first_section = re.search(r'(?:<a id="sec-[^\"]+"></a>\n)+## ', text)
    if first_section is None:
        raise ValueError("document has no anchored section")
    return text[:first_section.start()] + toc + text[first_section.start():]


def locate(rows, value, document=None):
    if document:
        # A document is required to disambiguate the independently numbered specs.
        number = value.strip().lstrip("§").strip()
        matches = {}
        for row in rows:
            if Path(row[2]).name == document and heading_number(row[3]) == number:
                matches.setdefault((row[2], row[4]), row)
        return list(matches.values())
    wanted = normalize_lookup(value)
    return [row for row in rows if row[0] == wanted]

def normalize_lookup(value: str) -> str:
    value = value.strip()
    if value.startswith("§"):
        value = value[1:]
    value = value.strip()
    if value.startswith("sec-"):
        return value
    if not re.fullmatch(r"\d+(?:\.\d+)*", value):
        raise SystemExit(f"некорректный номер раздела: {value!r}")
    return "sec-" + value.replace(".", "-")

def main() -> int:
    ap = argparse.ArgumentParser(description="Оглавления и поиск разделов PHANTOM")
    ap.add_argument("--check", action="store_true", help="проверить актуальность локальных оглавлений")
    ap.add_argument("--locate", metavar="РАЗДЕЛ", help="локальный номер с --document; иначе legacy identifier")
    ap.add_argument("--document", metavar="ФАЙЛ", help="искать локальный номер в указанном документе")
    args = ap.parse_args()

    if args.check and args.locate:
        raise SystemExit("--check и --locate нельзя использовать одновременно")
    if args.document and not args.locate:
        raise SystemExit("--document требует --locate")

    rows = collect()

    if args.locate:
        matches = locate(rows, args.locate, args.document)
        if matches:
            for anchor, sec, rel, heading, line in matches:
                label = "§" + heading_number(heading) if args.document else sec
                print(f"{label}\t{rel}:{line}\t{anchor}\t{heading}")
            return 0
        print(f"НЕ_НАЙДЕН\t{args.locate}")
        return 2

    stale = []
    for path in active_files():
        actual = path.read_text(encoding="utf-8")
        expected = with_document_toc(actual, document_toc(rows, path.relative_to(ROOT).as_posix()))
        if actual != expected:
            stale.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_bytes(expected.encode("utf-8"))
    if args.check and stale:
        print("ОШИБКА: оглавления устарели: " + ", ".join(stale))
        return 1
    print("PASS: локальные оглавления актуальны" if args.check else "ОБНОВЛЕНО оглавлений: " + str(len(stale)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
