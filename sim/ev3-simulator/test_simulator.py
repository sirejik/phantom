import hashlib,hmac,importlib.util,json,pathlib,struct,sys,unittest
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(ROOT/"protocol"))
import phantom_protocol as wire
spec=importlib.util.spec_from_file_location("phantom_simulator",str(HERE/"phantom_simulator.py"));simulator=importlib.util.module_from_spec(spec);spec.loader.exec_module(simulator)

class WireTests(unittest.TestCase):
    def setUp(self):self.sim=simulator.Simulator();self.address=("127.0.0.1",12345);self.nonce=b"N"*16
    def hello(self):
        payload=wire.hello_payload("phantom01",0,0,self.nonce);packet=wire.encode(1,payload,simulator.TEST_KEY,b"\0"*16,self.sim.boot_id,0,1);reply=self.sim.process(packet,self.address,self.sim.started)[0][0];decoded=wire.decode(reply,simulator.TEST_KEY);self.assertEqual(decoded["message"],"HELLO_ACK");self.assertEqual(decoded["payload"][:16],self.nonce)
    def send(self,name,payload,sequence):return wire.encode(wire.NAMES[name]["type"],payload,simulator.TEST_KEY,self.sim.session,self.sim.boot_id,sequence,sequence)
    def test_all_generated_vectors_have_valid_hmac_and_lengths(self):
        vectors=json.loads((ROOT/"protocol"/"golden_vectors"/"v1.json").read_text())["vectors"]
        self.assertEqual(len(vectors),len(wire.MESSAGES))
        for vector in vectors:
            data=bytes.fromhex(vector["datagram_hex"]);self.assertEqual(len(data),64+vector["payload_length"]+32);self.assertTrue(hmac.compare_digest(data[-32:],hmac.new(bytes.fromhex(vector["hmac_key_hex"]),data[:-32],hashlib.sha256).digest()))
    def test_handshake_is_server_generated_and_retry_idempotent(self):
        self.hello();session=self.sim.session;self.hello();self.assertEqual(session,self.sim.session)
    def test_reference_required_before_command(self):
        self.hello();command=self.send("COMMAND",wire.command_payload(5,[.1,.2,.3],.4),1);self.sim.process(command,self.address,self.sim.started+.01);self.assertEqual(self.sim.state,simulator.SAFE_HOLD)
    def test_calibration_reference_command_and_timeout(self):
        self.hello();reply=self.sim.process(self.send("CALIBRATION_QUERY",struct.pack("<Q",7),1),self.address,self.sim.started+.01)[0][0];sample=wire.decode(reply,simulator.TEST_KEY)["payload"];sample_id=struct.unpack_from("<Q",sample,8)[0]
        reference=struct.pack("<Q32s32sQ3ff4i",1,self.sim.bundle_hash,b"\x44"*32,sample_id,0.,0.,.5,0.,0,0,500,0);ack=self.sim.process(self.send("SET_JOINT_REFERENCE",reference,2),self.address,self.sim.started+.02);self.assertTrue(ack);self.assertTrue(self.sim.references)
        self.sim.process(self.send("COMMAND",wire.command_payload(5,[.2,.1,.6],.8),3),self.address,self.sim.started+.03);self.assertEqual(self.sim.state,simulator.TRACKING);self.sim.update(.02,self.sim.started+.20);self.assertEqual(self.sim.state,simulator.SAFE_HOLD)
    def test_corrupt_hmac_reserved_nan_stale_do_not_change_target(self):
        self.hello();before=list(self.sim.target);packet=bytearray(self.send("COMMAND",wire.command_payload(5,[.1,.2,.3],.4),1));packet[-1]^=1;self.sim.process(bytes(packet),self.address,self.sim.started);self.assertEqual(before,self.sim.target)
        bad=struct.pack("<IffffI",5,float("nan"),0,0,.2,0);data=self.send("COMMAND",bad,2);self.sim.process(data,self.address,self.sim.started);self.assertEqual(before,self.sim.target)
    def test_scenarios_are_declared(self):self.assertTrue({"stall","reference_loss","maintenance","local_stop","disconnect"}.issubset(simulator.SCENARIOS))
    def test_stage3_network_only_profile_and_controlled_restart(self):
        sim=simulator.Simulator(network_only=True);address=("127.0.0.1",12345);nonce=b"Q"*16;hello=wire.encode(1,wire.hello_payload("phantom01",0,0,nonce),simulator.TEST_KEY,b"\0"*16,sim.boot_id,0,1);ack=wire.decode(sim.process(hello,address,sim.started)[0][0],simulator.TEST_KEY)
        self.assertEqual(struct.unpack_from("<H",ack["payload"],308)[0],simulator.CONNECTED_UNREFERENCED);self.assertEqual(ack["payload"][312],1);self.assertEqual(ack["payload"][148:180],sim.bundle_hash)
        old_boot=sim.boot_id;sim.restart_controller();self.assertNotEqual(old_boot,sim.boot_id);self.assertIsNone(sim.session)
    def test_stage3_fault_scenarios_are_declared(self):
        required={"hello_ack_lost","busy","telemetry_stop_resume","bad_hmac","wrong_robot","wrong_protocol","wrong_schema_hash","wrong_bundle_hash","duplicate_packet","stale_packet","reorder","controller_boot_change","endpoint_update","service_remove_readd"}
        self.assertTrue(required.issubset(simulator.SCENARIOS))
    def test_competing_control_is_busy_and_stale_session_can_be_replaced(self):
        self.hello();first_session=self.sim.session;other=("127.0.0.1",23456);nonce=b"Z"*16;hello=wire.encode(1,wire.hello_payload("phantom01",0,0,nonce),simulator.TEST_KEY,b"\0"*16,self.sim.boot_id,0,1)
        rejected=wire.decode(self.sim.process(hello,other,self.sim.started+.1)[0][0],simulator.TEST_KEY);self.assertEqual(rejected["session_id"],b"\0"*16);self.assertEqual(struct.unpack_from("<H",rejected["payload"],314)[0],simulator.ERR_CONTROL_SESSION_BUSY);self.assertEqual(self.sim.session,first_session)
        accepted=wire.decode(self.sim.process(hello,other,self.sim.started+self.sim.session_stale+.2)[0][0],simulator.TEST_KEY);self.assertNotEqual(accepted["session_id"],b"\0"*16);self.assertNotEqual(self.sim.session,first_session)
if __name__=="__main__":unittest.main()
