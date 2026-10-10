"""Strict bounded reference codec for PHANTOM protocol v1."""
import hashlib, hmac, json, math, pathlib, struct
import jcs

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA=json.loads((ROOT.parent/"config/shared/protocol/wire-schema.json").read_text(encoding="utf-8"))
SEMANTICS=json.loads((ROOT.parent/"config/shared/protocol/semantics.json").read_text(encoding="utf-8"))
MESSAGES={m["type"]:m for m in SCHEMA["messages"]}; NAMES={m["name"]:m for m in SCHEMA["messages"]}
HEADER=struct.Struct("<4sHHHHI16s16sQQ")
HEADER_BYTES=64; HMAC_BYTES=32; MAX_DATAGRAM_BYTES=1024; MAX_PAYLOAD_BYTES=928; ZERO_ID=b"\0"*16

class ProtocolError(ValueError): pass

def _kind_shape(name): return name if name in ("u8","i8","u16","i16","u32","i32","u64","f32","id32") else [_kind_shape(item[1]) for item in SCHEMA["types"][name]]
def _field_shape(field): return [_kind_shape(field[1]),field[2] if len(field)>2 else 1]
def structural_projection():
    return {"schema_version":SCHEMA["schema_version"],"protocol_version":SCHEMA["protocol_version"],
            "protocol_minor":SCHEMA["protocol_minor"],"magic_ascii":SCHEMA["magic_ascii"],
            "endianness":SCHEMA["endianness"],"float_format":SCHEMA["float_format"],
            "header_bytes":SCHEMA["header_bytes"],"hmac_bytes":SCHEMA["hmac_bytes"],
            "max_datagram_bytes":SCHEMA["max_datagram_bytes"],
            "enums":SCHEMA["enums"],"bitfields":SCHEMA["bitfields"],
            "messages":[{"type":item["type"],"length":item["length"],"fields":[_field_shape(value) for value in item["fields"]]} for item in SCHEMA["messages"]]}
def schema_hash(): return hashlib.sha256(jcs.canonicalize(structural_projection())).digest()
def semantics_hash(): return hashlib.sha256(jcs.canonicalize(SEMANTICS)).digest()
def contract_hash():
    value={"protocol_schema_hash":schema_hash().hex(),"protocol_semantics_hash":semantics_hash().hex()}
    return hashlib.sha256(jcs.canonicalize(value)).digest()

def id32(value):
    data=value.encode("utf-8")
    if not data or len(data)>32 or b"\0" in data: raise ProtocolError("invalid id32")
    return data+b"\0"*(32-len(data))

def read_id32(data):
    if len(data)!=32: raise ProtocolError("id32 length")
    end=data.find(b"\0"); end=32 if end<0 else end
    if any(data[end:]): raise ProtocolError("id32 padding")
    try: value=data[:end].decode("utf-8")
    except UnicodeDecodeError as exc: raise ProtocolError("id32 utf8") from exc
    if not value: raise ProtocolError("empty id32")
    return value

def raw_sha256(value, label="SHA-256"):
    if isinstance(value, str):
        try: value=bytes.fromhex(value)
        except ValueError as exc: raise ProtocolError(label+" hex") from exc
    if not isinstance(value, bytes) or len(value)!=32: raise ProtocolError(label+" length")
    return value

def _hello_ack_result(payload):
    if len(payload)!=NAMES["HELLO_ACK"]["length"]: raise ProtocolError("HELLO_ACK length")
    return struct.unpack_from("<H",payload,314)[0]

def encode(message_type,payload,key,session_id,controller_boot_id,sequence,sender_monotonic_us=0):
    message=MESSAGES.get(int(message_type))
    if message is None or len(payload)!=message["length"]: raise ProtocolError("message/payload length")
    if len(key)<32: raise ProtocolError("PSK must contain at least 256 bits")
    if len(session_id)!=16 or len(controller_boot_id)!=16: raise ProtocolError("identifier length")
    if message["name"]=="HELLO":
        if session_id!=ZERO_ID or sequence!=0: raise ProtocolError("HELLO binding")
    elif message["name"]=="HELLO_ACK":
        result=_hello_ack_result(payload)
        if sequence!=0 or (result==0 and session_id==ZERO_ID) or (result!=0 and session_id!=ZERO_ID): raise ProtocolError("HELLO_ACK binding")
    elif session_id==ZERO_ID or sequence<1: raise ProtocolError("session binding")
    header=HEADER.pack(b"PHNT",1,int(message_type),64,len(payload),0,session_id,controller_boot_id,sequence,sender_monotonic_us)
    return header+payload+hmac.new(key,header+payload,hashlib.sha256).digest()

