import hashlib,hmac,json,math,pathlib,struct,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"protocol"));import phantom_protocol as wire
class ProtocolTests(unittest.TestCase):
 def test_schema_exact_sizes_and_unique_types(self):
  scalar={"u8":1,"i8":1,"u16":2,"i16":2,"u32":4,"i32":4,"u64":8,"f32":4,"id32":32}
  def size(t):return scalar[t] if t in scalar else sum(size(f[1])*(f[2] if len(f)>2 else 1) for f in wire.SCHEMA["types"][t])
  seen=set()
  for m in wire.SCHEMA["messages"]:self.assertNotIn(m["type"],seen);seen.add(m["type"]);self.assertEqual(sum(size(f[1])*(f[2] if len(f)>2 else 1) for f in m["fields"]),m["length"])
 def test_golden_vectors(self):
  doc=json.loads((ROOT/"protocol"/"golden_vectors"/"v1.json").read_text())
  self.assertEqual(doc["protocol_schema_sha256"],wire.schema_hash().hex())
  for v in doc["vectors"]:
   data=bytes.fromhex(v["datagram_hex"]);key=bytes.fromhex(v["hmac_key_hex"]);self.assertEqual(hashlib.sha256(data).hexdigest(),v["datagram_sha256"]);self.assertTrue(hmac.compare_digest(data[-32:],hmac.new(key,data[:-32],hashlib.sha256).digest()));self.assertEqual(wire.decode(data,key)["message"],v["name"])
 def test_command_parser_rejects_length_hmac_reserved_nan_inf(self):
  key=bytes(range(32));session=b"S"*16;boot=b"B"*16;good=wire.encode(256,wire.command_payload(5,[.1,.2,.3],.4),key,session,boot,1)
  self.assertEqual(wire.decode(good,key)["message"],"COMMAND")
  for bad in (good[:-1],good+b"x",good[:20]+bytes([good[20]^1])+good[21:]):
   with self.assertRaises(wire.ProtocolError):wire.decode(bad,key)
  for value in (float("nan"),float("inf")):
   payload=struct.pack("<IffffI",5,value,0,0,.2,0);packet=wire.encode(256,payload,key,session,boot,2)
   with self.assertRaises(wire.ProtocolError):wire.decode(packet,key)
  for payload in (struct.pack("<IffffI",5,6.5,0,0,.2,0),struct.pack("<IffffI",5,0,0,0,-.1,0),struct.pack("<IffffI",5,0,0,0,.2,1)):
   packet=wire.encode(256,payload,key,session,boot,2)
   with self.assertRaises(wire.ProtocolError):wire.decode(packet,key)
 def test_authenticated_protocol_reserved_and_enum_rejections(self):
  key=bytes(range(32));boot=b"B"*16
  def retag(data):return data[:-32]+hmac.new(key,data[:-32],hashlib.sha256).digest()
  hello=wire.encode(1,wire.hello_payload("phantom01",0,0,b"N"*16),key,b"\0"*16,boot,0)
  for offset,value in ((4,2),(12,1),(64+34,2),(64+35,2)):
   with self.subTest(kind="hello",offset=offset):
    bad=bytearray(hello);bad[offset]=value
    with self.assertRaises(wire.ProtocolError):wire.decode(retag(bytes(bad)),key)
  telemetry=wire.encode(512,wire.telemetry_payload("phantom01",b"I"*32,b"C"*32,b"\0"*32,3,0,1,b"\0"*16,0,0xffffffff,(0,0,0),(0,0,0),0,0,7600,0,"UNSELECTED",2,1),key,b"S"*16,boot,1)
  for offset,value in ((64+133,0x04),(64+232,3),(64+234,1)):
   with self.subTest(kind="telemetry",offset=offset):
    bad=bytearray(telemetry);bad[offset]=value
    with self.assertRaises(wire.ProtocolError):wire.decode(retag(bytes(bad)),key)
 def test_unknown_type_and_sequence_rejected(self):
  key=bytes(range(32));header=wire.HEADER.pack(b"PHNT",1,0xffff,64,0,0,b"S"*16,b"B"*16,1,0);data=header+hmac.new(key,header,hashlib.sha256).digest()
  with self.assertRaises(wire.ProtocolError):wire.decode(data,key)
  packet=wire.encode(768,struct.pack("<QQ",1,2),key,b"S"*16,b"B"*16,2)
  with self.assertRaises(wire.ProtocolError):wire.decode(packet,key,last_sequence=2)
if __name__=="__main__":unittest.main()
