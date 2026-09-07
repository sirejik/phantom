import hashlib
import hmac
import json
import importlib.util
import pathlib
import struct
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("phantom_network", str(HERE / "phantom_network.py"))
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)
wire = network.wire


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.boot_path = pathlib.Path(self.temp.name) / "boot"
        self.status_path = pathlib.Path(self.temp.name) / "status.json"
        self.boot = b"B" * 16
        self.boot_path.write_text(self.boot.hex() + "\n", encoding="ascii")
        self.key = bytes(range(32))
        self.config = {"schema_version": 1, "robot_id": "phantom01", "build_profile": "Diagnostic",
                       "qualification_only": True, "qualification_evidence_manifest_hash": "0" * 64,
                       "actuator_scope_mask": 0, "safety_observation_mask": 0,
                       "network": {"listen_port_udp": 30470, "rx_rate_limit_pps": 100,
                                   "rx_burst_packets": 20, "hello_retry_window_ms": 2000,
                                   "session_stale_ms": 5000, "discovery_service_type": "_phantom-ev3._udp",
                                   "discovery_domain": "local.", "ip_family": "IPV4"}}
        self.bundle = {"schema_version": 1, "qualification_only": True,
                       "qualification_evidence_manifest_hash": "0" * 64,
                       "actuator_scope_mask": 0, "safety_observation_mask": 0}
        self.manifest = {"build_id": hashlib.sha256(b"stage3-test").hexdigest(), "specification_sha256": "11" * 32,
                         "protocol_schema_hash": wire.schema_hash().hex(),
                         "commissioning_bundle_hash": hashlib.sha256(network.canonical(self.bundle)).hexdigest()}
        self.server = network.Stage3Server(self.config, self.bundle, self.manifest, self.key,
                                           self.boot_path, self.status_path)
        self.server.token_time = 0.0
        self.server.read_boot_id()
        self.address = ("127.0.0.1", 12345)
        self.nonce = b"N" * 16

    def tearDown(self):
        self.temp.cleanup()

    def assertNoMotorAuthority(self):
        """The network worker must own no actuator path at all.

        This replaces a counter that was structurally always zero: it asserts the
        structural property (no motor interface, no scope, motion requests
        counted as rejected) instead of reading back a constant.
        """
        self.assertEqual(0, self.config["actuator_scope_mask"])
        self.assertEqual(0, self.bundle["actuator_scope_mask"])
        for forbidden in ("set_duty", "brake_all", "motor", "duty_cycle_sp"):
            self.assertFalse(hasattr(self.server, forbidden),
                             "network worker exposed an actuator surface: " + forbidden)
        self.assertNotIn("nonzero_motor_writes", self.server.counters)
        self.assertIn("motor_write_attempts_rejected", self.server.counters)

    def packet(self, name, payload, sequence, session=None, boot=None, key=None):
        return wire.encode(wire.NAMES[name]["type"], payload, self.key if key is None else key,
                           wire.ZERO_ID if session is None else session,
                           self.boot if boot is None else boot, sequence, 1)

    def hello(self, nonce=None, address=None):
        payload = wire.hello_payload("phantom01", 0, 0, self.nonce if nonce is None else nonce)
        return self.server.process(self.packet("HELLO", payload, 0), self.address if address is None else address, 1.0)

    def test_hello_is_authenticated_server_generated_and_retry_is_idempotent(self):
        ack = self.hello()
        self.assertIsNotNone(ack)
        decoded = wire.decode(ack, self.key)
        self.assertEqual(decoded["message"], "HELLO_ACK")
        self.assertNotEqual(decoded["session_id"], wire.ZERO_ID)
        self.assertEqual(struct.unpack_from("<H", decoded["payload"], 314)[0], network.RESULT_OK)
        self.assertEqual(decoded["payload"][48:80], bytes.fromhex(self.manifest["build_id"]))
        session = decoded["session_id"]
        self.assertEqual(self.hello(), ack)
        self.assertEqual(self.server.session_id, session)
        rejected = wire.decode(self.hello(b"X" * 16, ("127.0.0.1", 12346)), self.key)
        self.assertEqual(rejected["session_id"], wire.ZERO_ID)
        self.assertEqual(struct.unpack_from("<H", rejected["payload"], 314)[0], network.ERR_CONTROL_SESSION_BUSY)

    def test_authenticated_semantic_hello_rejections_have_zero_session(self):
        cases = ((wire.hello_payload("wrong", 0, 0, self.nonce), network.ERR_SESSION),
                 (wire.id32("phantom01") + struct.pack("<HBB", 0, 0, 1) + self.nonce + struct.pack("<I", 0), network.ERR_AUTH),
                 (wire.id32("phantom01") + struct.pack("<HBB", 1, 0, 0) + self.nonce + struct.pack("<I", 0), network.ERR_UNSUPPORTED),
                 (wire.id32("phantom01") + struct.pack("<HBB", 0, 0, 0) + self.nonce + struct.pack("<I", 1), network.ERR_UNSUPPORTED))
        for payload, expected in cases:
            reply = self.server.process(self.packet("HELLO", payload, 0), self.address, 1.0)
            decoded = wire.decode(reply, self.key)
            self.assertEqual(decoded["session_id"], wire.ZERO_ID)
            self.assertEqual(struct.unpack_from("<H", decoded["payload"], 314)[0], expected)
            self.assertIsNone(self.server.session_id)

    def test_controller_ipc_contract_gates_session_and_command(self):
        self.assertEqual(network.IPC_REQUEST.size, 120)
        self.assertEqual(network.IPC_REPLY.size, 64)
        class RejectOpen(network.LocalControllerAuthority):
            def open(self, *unused):
                return network.ERR_CONTROL_SESSION_BUSY
        self.server.authority = RejectOpen()
        rejected = wire.decode(self.hello(), self.key)
        self.assertEqual(rejected["session_id"], wire.ZERO_ID)
        self.assertEqual(struct.unpack_from("<H", rejected["payload"], 314)[0], network.ERR_CONTROL_SESSION_BUSY)
        self.assertIsNone(self.server.session_id)
        class RejectCommand(network.LocalControllerAuthority):
            def command(self, *unused):
                return network.ERR_SESSION
        self.server.authority = RejectCommand()
        self.hello()
        session = self.server.session_id
        command = self.packet("COMMAND", wire.command_payload(5, [.1, .2, .3], .4), 1, session)
        self.assertIsNone(self.server.process(command, self.address, 1.1))
        self.assertIsNone(self.server.session_id)
        self.assertNoMotorAuthority()

    def test_ping_pong_and_scope_zero_command(self):
        self.hello()
        session = self.server.session_id
        ping = self.packet("PING", struct.pack("<QQ", 7, 99), 1, session)
        pong = wire.decode(self.server.process(ping, self.address, 1.1), self.key,
                           expected_session=session, expected_boot=self.boot)
        self.assertEqual(pong["message"], "PONG")
        self.assertEqual(pong["payload"], struct.pack("<QQ", 7, 99))
        command = self.packet("COMMAND", wire.command_payload(5, [.1, .2, .3], .4), 2, session)
        self.assertIsNone(self.server.process(command, self.address, 1.2))
        self.assertEqual(self.server.last_command_sequence, 2)
        self.assertNoMotorAuthority()
        telemetry = wire.decode(self.server.telemetry(1.21), self.key, expected_session=session,
                                expected_boot=self.boot)
        self.assertEqual(telemetry["message"], "TELEMETRY")
        state = struct.unpack_from("<H", telemetry["payload"], 128)[0]
        q = struct.unpack_from("<3f", telemetry["payload"], 164)
        q_speed = struct.unpack_from("<3f", telemetry["payload"], 176)
        grip = struct.unpack_from("<f", telemetry["payload"], 188)[0]
        payload_state = telemetry["payload"][232]
        profile = telemetry["payload"][233]
        self.assertEqual(state, network.CONNECTED_UNREFERENCED)
        self.assertEqual(q, (0.0, 0.0, 0.0))
        self.assertEqual(q_speed, (0.0, 0.0, 0.0))
        self.assertEqual(grip, 0.0)
        self.assertEqual(payload_state, network.PAYLOAD_UNKNOWN)
        self.assertEqual(profile, 1)

    def test_bad_hmac_replay_wrong_boot_nan_and_oversize_are_inert(self):
        self.hello()
        session = self.server.session_id
        good = self.packet("PING", struct.pack("<QQ", 1, 2), 1, session)
        corrupt = bytearray(good); corrupt[-1] ^= 1
        self.assertIsNone(self.server.process(bytes(corrupt), self.address, 1.1))
        self.assertIsNotNone(self.server.process(good, self.address, 1.2))
        self.assertIsNone(self.server.process(good, self.address, 1.3))
        wrong_boot = self.packet("PING", struct.pack("<QQ", 2, 3), 2, session, b"Z" * 16)
        self.assertIsNone(self.server.process(wrong_boot, self.address, 1.4))
        for bad_value in (float("nan"), float("inf")):
            bad_float = struct.pack("<IffffI", 5, bad_value, 0.0, 0.0, .2, 0)
            bad_command = self.packet("COMMAND", bad_float, 2, session)
            self.assertIsNone(self.server.process(bad_command, self.address, 1.5))
        self.assertIsNone(self.server.process(b"X" * 1025, self.address, 1.6))
        self.assertNoMotorAuthority()

    def test_cheap_parser_identity_and_unknown_key_rejections_are_inert(self):
        hello = self.packet("HELLO", wire.hello_payload("phantom01", 0, 0, self.nonce), 0)
        malformed = []
        for offset, value in ((0, ord("X")), (4, 2), (10, 1), (12, 1)):
            packet = bytearray(hello)
            packet[offset] = value
            malformed.append(bytes(packet))
        malformed.extend((hello[:-1], hello + b"X", b"X" * 10))
        packet = bytearray(hello)
        struct.pack_into("<H", packet, 6, 0xffff)
        malformed.append(bytes(packet))
        for packet in malformed:
            self.assertIsNone(self.server.process(packet, self.address, 1.0))
        wrong_key = self.packet("HELLO", wire.hello_payload("phantom01", 0, 0, self.nonce), 0,
                                key=b"K" * 32)
        wrong_robot = self.packet("HELLO", wire.hello_payload("another", 0, 0, self.nonce), 0)
        self.assertIsNone(self.server.process(wrong_key, self.address, 1.1))
        rejected = wire.decode(self.server.process(wrong_robot, self.address, 1.2), self.key)
        self.assertEqual(rejected["session_id"], wire.ZERO_ID)
        self.assertEqual(struct.unpack_from("<H", rejected["payload"], 314)[0], network.ERR_SESSION)
        self.assertIsNone(self.server.session_id)
        self.assertNoMotorAuthority()

    def test_stale_old_duplicate_and_reordered_session_packets_are_inert(self):
        self.hello()
        old_session = self.server.session_id
        first = self.packet("PING", struct.pack("<QQ", 1, 2), 3, old_session)
        reordered = self.packet("PING", struct.pack("<QQ", 2, 3), 2, old_session)
        self.assertIsNotNone(self.server.process(first, self.address, 1.1))
        self.assertIsNone(self.server.process(first, self.address, 1.2))
        self.assertIsNone(self.server.process(reordered, self.address, 1.3))
        self.server.end_session("test_timeout")
        stale = self.packet("COMMAND", wire.command_payload(5, [.1, .2, .3], .4), 4, old_session)
        self.assertIsNone(self.server.process(stale, self.address, 7.0))
        self.assertEqual(self.server.last_command_sequence, 0)
        self.assertNoMotorAuthority()

    def test_controller_restart_invalidates_session(self):
        self.hello()
        old = self.server.session_id
        old_target = self.packet("COMMAND", wire.command_payload(5, [.1, .2, .3], .4), 1, old)
        self.boot_path.write_text((b"C" * 16).hex() + "\n", encoding="ascii")
        self.server.read_boot_id()
        self.assertIsNone(self.server.session_id)
        self.assertNotEqual(old, self.server.session_id)
        self.assertIsNone(self.server.process(old_target, self.address, 1.1))
        self.assertEqual(self.server.last_command_sequence, 0)
        self.assertNoMotorAuthority()

    def test_telemetry_is_serialised_from_the_controller_snapshot(self):
        """Telemetry state/fault/battery must come from the controller, not constants."""
        self.hello()
        session = self.server.session_id

        class Reporting(network.LocalControllerAuthority):
            def snapshot(self, boot_id, rx_us):
                return {"state": network.DISCOVERY, "fault_code": 107,
                        "status_flags": 0x18, "battery_mv": 7123, "grip_state": 1,
                        "loop_health_flags": 4, "incident_id": b"\xab" * 16,
                        "q_actual": (0.0, 0.0, 0.0), "q_speed": (0.0, 0.0, 0.0),
                        "grip_actual": 0.0, "snapshot_monotonic_us": rx_us}

        self.server.authority = Reporting()
        self.server.authority.session = session
        telemetry = wire.decode(self.server.telemetry(1.3), self.key)
        payload = telemetry["payload"]
        self.assertEqual(network.DISCOVERY, struct.unpack_from("<H", payload, 128)[0])
        self.assertEqual(107, struct.unpack_from("<H", payload, 130)[0])
        self.assertEqual(0x18, struct.unpack_from("<I", payload, 132)[0])
        self.assertEqual(b"\xab" * 16, payload[136:152])
        self.assertEqual(7123, struct.unpack_from("<H", payload, 194)[0])
        self.assertEqual(4, struct.unpack_from("<I", payload, 196)[0])
        self.assertNoMotorAuthority()

    def test_absent_controller_snapshot_suppresses_telemetry_and_handshake(self):
        """An unobservable controller must not be reported as a healthy robot."""
        class Silent(network.LocalControllerAuthority):
            def snapshot(self, boot_id, rx_us):
                return None

        self.hello()
        self.assertIsNotNone(self.server.session_id)
        self.server.authority = Silent()
        self.assertIsNone(self.server.telemetry(1.4))
        self.assertGreater(self.server.counters["controller_snapshot_stale"], 0)

        self.server.end_session("test")
        self.assertIsNone(self.hello())
        self.assertIsNone(self.server.session_id)
        self.assertNoMotorAuthority()

    def test_motion_request_at_zero_scope_is_counted_as_rejected(self):
        self.hello()
        session = self.server.session_id
        hold = self.packet("COMMAND", wire.command_payload(2, [0.0, 0.0, 0.0], 0.0), 1, session)
        self.server.process(hold, self.address, 1.1)
        self.assertEqual(0, self.server.counters["motor_write_attempts_rejected"])
        moving = self.packet("COMMAND", wire.command_payload(5, [.1, .2, .3], .4), 2, session)
        self.server.process(moving, self.address, 1.2)
        self.assertEqual(1, self.server.counters["motor_write_attempts_rejected"])
        self.assertNoMotorAuthority()

    def test_status_snapshot_reports_controller_observability(self):
        self.hello()
        self.server.telemetry(1.1)
        self.server.status()
        report = json.loads(self.status_path.read_text(encoding="utf-8"))
        self.assertEqual(2, report["schema_version"])
        self.assertTrue(report["controller_snapshot_fresh"])
        self.assertEqual(network.CONNECTED_UNREFERENCED, report["controller_state"])
        self.assertNotIn("nonzero_motor_writes", report["counters"])

    def test_token_bucket_bounds_flood(self):
        self.server.rate = 1
        self.server.capacity = 2
        self.server.tokens = 2
        packet = self.packet("HELLO", wire.hello_payload("phantom01", 0, 0, self.nonce), 0)
        for unused in range(1000):
            self.server.process(packet, self.address, 2.0)
        self.assertGreater(self.server.counters["rx_drop"], 990)
        self.assertNoMotorAuthority()


if __name__ == "__main__":
    unittest.main()