def _validate_payload(message,payload):
    if message["name"]=="COMMAND":
        flags,q0,q1,q2,grip,reserved=struct.unpack("<IffffI",payload)
        if flags&~0xF or reserved or not all(math.isfinite(x) for x in (q0,q1,q2,grip)): raise ProtocolError("COMMAND format")
        if not all(-6.4<=x<=6.4 for x in (q0,q1,q2)) or not 0<=grip<=1: raise ProtocolError("COMMAND range")
    if message["name"]=="HELLO":
        read_id32(payload[:32]); minor,key_slot,role=struct.unpack_from("<HBB",payload,32)
        if role not in (0,1) or key_slot not in (0,1): raise ProtocolError("HELLO enum")
    if message["name"]=="HELLO_ACK":
        read_id32(payload[16:48]); raw_sha256(payload[48:80],"build_id")
        minor,key_slot,role=struct.unpack_from("<HBB",payload,80)
        state,reference_flags,build_profile,gripper_capabilities,result=struct.unpack_from("<HHBBH",payload,308)
        if minor or key_slot not in (0,1) or role not in (0,1) or result==0 and key_slot!=role or state>10 or reference_flags&~3 or build_profile>1 or gripper_capabilities&~3 or result>15: raise ProtocolError("HELLO_ACK enum")
    if message["name"]=="TELEMETRY":
        read_id32(payload[:32]); raw_sha256(payload[32:64],"build_id")
        state,fault,status=struct.unpack_from("<HHI",payload,128)
        grip_state=struct.unpack_from("<H",payload,192)[0]
        loop_flags=struct.unpack_from("<I",payload,196)[0]
        read_id32(payload[200:232]); payload_state,build_profile,reserved=struct.unpack_from("<BBH",payload,232)
        if state>10 or fault!=0 and not 100<=fault<=116 or status&~0x3ff or grip_state>5 or loop_flags&~0x1f or payload_state>2 or build_profile>1 or reserved: raise ProtocolError("TELEMETRY enum")
    scalar={"u8":1,"i8":1,"u16":2,"i16":2,"u32":4,"i32":4,"u64":8,"f32":4,"id32":32}
    def size(kind): return scalar[kind] if kind in scalar else sum(size(f[1])*(f[2] if len(f)>2 else 1) for f in SCHEMA["types"][kind])
    offset=0
    for field in message["fields"]:
        count=field[2] if len(field)>2 else 1; length=size(field[1])*count
        if field[0].startswith("reserved") and any(payload[offset:offset+length]): raise ProtocolError("reserved bytes")
        if field[1]=="f32":
            for i in range(count):
                if not math.isfinite(struct.unpack_from("<f",payload,offset+4*i)[0]): raise ProtocolError("non-finite")
        offset+=length

def decode(datagram,key,expected_session=None,expected_boot=None,last_sequence=None):
    if len(datagram)>1024 or len(datagram)<96: raise ProtocolError("datagram length")
    magic,version,message_type,header_length,payload_length,flags,session,boot,sequence,sender_us=HEADER.unpack_from(datagram)
    if magic!=b"PHNT" or version!=1 or header_length!=64 or flags: raise ProtocolError("header")
    message=MESSAGES.get(message_type)
    if message is None or payload_length!=message["length"] or payload_length>928 or len(datagram)!=64+payload_length+32: raise ProtocolError("exact length")
    if not hmac.compare_digest(datagram[-32:],hmac.new(key,datagram[:-32],hashlib.sha256).digest()): raise ProtocolError("HMAC")
    if expected_session is not None and session!=expected_session: raise ProtocolError("session")
    if expected_boot is not None and boot!=expected_boot: raise ProtocolError("boot")
    if last_sequence is not None and sequence<=last_sequence: raise ProtocolError("sequence")
    payload=datagram[64:-32]; _validate_payload(message,payload)
    if message["name"]=="HELLO" and (session!=ZERO_ID or sequence!=0): raise ProtocolError("HELLO binding")
    if message["name"]=="HELLO_ACK":
        result=_hello_ack_result(payload)
        if sequence!=0 or (result==0 and session==ZERO_ID) or (result!=0 and session!=ZERO_ID): raise ProtocolError("HELLO_ACK binding")
    if message["name"] not in ("HELLO","HELLO_ACK") and (session==ZERO_ID or sequence<1): raise ProtocolError("session binding")
    return {"message":message["name"],"message_type":message_type,"payload":payload,"session_id":session,"controller_boot_id":boot,"sequence":sequence,"sender_monotonic_us":sender_us}

def hello_payload(robot_id,key_slot,role,nonce):
    if len(nonce)!=16: raise ProtocolError("nonce length")
    return id32(robot_id)+struct.pack("<HBB",0,key_slot,role)+nonce+struct.pack("<I",0)

def command_payload(flags,q,grip): return struct.pack("<IffffI",flags,float(q[0]),float(q[1]),float(q[2]),float(grip),0)

def telemetry_payload(robot_id,build_id,bundle_hash,safe_hash,state,fault,status,incident,last_sequence,command_age_ms,q,speed,grip,grip_state,battery_mv,loop_flags,profile_id,payload_state,build_profile):
    return struct.pack("<32s32s32s32sHHI16sQI3f3ffHHI32sBBH",id32(robot_id),raw_sha256(build_id,"build_id"),bundle_hash,safe_hash,state,fault,status,incident,last_sequence,command_age_ms,*q,*speed,grip,grip_state,battery_mv,loop_flags,id32(profile_id),payload_state,build_profile,0)
