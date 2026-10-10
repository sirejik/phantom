import copy,hashlib,hmac,json,math,pathlib,struct,sys,unittest
import tempfile
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"protocol"));sys.path.insert(0,str(ROOT/"tools"));import phantom_protocol as wire;import protocolgen
class ProtocolTests(unittest.TestCase):
 def test_build_gate_ignores_missing_or_modified_generated_documentation(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory)
   with patch.object(protocolgen,"ROOT",root),patch.object(sys,"argv",["protocolgen"]):
    protocolgen.main()
    document=root/"docs/protocol-wire-reference.md"
    document.write_bytes(b"edited documentation\n")
    with patch.object(sys,"argv",["protocolgen","--check"]):protocolgen.main()
    with patch.object(sys,"argv",["protocolgen","--check","--include-docs"]):
     with self.assertRaises(SystemExit):protocolgen.main()
    document.unlink()
    with patch.object(sys,"argv",["protocolgen","--check"]):protocolgen.main()
 def test_schema_exact_sizes_and_unique_types(self):
  scalar={"u8":1,"i8":1,"u16":2,"i16":2,"u32":4,"i32":4,"u64":8,"f32":4,"id32":32}
  def size(t):return scalar[t] if t in scalar else sum(size(f[1])*(f[2] if len(f)>2 else 1) for f in wire.SCHEMA["types"][t])
  seen=set()
  for m in wire.SCHEMA["messages"]:self.assertNotIn(m["type"],seen);seen.add(m["type"]);self.assertEqual(sum(size(f[1])*(f[2] if len(f)>2 else 1) for f in m["fields"]),m["length"])
 def test_golden_vectors(self):
  doc=json.loads((ROOT/"protocol"/"golden_vectors"/"v1.json").read_text())
  self.assertEqual(doc["protocol_schema_sha256"],wire.schema_hash().hex())
  self.assertEqual(doc["protocol_semantics_sha256"],wire.semantics_hash().hex())
  self.assertEqual(doc["protocol_contract_sha256"],wire.contract_hash().hex())
  for v in doc["vectors"]:
   data=bytes.fromhex(v["datagram_hex"]);key=bytes.fromhex(v["hmac_key_hex"]);self.assertEqual(hashlib.sha256(data).hexdigest(),v["datagram_sha256"]);self.assertTrue(hmac.compare_digest(data[-32:],hmac.new(key,data[:-32],hashlib.sha256).digest()));self.assertEqual(wire.decode(data,key)["message"],v["name"])
 def test_structural_and_semantic_identities_are_independent(self):
  renamed=copy.deepcopy(wire.SCHEMA);renamed["messages"][1]["fields"][7][0]="renamed_without_layout_change"
  renamed_schema=hashlib.sha256(wire.jcs.canonicalize(protocolgen.structural_projection(renamed))).digest()
  self.assertEqual(renamed_schema,wire.schema_hash())
  renumbered=copy.deepcopy(wire.SCHEMA);state=renumbered["enums"]["State"];state["READY"],state["HOLD"]=state["HOLD"],state["READY"]
  renumbered_schema=hashlib.sha256(wire.jcs.canonicalize(protocolgen.structural_projection(renumbered))).digest()
  self.assertNotEqual(renumbered_schema,wire.schema_hash())
  moved_bit=copy.deepcopy(wire.SCHEMA);flags=moved_bit["bitfields"]["command_motion_flags"];flags["MOTION_ENABLE"],flags["TRACKING_VALID"]=flags["TRACKING_VALID"],flags["MOTION_ENABLE"]
  moved_bit_schema=hashlib.sha256(wire.jcs.canonicalize(protocolgen.structural_projection(moved_bit))).digest()
  self.assertNotEqual(moved_bit_schema,wire.schema_hash())
  changed=copy.deepcopy(wire.SEMANTICS);changed["validation"]["unknown_enum_or_bit"]="REJECT_AND_AUDIT"
  changed_semantics=hashlib.sha256(wire.jcs.canonicalize(changed)).digest()
  self.assertNotEqual(changed_semantics,wire.semantics_hash())
  changed_contract=hashlib.sha256(wire.jcs.canonicalize({"protocol_schema_hash":wire.schema_hash().hex(),"protocol_semantics_hash":changed_semantics.hex()})).digest()
  self.assertNotEqual(changed_contract,wire.contract_hash())
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
 def test_hello_ack_reserved_bytes_are_authenticated_and_rejected(self):
  vectors=json.loads((ROOT/"protocol/golden_vectors/v1.json").read_text())["vectors"]
  vector=next(v for v in vectors if v["name"]=="HELLO_ACK")
  key=bytes.fromhex(vector["hmac_key_hex"]);packet=bytearray.fromhex(vector["datagram_hex"])
  field=next(f for f in protocolgen.offsets(wire.SCHEMA,wire.NAMES["HELLO_ACK"]) if f[0]=="reserved0")
  for index in (0,field[4]-1):
   bad=bytearray(packet);bad[64+field[3]+index]=1
   bad[-32:]=hmac.new(key,bytes(bad[:-32]),hashlib.sha256).digest()
   with self.assertRaises(wire.ProtocolError):wire.decode(bytes(bad),key)
if __name__=="__main__":unittest.main()
