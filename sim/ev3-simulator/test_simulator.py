import importlib.util
import pathlib
import struct
import unittest

PATH = pathlib.Path(__file__).with_name("phantom_simulator.py")
SPEC = importlib.util.spec_from_file_location("phantom_simulator", str(PATH))
simulator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(simulator)

class ProtocolTests(unittest.TestCase):
    def packet(self, seq=1, flags=simulator.FLAG_HELLO, session=123):
        body=struct.pack("<IHHQIQffff",simulator.MAGIC,simulator.VERSION,flags,session,seq,10,0.1,0.2,0.3,0.4)
        return simulator.crc_packet(body)

    def test_golden_vector_decodes(self):
        data=bytes.fromhex("50484e540100020008070605040302010d0c0b0a18171615141312110000803f000000c00000003f0000803e6230dfde")
        packet=simulator.decode_target(data)
        self.assertEqual(packet["session"],0x0102030405060708)
        self.assertEqual(packet["seq"],0x0a0b0c0d)

    def test_crc_and_nan_rejected(self):
        data=bytearray(self.packet());data[20]^=1
        self.assertIsNone(simulator.decode_target(bytes(data)))
        body=struct.pack("<IHHQIQffff",simulator.MAGIC,1,1,1,1,1,float("nan"),0,0,0)
        self.assertIsNone(simulator.decode_target(simulator.crc_packet(body)))

    def test_stale_and_wrong_session_ignored(self):
        sim=simulator.Simulator();now=sim.started
        sim.queue_datagram(self.packet(10),("127.0.0.1",1),now);self.assertEqual(len(sim.drain(now)),1)
        sim.queue_datagram(self.packet(9,simulator.FLAG_TRACKING),("127.0.0.1",1),now);sim.drain(now);self.assertEqual(sim.stale,1)
        sim.queue_datagram(self.packet(11,simulator.FLAG_TRACKING,999),("127.0.0.1",1),now);sim.drain(now);self.assertEqual(sim.last_seq,10)

    def test_ack_and_telemetry_sizes(self):
        sim=simulator.Simulator();sim.session=1
        self.assertEqual(len(sim.hello_ack()),84)
        self.assertEqual(len(sim.telemetry(sim.started)),84)

if __name__ == "__main__": unittest.main()
