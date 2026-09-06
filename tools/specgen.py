#!/usr/bin/env python3
"""Генерация/проверка docs/PHANTOM_SPECIFICATION.md по docs/PHANTOM/spec-set.json."""

from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "docs" / "PHANTOM" / "spec-set.json"
OUTPUT = ROOT / "docs" / "PHANTOM_SPECIFICATION.md"
ALLOWED_CONFIG_KEYS = {"format_version", "normative_files"}

def exact_utf8_lf_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise SystemExit(f"UTF-8 BOM запрещён для normative identity: {path.relative_to(ROOT)}")
    if b"\r" in data:
        raise SystemExit(f"нормативный Markdown должен использовать только LF line endings: {path.relative_to(ROOT)}")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"нормативный Markdown не является valid UTF-8: {path.relative_to(ROOT)}: {exc}")
    return data

def load_config():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if set(cfg) != ALLOWED_CONFIG_KEYS:
        unknown = sorted(set(cfg) - ALLOWED_CONFIG_KEYS)
        missing = sorted(ALLOWED_CONFIG_KEYS - set(cfg))
        raise SystemExit(f"некорректные ключи spec-set: неизвестные={unknown}, отсутствующие={missing}")
    version = cfg["format_version"]
    files = cfg["normative_files"]
    if not isinstance(version, int) or version <= 0:
        raise SystemExit("format_version должен быть положительным целым числом")
    if not isinstance(files, list) or not files or not all(isinstance(x, str) and x for x in files):
        raise SystemExit("normative_files должен быть непустым списком строк")
    return version, files

def validate_relpath(rel: str) -> str:
    if "\\" in rel:
        raise SystemExit(f"нормативный путь должен использовать POSIX-разделители: {rel}")
    pp = PurePosixPath(rel)
    if pp.is_absolute() or ".." in pp.parts or "." in pp.parts:
        raise SystemExit(f"небезопасный или неканонический нормативный путь: {rel}")
    canonical = pp.as_posix()
    if canonical != rel:
        raise SystemExit(f"неканонический нормативный путь: {rel}")
    if not canonical.startswith("docs/PHANTOM/") or not canonical.endswith(".md"):
        raise SystemExit(f"нормативный документ должен быть Markdown-файлом в docs/PHANTOM/: {rel}")
    return canonical

def render() -> bytes:
    version, configured = load_config()
    files = [validate_relpath(x) for x in configured]
    if len(files) != len(set(files)):
        raise SystemExit("normative_files содержит точные дубликаты")
    folded = [x.casefold() for x in files]
    if len(folded) != len(set(folded)):
        raise SystemExit("normative_files содержит дубликаты без учёта регистра")

    rows=[]
    for rel in files:
        path=ROOT/rel
        if not path.is_file():
            raise SystemExit(f"отсутствует нормативный документ: {rel}")
        digest=hashlib.sha256(exact_utf8_lf_bytes(path)).hexdigest()
        rows.append((rel,digest))

    lines=[
        "# PHANTOM — manifest спецификации",
        "",
        "<!-- СГЕНЕРИРОВАНО tools/specgen.py. НЕ РЕДАКТИРОВАТЬ ВРУЧНУЮ. -->",
        "",
        f"format_version: `{version}`",
        "",
        "`specification_sha256` — SHA-256 точных UTF-8/LF bytes этого generated manifest.",
        "Hidden BOM/CRLF normalization перед hashing запрещена; неканоническая форма блокируется gate.",
        "Упорядоченные exact-byte hashes ниже транзитивно связывают полный нормативный набор PHANTOM.",
        "",
        "| нормативный путь | exact-byte SHA-256 |",
        "|---|---|",
    ]
    lines += [f"| `{p}` | `{h}` |" for p,h in rows]
    lines += [
        "",
        "Текущий status, task execution plans, ADRs, risk records, changelog и внешние",
        "технические references намеренно исключены из specification identity.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")

def main():
    ap=argparse.ArgumentParser(description="Генерация или проверка manifest спецификации PHANTOM")
    ap.add_argument("--check",action="store_true")
    args=ap.parse_args()
    expected=render()
    if args.check:
        if not OUTPUT.exists():
            print(f"ОШИБКА: отсутствует {OUTPUT.relative_to(ROOT)}")
            return 1
        actual=OUTPUT.read_bytes()
        if actual != expected:
            print("ОШИБКА: manifest спецификации PHANTOM устарел или имеет неканонические bytes; выполните python tools/specgen.py")
            return 1
        digest=hashlib.sha256(actual).hexdigest()
        print(f"PASS: manifest спецификации актуален: {digest}")
        return 0
    OUTPUT.write_bytes(expected)
    digest=hashlib.sha256(expected).hexdigest()
    print(f"СОЗДАН {OUTPUT.relative_to(ROOT)}")
    print(f"specification_sha256={digest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
