#!/usr/bin/env python3
"""Validate the normative JSON-as-YAML wire/IPC schemas and generate shared artifacts."""
import argparse, hashlib, hmac, json, pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "protocol"))
import jcs  # noqa: E402  single canonicalizer, shared with the ev3dev runtime

SCHEMA_PATH = ROOT / "protocol" / "wire_schema.yaml"
SEMANTICS_PATH = ROOT / "protocol" / "semantics.yaml"
IPC_SCHEMA_PATH = ROOT / "protocol" / "ipc_schema.yaml"
SCALAR = {"u8":1,"i8":1,"u16":2,"i16":2,"u32":4,"i32":4,"u64":8,"f32":4,"id32":32}
STRUCT_CODE = {"u8":"B","i8":"b","u16":"H","i16":"h","u32":"I","i32":"i","u64":"Q","f32":"f"}
CPP_TYPE = {"u8":"std::uint8_t","i8":"std::int8_t","u16":"std::uint16_t","i16":"std::int16_t",
            "u32":"std::uint32_t","i32":"std::int32_t","u64":"std::uint64_t","f32":"float",
            "id32":"char"}

# RFC 8785 conformance fixtures.  They intentionally exercise the two places
# where a naive `json.dumps(sort_keys=True)` diverges from JCS: UTF-16 member
# ordering and ECMAScript number formatting.
JCS_CASES = [
    {"name": "empty_object", "value": {}},
    {"name": "empty_array", "value": []},
    {"name": "literals", "value": {"t": True, "f": False, "n": None}},
    {"name": "small_integers", "value": {"zero": 0, "one": 1, "negative": -1, "max_safe": 9007199254740991}},
    {"name": "integral_floats", "value": [1.0, 2.0, 100.0, -0.0, 1e20]},
    {"name": "fractional", "value": [0.5, 0.1, -1.25, 333333333.33333331]},
    {"name": "exponent_forms", "value": [1e21, 1e-6, 1e-7, 9.999999999999997e22]},
    {"name": "utf16_key_order", "value": {"é": 1, "\U0001f600": 2, "פּ": 3, "a": 4}},
    {"name": "string_escapes", "value": {"s": "line\nquote\"back\\slash\ttab"}},
    {"name": "nested", "value": {"b": [{"y": 1, "x": [1, 2.5, None]}], "a": {"": ""}}},
]


def canonical(obj):
    return jcs.canonicalize(obj)


