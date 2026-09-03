"""Strict bounded reference codec for PHANTOM protocol v1."""
import hashlib, hmac, json, math, pathlib, struct

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA=json.loads((ROOT/"wire_schema.yaml").read_text(encoding="utf-8"))
MESSAGES={m["type"]:m for m in SCHEMA["messages"]}; NAMES={m["name"]:m for m in SCHEMA["messages"]}
HEADER=struct.Struct("<4sHHHHI16s16sQQ")
HEADER_BYTES=64; HMAC_BYTES=32; MAX_DATAGRAM_BYTES=1024; MAX_PAYLOAD_BYTES=928; ZERO_ID=b"\0"*16

class ProtocolError(ValueError): pass

def schema_hash():
    return hashlib.sha256(json.dumps(SCHEMA,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).digest()

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

def encode(message_type,payload,key,session_id,controller_boot_id,sequence,sender_monotonic_us=0):
    message=MESSAGES.get(int(message_type))
    if message is None or len(payload)!=message["length"]: raise ProtocolError("message/payload length")
    if len(key)<32: raise ProtocolError("PSK must contain at least 256 bits")
    if len(session_id)!=16 or len(controller_boot_id)!=16: raise ProtocolError("identifier length")
    if message["name"]=="HELLO":
        if session_id!=ZERO_ID or sequence!=0: raise ProtocolError("HELLO binding")
    elif message["name"]=="HELLO_ACK":
        if session_id==ZERO_ID or sequence!=0: raise ProtocolError("HELLO_ACK binding")
    elif session_id==ZERO_ID or sequence<1: raise ProtocolError("session binding")
    header=HEADER.pack(b"PHNT",1,int(message_type),64,len(payload),0,session_id,controller_boot_id,sequence,sender_monotonic_us)
    return header+payload+hmac.new(key,header+payload,hashlib.sha256).digest()

def _validate_payload(message,payload):
    if message["name"]=="COMMAND":
        flags,q0,q1,q2,grip,reserved=struct.unpack("<IffffI",payload)
        if flags&~0xF or reserved or not all(math.isfinite(x) for x in (q0,q1,q2,grip)): raise ProtocolError("COMMAND format")
        if not all(-6.4<=x<=6.4 for x in (q0,q1,q2)) or not 0<=grip<=1: raise ProtocolError("COMMAND range")
    if message["name"]=="HELLO":
        read_id32(payload[:32]); minor,_,role=struct.unpack_from("<HBB",payload,32)
        if minor or role not in (0,1): raise ProtocolError("HELLO enum")
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
    return {"message":message["name"],"message_type":message_type,"payload":payload,"session_id":session,"controller_boot_id":boot,"sequence":sequence,"sender_monotonic_us":sender_us}

def hello_payload(robot_id,key_slot,role,nonce):
    if len(nonce)!=16: raise ProtocolError("nonce length")
    return id32(robot_id)+struct.pack("<HBB",0,key_slot,role)+nonce+struct.pack("<I",0)

def command_payload(flags,q,grip): return struct.pack("<IffffI",flags,float(q[0]),float(q[1]),float(q[2]),float(grip),0)

def telemetry_payload(robot_id,build_id,bundle_hash,safe_hash,state,fault,status,incident,last_sequence,command_age_ms,q,speed,grip,grip_state,battery_mv,loop_flags,profile_id,payload_state,build_profile):
    return struct.pack("<32s32s32s32sHHI16sQI3f3ffHHI32sBBH",id32(robot_id),id32(build_id),bundle_hash,safe_hash,state,fault,status,incident,last_sequence,command_age_ms,*q,*speed,grip,grip_state,battery_mv,loop_flags,id32(profile_id),payload_state,build_profile,0)
