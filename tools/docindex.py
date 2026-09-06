#!/usr/bin/env python3
"""Генерация/проверка/поиск стабильных ссылок на разделы PHANTOM."""

from pathlib import Path
import argparse
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PH = ROOT / "docs" / "PHANTOM"
SPEC_SET = PH / "spec-set.json"
SUPPORTING = [PH / "REFERENCES.md"]  # владеет навигацией legacy §11.5, но не является нормативным
OUTPUT = PH / "SECTION_INDEX.md"

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

def sec_key(anchor):
    parts = anchor[len("sec-") :] if anchor.startswith("sec-") else anchor
    parts = parts.split("-")
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]

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
    rows.sort(key=lambda r: sec_key(r[0]))
    return rows

def render(rows) -> str:
    lines = [
        "# Индекс разделов PHANTOM",
        "",
        "<!-- СГЕНЕРИРОВАНО tools/docindex.py. НЕ РЕДАКТИРОВАТЬ ВРУЧНУЮ. -->",
        "",
        "Стабильные legacy-номера разделов сохраняются после разбиения документации.",
        "Используйте этот индекс или `python tools/docindex.py --locate <section>`, чтобы",
        "найти `§x.y` без загрузки всех документов PHANTOM.",
        "",
        "| Раздел | Текущий документ | Заголовок |",
        "|---|---|---|",
    ]
    for anchor, sec, rel, heading, _ in rows:
        display = path_rel = Path(rel).relative_to("docs/PHANTOM").as_posix()
        lines.append(f"| `{sec}` | [`{display}`]({path_rel}#{anchor}) | {heading} |")
    lines.append("")
    return "\n".join(lines)

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
    ap = argparse.ArgumentParser(description="Индекс разделов PHANTOM")
    ap.add_argument("--check", action="store_true", help="проверить актуальность индекса")
    ap.add_argument("--locate", metavar="РАЗДЕЛ", help="найти раздел, например 7.16 или §10.5")
    args = ap.parse_args()

    if args.check and args.locate:
        raise SystemExit("--check и --locate нельзя использовать одновременно")

    rows = collect()

    if args.locate:
        wanted = normalize_lookup(args.locate)
        for anchor, sec, rel, heading, line in rows:
            if anchor == wanted:
                print(f"{sec}\t{rel}:{line}\t{anchor}\t{heading}")
                return 0
        print(f"НЕ_НАЙДЕН\t{args.locate}")
        return 2

    expected = render(rows)
    if args.check:
        if not OUTPUT.exists():
            print("ОШИБКА: SECTION_INDEX.md отсутствует")
            return 1
        actual = OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if actual != expected:
            print("ОШИБКА: SECTION_INDEX.md устарел; выполните python tools/docindex.py")
            return 1
        print("PASS: SECTION_INDEX.md актуален")
        return 0

    with OUTPUT.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(expected)
    print(f"СОЗДАН {OUTPUT.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
