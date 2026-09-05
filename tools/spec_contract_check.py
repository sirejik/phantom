#!/usr/bin/env python3
"""Check the normative wire-layout mirror and canonical source hashes."""
import hashlib,json,pathlib,re,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=ROOT/"docs/PHANTOM_SPECIFICATION.md"
SCHEMA=ROOT/"protocol/wire_schema.yaml"

def fail(message):
    print("spec contract FAIL: "+message,file=sys.stderr);raise SystemExit(1)

def field_shape(field):
    name,kind=field[0],field[1];count=field[2] if len(field)>2 else 1
    return name,kind,count

def parsed_field(line):
    line=line.split("#",1)[0].strip()
    if not line:return None
    match=re.match(r"(id32|u8|i8|u16|i16|u32|i32|u64|f32|AxisCalibration|CurveNode)(?:\[(\d+)\])?\s+(\w+)(?:\[(\d+)\])?$",line)
    if not match:return None
    kind,type_count,name,name_count=match.groups();count=int(type_count or name_count or 1)
    return name,kind,count

def main():
    raw=SPEC.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):fail("specification has UTF-8 BOM")
    if b"\r" in raw:fail("specification must use LF line endings")
    try:text=raw.decode("utf-8")
    except UnicodeDecodeError:fail("specification is not UTF-8")
    schema=json.loads(SCHEMA.read_text(encoding="utf-8"))
    canonical=json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    generated=(ROOT/"protocol/generated/wire_schema.canonical.json").read_bytes()
    if generated!=canonical+b"\n":fail("canonical schema artifact is stale")
    digest=hashlib.sha256(canonical).hexdigest()
    recorded=(ROOT/"protocol/generated/schema.sha256").read_text(encoding="ascii").split()[0]
    if digest!=recorded:fail("protocol schema hash does not cover canonical JSON")
    pattern=re.compile(r"^0x([0-9A-Fa-f]{4})\s+(\w+)\s+—\s+(\d+) bytes\n((?:  .+\n)+)",re.MULTILINE)
    mirrors={}
    for match in pattern.finditer(text):
        fields=[parsed_field(line) for line in match.group(4).splitlines()]
        fields=[value for value in fields if value is not None]
        mirrors[match.group(2)]=(int(match.group(1),16),int(match.group(3)),fields)
    for message in schema["messages"]:
        if message["name"] not in mirrors:fail("§11.8 layout missing "+message["name"])
        message_type,length,fields=mirrors[message["name"]]
        if message_type!=message["type"] or length!=message["length"]:fail("§11.8 type/length mismatch "+message["name"])
        expected=[field_shape(field) for field in message["fields"]]
        if fields!=expected:fail("§11.8 fields mismatch %s: %r != %r"%(message["name"],fields,expected))
    if len(mirrors)!=len(schema["messages"]):fail("§11.8 contains unknown/duplicate layouts")
    print("spec contract PASS: UTF-8/LF, 21 wire layouts, canonical schema/hash")

if __name__=="__main__":main()
