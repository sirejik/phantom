#!/usr/bin/env python3
"""Hash component source inputs, excluding documentation and interpreter caches."""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"Library", "Temp", "obj", "__pycache__", "docs", ".git"}
DOCUMENT_SUFFIXES = {".md", ".markdown", ".rst", ".adoc"}


def source_hash(root, inputs):
    files = set()
    for item in inputs:
        path = root / item
        candidates = [path] if path.is_file() else path.rglob("*")
        for candidate in candidates:
            relative = candidate.relative_to(root)
            if (candidate.is_file() and not EXCLUDED_DIRS.intersection(relative.parts)
                    and candidate.suffix.lower() not in DOCUMENT_SUFFIXES
                    and candidate.suffix.lower() not in {".pyc", ".pyo"}):
                files.add(candidate)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


if __name__ == "__main__":
    print(source_hash(ROOT, sys.argv[1:]))
