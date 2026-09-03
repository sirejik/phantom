#!/usr/bin/env python3
import hashlib,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1];files=[]
for item in sys.argv[1:]:
    path=root/item
    if path.is_file():files.append(path)
    elif path.is_dir():files.extend(p for p in path.rglob("*") if p.is_file() and not any(part in ("Library","Temp","obj") for part in p.parts))
digest=hashlib.sha256()
for path in sorted(set(files),key=lambda value:value.as_posix()):
    relative=path.relative_to(root).as_posix().encode();digest.update(relative+b"\0"+hashlib.sha256(path.read_bytes()).digest())
print(digest.hexdigest())
