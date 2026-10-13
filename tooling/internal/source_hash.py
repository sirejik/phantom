#!/usr/bin/env python3
"""Hash component source inputs, excluding documentation and interpreter caches."""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXCLUDED_DIRS = {"Library", "Temp", "obj", "__pycache__", "docs", ".git"}
DOCUMENT_SUFFIXES = {".md", ".markdown", ".rst", ".adoc"}
EV3_SOURCE_INPUTS = (
    "ev3/CMakeLists.txt", "ev3/include", "ev3/src", "ev3/safety",
    "protocol", "schemas/shared/protocol", "config/shared/protocol", "tooling/resources/ev3", "ev3/toolchains/armel.cmake", "ev3/docker",
)
QUEST_SOURCE_INPUTS = (
    "PhantomQuest/Assets/Phantom", "PhantomQuest/Assets/Plugins",
    "PhantomQuest/Packages", "PhantomQuest/ProjectSettings", "config/quest/project.json",
)


def source_hash(root, inputs):
    files = set()
    for item in inputs:
        path = root / item
        candidates = [path] if path.is_file() else path.rglob("*")
        for candidate in candidates:
            relative = candidate.relative_to(root)
            if (candidate.is_file() and not EXCLUDED_DIRS.intersection(relative.parts)
                    and candidate.suffix.lower() not in DOCUMENT_SUFFIXES
                    and not any(candidate.name.lower().endswith(suffix + ".meta")
                                for suffix in DOCUMENT_SUFFIXES)
                    and candidate.suffix.lower() not in {".pyc", ".pyo"}):
                files.add(candidate)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments[:1] == ["--component"]:
        if arguments != ["--component", "EV3"]:
            raise SystemExit("supported component: EV3")
        arguments = EV3_SOURCE_INPUTS
    print(source_hash(ROOT, arguments))
