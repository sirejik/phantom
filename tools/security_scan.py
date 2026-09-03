#!/usr/bin/env python3
import pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
tracked=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=str(ROOT),text=True,encoding="utf-8").splitlines()
bad=[];patterns=[re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),re.compile(rb"(?i)(?:control|commissioning)[_-]?(?:psk|secret)\s*[:=]\s*['\"]?[0-9a-f]{64}")]
for rel in tracked:
 if rel.startswith((".secrets/","protocol/golden_vectors/")) or "/test" in rel.lower():continue
 path=ROOT/rel
 try:data=path.read_bytes()
 except OSError:continue
 if any(p.search(data) for p in patterns):bad.append(rel)
if bad:print("possible secrets: "+", ".join(bad));sys.exit(1)
print("secret scan PASS: %d tracked/untracked repository files"%len(tracked))