def load_json(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def type_size(schema, name):
    if name in SCALAR: return SCALAR[name]
    return sum(type_size(schema, field[1]) * (field[2] if len(field)>2 else 1) for field in schema["types"][name])


def field_size(schema, field): return type_size(schema, field[1]) * (field[2] if len(field)>2 else 1)
def field_count(field): return field[2] if len(field)>2 else 1
def title(name): return "".join(x.title() for x in name.lower().split("_"))


def offsets(schema, message):
    """Return [(name, kind, count, offset, size)] for one message."""
    result, offset = [], 0
    for field in message["fields"]:
        size = field_size(schema, field)
        result.append((field[0], field[1], field_count(field), offset, size))
        offset += size
    return result


def validate(schema):
    assert schema["header_bytes"] == 64 and schema["hmac_bytes"] == 32
    seen=set()
    for message in schema["messages"]:
        assert message["type"] not in seen, message["type"]
        seen.add(message["type"])
        actual=sum(field_size(schema, field) for field in message["fields"])
        assert actual == message["length"], "%s: schema=%d computed=%d"%(message["name"],message["length"],actual)
        assert 64+actual+32 <= schema["max_datagram_bytes"]
    for name, bits in schema["bitfields"].items():
        positions = sorted(bits.values())
        assert positions == list(range(len(positions))), "%s: bit positions must be dense from 0"%name
        assert positions[-1] < 32, "%s: bit position exceeds u32"%name


def structural_projection(schema):
    """Return only values that determine the binary wire structure."""
    def kind(name):
        return name if name in SCALAR else [kind(item[1]) for item in schema["types"][name]]
    field = lambda item: [kind(item[1]), field_count(item)]
    return {
        "schema_version": schema["schema_version"], "protocol_version": schema["protocol_version"],
        "protocol_minor": schema["protocol_minor"], "magic_ascii": schema["magic_ascii"],
        "endianness": schema["endianness"], "float_format": schema["float_format"],
        "header_bytes": schema["header_bytes"], "hmac_bytes": schema["hmac_bytes"],
        "max_datagram_bytes": schema["max_datagram_bytes"],
        # Symbol-to-number mappings are structural: swapping two enum values or
        # bit positions changes the bytes interpreted by independently built
        # peers even when the unordered set of numbers stays the same.
        "enums": schema["enums"],
        "bitfields": schema["bitfields"],
        "messages": [{"type": item["type"], "length": item["length"],
                      "fields": [field(value) for value in item["fields"]]}
                     for item in schema["messages"]],
    }


def validate_semantics(semantics, schema):
    assert semantics["schema_version"] == 1
    assert semantics["protocol_version"] == schema["protocol_version"]
    assert semantics["admission"]["compatibility_identity"] == "protocol_contract_hash"
    assert semantics["authentication"]["minimum_key_bytes"] >= 32
    assert semantics["authority"]["ev3_is_authoritative"] is True
    assert semantics["authority"]["quest_sends_intent_not_pwm"] is True


def validate_ipc(schema):
    assert schema["ipc_version"] == 1 and schema["magic_ascii"] == "PHIP"
    seen=set()
    for message in schema["messages"]:
        assert message["name"] not in seen, message["name"]
        seen.add(message["name"])
        actual=sum(SCALAR[f[1]]*field_count(f) for f in message["fields"])
        assert actual == message["length"], "%s: schema=%d computed=%d"%(message["name"],message["length"],actual)
        assert message["direction"] in ("network_to_controller","controller_to_network")
        assert message["fields"][0][0] == "magic" and message["fields"][0][2] == 4


def struct_format(message):
    parts=["<"]
    for field in message["fields"]:
        kind, count = field[1], field_count(field)
        if kind == "u8" and count > 1: parts.append("%ds"%count)
        elif count > 1: parts.append("%d%s"%(count, STRUCT_CODE[kind]))
        else: parts.append(STRUCT_CODE[kind])
    return "".join(parts)


def default_bytes(schema, field, ordinal):
    name, kind = field[0], field[1]; count=field_count(field)
    if kind=="id32":
        value=("phantom01" if "robot_id" in name else ("EMPTY" if "profile" in name else "build-test")).encode()
        return value+b"\0"*(32-len(value))
    if kind in schema["types"]:
        out=b""
        for _ in range(count):
            for nested in schema["types"][kind]: out+=default_bytes(schema,nested,ordinal)
        return out
    if kind=="f32":
        values=[0.5]*count if name in ("grip_intent","grip_actual") else [0.125*(ordinal+i+1) for i in range(count)]
        return b"".join(struct.pack("<f", value) for value in values)
    fmt={"u8":"B","i8":"b","u16":"H","i16":"h","u32":"I","i32":"i","u64":"Q"}[kind]
    # Reserved fields and bitfields default to zero. IDs get deterministic non-zero values.
    zeroed=name.startswith("reserved") or "flags" in name or name in ("protocol_minor","state","fault_code","result_code","build_profile","payload_state","key_slot","accepted_key_slot","session_role","accepted_role","axis","direction","signed_direction","measurement_kind","stop_reason","grip_state","gripper_capabilities")
    value=0 if zeroed else ordinal+1
    return b"".join(struct.pack("<"+fmt,value if zeroed else value+i) for i in range(count))


def packet(schema, message, payload, key):
    session=b"\0"*16 if message["name"]=="HELLO" else bytes(range(16,32))
    boot=bytes(range(32,48)); seq=0 if message["name"] in ("HELLO","HELLO_ACK") else 1
    header=struct.pack("<4sHHHHI16s16sQQ",b"PHNT",1,message["type"],64,len(payload),0,session,boot,seq,123456789)
    return header+payload+hmac.new(key,header+payload,hashlib.sha256).digest()


def ipc_default_bytes(field, ordinal):
    name, kind, count = field[0], field[1], field_count(field)
    if name == "magic": return b"PHIP"
    if kind == "u8" and count > 1:
        if name.startswith("reserved"): return b"\0"*count
        return bytes(((ordinal*7+i+1) & 0xff) for i in range(count))
    if kind == "f32":
        return b"".join(struct.pack("<f", 0.25*(ordinal+i+1)) for i in range(count))
    zeroed = name.startswith("reserved")
    value = 0 if zeroed else (ordinal+1)
    return b"".join(struct.pack("<"+STRUCT_CODE[kind], value) for _ in range(count))


def render_protocol_md(schema, ipc, schema_digest, semantics_digest, contract_digest, ipc_digest):
    lines = [
        "# PHANTOM protocol v1 — generated wire mirror",
        "",
        "<!-- Generated by tools/protocolgen.py. DO NOT EDIT. -->",
        "",
        "`protocol/wire_schema.yaml` is the normative machine-readable source for the",
        "Quest<->EV3 datagram structure; `protocol/ipc_schema.yaml` is the normative source",
        "for the EV3-local `phantom-network` <-> `phantom-controller` boundary. This file is a",
        "derived human-readable mirror and never a competing source of truth.",
        "",
        "| identity | value |",
        "|---|---|",
        "| `protocol_schema_hash` | `%s` |" % schema_digest,
        "| `protocol_semantics_hash` | `%s` |" % semantics_digest,
        "| `protocol_contract_hash` | `%s` |" % contract_digest,
        "| `ipc_schema_hash` | `%s` |" % ipc_digest,
        "| protocol version | %d.%d |" % (schema["protocol_version"], schema["protocol_minor"]),
        "| endianness | %s |" % schema["endianness"],
        "| float format | %s |" % schema["float_format"],
        "| header / HMAC / max datagram | %d / %d / %d bytes |" % (
            schema["header_bytes"], schema["hmac_bytes"], schema["max_datagram_bytes"]),
        "",
        "Every datagram is `header(%d) || payload(exact per type) || HMAC-SHA-256(%d)`." % (
            schema["header_bytes"], schema["hmac_bytes"]),
        "",
        "## Enumerations",
        "",
    ]
    for enum_name, values in schema["enums"].items():
        lines += ["### `%s`" % enum_name, "", "| name | value |", "|---|---|"]
        lines += ["| `%s` | %d |" % (name, value) for name, value in values.items()]
        lines.append("")
    lines += ["## Bitfields", ""]
    for field_name, values in schema["bitfields"].items():
        lines += ["### `%s`" % field_name, "", "| bit | mask | name |", "|---|---|---|"]
        lines += ["| %d | `0x%08X` | `%s` |" % (bit, 1 << bit, name) for name, bit in values.items()]
        lines.append("")
    lines += ["## Composite types", ""]
    for type_name, fields in schema["types"].items():
        lines += ["### `%s` — %d bytes" % (type_name, type_size(schema, type_name)), "",
                  "| offset | field | type |", "|---|---|---|"]
        offset = 0
        for field in fields:
            lines.append("| %d | `%s` | `%s` |" % (offset, field[0], field[1]))
            offset += field_size(schema, field)
        lines.append("")
    lines += ["## Messages", "", "| message | type | payload bytes | total datagram |", "|---|---|---|---|"]
    for message in schema["messages"]:
        lines.append("| `%s` | `0x%04X` | %d | %d |" % (
            message["name"], message["type"], message["length"],
            schema["header_bytes"] + message["length"] + schema["hmac_bytes"]))
    lines.append("")
    for message in schema["messages"]:
        lines += ["### `%s` (`0x%04X`) — %d payload bytes" % (message["name"], message["type"], message["length"]),
                  "", "| offset | size | field | type | count |", "|---|---|---|---|---|"]
        for name, kind, count, offset, size in offsets(schema, message):
            lines.append("| %d | %d | `%s` | `%s` | %d |" % (offset, size, name, kind, count))
        lines.append("")
    lines += ["## EV3-local IPC (`phantom-network` <-> `phantom-controller`)", "",
              "Magic `%s`, `ipc_version=%d`, little-endian, fixed length, canonical-zero reserved bytes." % (
                  ipc["magic_ascii"], ipc["ipc_version"]),
              "", "| message type | value |", "|---|---|"]
    lines += ["| `%s` | %d |" % (name, value) for name, value in ipc["message_types"].items()]
    lines.append("")
    for message in ipc["messages"]:
        lines += ["### `%s` — %d bytes (%s)" % (
            message["name"], message["length"], message["direction"].replace("_", " ")),
            "", "| offset | size | field | type | count |", "|---|---|---|---|---|"]
        offset = 0
        for field in message["fields"]:
            count = field_count(field)
            size = SCALAR[field[1]] * count
            lines.append("| %d | %d | `%s` | `%s` | %d |" % (offset, size, field[0], field[1], count))
            offset += size
        lines.append("")
    return "\n".join(lines)


def render_cpp(schema, schema_digest, semantics_digest, contract_digest):
    lines=["// Generated by tools/protocolgen.py. DO NOT EDIT.","#pragma once","#include <cstddef>","#include <cstdint>","namespace phantom { namespace wire {",'constexpr const char* kProtocolSchemaSha256 = "%s";'%schema_digest,'constexpr const char* kProtocolSemanticsSha256 = "%s";'%semantics_digest,'constexpr const char* kProtocolContractSha256 = "%s";'%contract_digest,"constexpr std::size_t kHeaderBytes=64, kHmacBytes=32, kMaxDatagramBytes=1024;","enum class MessageType : std::uint16_t {"]
    lines += ["  %s = 0x%04X,"%(m["name"],m["type"]) for m in schema["messages"]]
    lines += ["};"]
    for enum_name,values in schema["enums"].items():
        lines.append("enum class %s : std::uint16_t {"%enum_name)
        lines += ["  %s = %d,"%(name,value) for name,value in values.items()]
        lines.append("};")
    for field_name,values in schema["bitfields"].items():
        for name,bit in values.items():lines.append("constexpr std::uint32_t k%s%s = (std::uint32_t(1) << %d);"%(title(field_name),title(name),bit))
    for field_name,values in schema["bitfields"].items():
        mask=0
        for bit in values.values(): mask |= 1 << bit
        lines.append("constexpr std::uint32_t k%sMask = 0x%08Xu;"%(title(field_name),mask))
    for m in schema["messages"]: lines.append("constexpr std::size_t k%sPayloadBytes = %d;"%("".join(x.title() for x in m["name"].lower().split("_")),m["length"]))
    lines += ["constexpr std::size_t PayloadBytes(MessageType type) {","  switch(type) {"]
    lines += ["    case MessageType::%s: return %d;"%(m["name"],m["length"]) for m in schema["messages"]]
    lines += ["  } return 0;","}"]
    lines += ["static_assert(kHeaderBytes+kHmacBytes+436<=kMaxDatagramBytes, \"largest v1 packet must fit\");","} } // namespace phantom::wire",""]
    return "\n".join(lines)


def render_ipc_cpp(ipc, digest):
    lines=["// Generated by tools/protocolgen.py. DO NOT EDIT.","#pragma once","#include <cstddef>","#include <cstdint>",
           "namespace phantom { namespace ipc {",
           'constexpr const char* kIpcSchemaSha256 = "%s";'%digest,
           "constexpr std::uint32_t kMagic = 0x%08Xu; // \"%s\" little-endian"%(
               int.from_bytes(ipc["magic_ascii"].encode("ascii"), "little"), ipc["magic_ascii"]),
           "constexpr std::uint16_t kIpcVersion = %d;"%ipc["ipc_version"]]
    lines.append("enum class MessageType : std::uint16_t {")
    lines += ["  %s = %d,"%(name,value) for name,value in ipc["message_types"].items()]
    lines.append("};")
    for message in ipc["messages"]:
        prefix = "k" + message["name"].replace("V1", "")
        lines.append("constexpr std::size_t %sBytes = %d;"%(prefix, message["length"]))
        offset = 0
        for field in message["fields"]:
            count = field_count(field)
            size = SCALAR[field[1]] * count
            lines.append("constexpr std::size_t %sOffset%s = %d;"%(prefix, title(field[0]), offset))
            lines.append("constexpr std::size_t %sSize%s = %d;"%(prefix, title(field[0]), size))
            offset += size
    lines += ["} } // namespace phantom::ipc",""]
    return "\n".join(lines)


def render_ipc_python(ipc, digest):
    lines=['"""Generated by tools/protocolgen.py. DO NOT EDIT."""','import struct','',
           'IPC_SCHEMA_SHA256 = "%s"'%digest,
           'MAGIC = b"%s"'%ipc["magic_ascii"],
           'IPC_VERSION = %d'%ipc["ipc_version"],'']
    lines.append("MESSAGE_TYPES = {")
    lines += ['    "%s": %d,'%(name,value) for name,value in ipc["message_types"].items()]
    lines += ["}",""]
    for message in ipc["messages"]:
        name = message["name"].replace("V1", "").upper()
        # Split "ControllerRequest" style names into SCREAMING_SNAKE for readability.
        snake = []
        for index, char in enumerate(message["name"].replace("V1", "")):
            if char.isupper() and index: snake.append("_")
            snake.append(char.upper())
        name = "".join(snake)
        lines.append('%s = struct.Struct("%s")'%(name, struct_format(message)))
        lines.append('%s_BYTES = %d'%(name, message["length"]))
        lines.append('%s_FIELDS = (%s)'%(name, "".join('"%s", '%f[0] for f in message["fields"])))
        offset = 0
        entries = []
        for field in message["fields"]:
            entries.append('"%s": %d'%(field[0], offset))
            offset += SCALAR[field[1]] * field_count(field)
        lines.append('%s_OFFSETS = {%s}'%(name, ", ".join(entries)))
        lines.append("")
    return "\n".join(lines)


def render_cs(schema, schema_digest, semantics_digest, contract_digest):
    lines=["// Generated by tools/protocolgen.py. DO NOT EDIT.","namespace Phantom.Networking.Generated","{","    public static class WireV1","    {",f'        public const string ProtocolSchemaSha256 = "{schema_digest}";',f'        public const string ProtocolSemanticsSha256 = "{semantics_digest}";',f'        public const string ProtocolContractSha256 = "{contract_digest}";',"        public const int HeaderBytes=64, HmacBytes=32, MaxDatagramBytes=1024;","        public enum MessageType : ushort","        {"]
    lines += ["            %s = 0x%04X,"%("".join(x.title() for x in m["name"].lower().split("_")),m["type"]) for m in schema["messages"]]
    lines += ["        }"]
    for enum_name,values in schema["enums"].items():
        lines.append("        public enum %s : ushort"%enum_name);lines.append("        {")
        lines += ["            %s = %d,"%(title(name),value) for name,value in values.items()]
        lines.append("        }")
    for field_name,values in schema["bitfields"].items():
        for name,bit in values.items():lines.append("        public const uint %s%s = 1u << %d;"%(title(field_name),title(name),bit))
    for field_name,values in schema["bitfields"].items():
        mask=0
        for bit in values.values(): mask |= 1 << bit
        lines.append("        public const uint %sMask = 0x%08Xu;"%(title(field_name),mask))
    for m in schema["messages"]: lines.append("        public const int %sPayloadBytes = %d;"%("".join(x.title() for x in m["name"].lower().split("_")),m["length"]))
    for m in schema["messages"]:
        for name,kind,count,offset,size in offsets(schema,m):
            lines.append("        public const int %sOffset%s = %d;"%("".join(x.title() for x in m["name"].lower().split("_")),title(name),offset))
    lines += ["        public static int PayloadBytes(MessageType type)","        {","            switch(type)","            {"]
    lines += ["                case MessageType.%s: return %d;"%("".join(x.title() for x in m["name"].lower().split("_")),m["length"]) for m in schema["messages"]]
    lines += ["                default: return -1;","            }","        }"]
    lines += ["    }","}",""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true")
    parser.add_argument("--include-docs",action="store_true",help="also check generated Markdown (documentation gate only)")
    args=parser.parse_args()
    schema=load_json(SCHEMA_PATH); validate(schema)
    semantics=load_json(SEMANTICS_PATH);validate_semantics(semantics,schema)
    structure=structural_projection(schema)
    digest=hashlib.sha256(canonical(structure)).hexdigest()
    semantics_digest=hashlib.sha256(canonical(semantics)).hexdigest()
    contract={"protocol_schema_hash":digest,"protocol_semantics_hash":semantics_digest}
    contract_digest=hashlib.sha256(canonical(contract)).hexdigest()
    ipc=load_json(IPC_SCHEMA_PATH); validate_ipc(ipc); ipc_digest=hashlib.sha256(canonical(ipc)).hexdigest()

    key=bytes(range(32)); vectors=[]
    for ordinal,message in enumerate(schema["messages"]):
        payload=b"".join(default_bytes(schema,f,ordinal) for f in message["fields"])
        encoded=packet(schema,message,payload,key)
        vectors.append({"name":message["name"],"message_type":message["type"],"payload_length":len(payload),"hmac_key_hex":key.hex(),"datagram_hex":encoded.hex(),"datagram_sha256":hashlib.sha256(encoded).hexdigest()})

    ipc_vectors=[]
    for ordinal,message in enumerate(ipc["messages"]):
        encoded=b"";fields=[];offset=0
        for field in message["fields"]:
            chunk=ipc_default_bytes(field,ordinal)
            size=SCALAR[field[1]]*field_count(field)
            assert len(chunk)==size,(message["name"],field[0])
            # Per-field bytes at the generated offset: this is what lets the C++
            # and Python sides prove they agree on the layout, not just the size.
            fields.append({"name":field[0],"offset":offset,"size":size,"hex":chunk.hex()})
            encoded+=chunk;offset+=size
        assert len(encoded)==message["length"]
        ipc_vectors.append({"name":message["name"],"direction":message["direction"],"length":message["length"],
                            "bytes_hex":encoded.hex(),"sha256":hashlib.sha256(encoded).hexdigest(),"fields":fields})

    jcs_vectors=[]
    for case in JCS_CASES:
        encoded=jcs.canonicalize(case["value"])
        jcs_vectors.append({"name":case["name"],"input_json":json.dumps(case["value"],ensure_ascii=False),
                            "canonical_utf8_hex":encoded.hex(),"sha256":hashlib.sha256(encoded).hexdigest()})

    outputs={
      ROOT/"protocol"/"generated"/"wire_schema.canonical.json":canonical(schema).decode("utf-8")+"\n",
      ROOT/"protocol"/"generated"/"wire_schema.structural.json":canonical(structure).decode("utf-8")+"\n",
      ROOT/"protocol"/"generated"/"protocol_semantics.canonical.json":canonical(semantics).decode("utf-8")+"\n",
      ROOT/"protocol"/"generated"/"protocol_contract.canonical.json":canonical(contract).decode("utf-8")+"\n",
      ROOT/"protocol"/"generated"/"ipc_schema.canonical.json":canonical(ipc).decode("utf-8")+"\n",
      ROOT/"protocol"/"generated"/"protocol_constants.hpp":render_cpp(schema,digest,semantics_digest,contract_digest),
      ROOT/"protocol"/"generated"/"ipc_constants.hpp":render_ipc_cpp(ipc,ipc_digest),
      ROOT/"protocol"/"generated"/"ipc_layout.py":render_ipc_python(ipc,ipc_digest),
      ROOT/"PhantomQuest"/"Assets"/"Phantom"/"Networking"/"GeneratedProtocol.g.cs":render_cs(schema,digest,semantics_digest,contract_digest),
      ROOT/"protocol"/"golden_vectors"/"v1.json":json.dumps({"protocol_schema_sha256":digest,"protocol_semantics_sha256":semantics_digest,"protocol_contract_sha256":contract_digest,"vectors":vectors},indent=2)+"\n",
      ROOT/"protocol"/"golden_vectors"/"ipc_v1.json":json.dumps({"ipc_schema_sha256":ipc_digest,"vectors":ipc_vectors},indent=2)+"\n",
      ROOT/"protocol"/"golden_vectors"/"jcs_v1.json":json.dumps({"specification":"RFC 8785","vectors":jcs_vectors},indent=2,ensure_ascii=False)+"\n",
      ROOT/"docs"/"protocol-wire-reference.md":render_protocol_md(schema,ipc,digest,semantics_digest,contract_digest,ipc_digest)+"\n",
      # Kept single-line: PowerShell build scripts read it as one string.
      ROOT/"protocol"/"generated"/"schema.sha256":digest+"  wire_schema.yaml\n",
      ROOT/"protocol"/"generated"/"semantics.sha256":semantics_digest+"  semantics.yaml\n",
      ROOT/"protocol"/"generated"/"contract.sha256":contract_digest+"  protocol_contract.canonical.json\n",
      ROOT/"protocol"/"generated"/"ipc_schema.sha256":ipc_digest+"  ipc_schema.yaml\n",
    }
    for path,data in outputs.items():
        if args.check:
            if path.suffix == ".md" and not args.include_docs:
                continue
            if not path.exists() or path.read_text(encoding="utf-8")!=data: raise SystemExit("generated protocol artifact stale: "+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("w",encoding="utf-8",newline="\n") as stream: stream.write(data)
    print("protocol contract ok: %d wire messages schema=%s semantics=%s contract=%s; %d IPC messages sha256=%s"%(
        len(schema["messages"]),digest,semantics_digest,contract_digest,len(ipc["messages"]),ipc_digest))

if __name__=="__main__": main()
