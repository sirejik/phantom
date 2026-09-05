#!/usr/bin/env python3
"""Bounded EV3-side PHANTOM v1 network worker for the Stage-3 zero-scope profile."""
from __future__ import print_function

import argparse
import hashlib
import hmac
import json
import math
import os
import pathlib
import select
import socket
import struct
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
WIRE_DIR = HERE if (HERE / "wire_schema.yaml").is_file() else HERE.parents[1] / "protocol"
sys.path.insert(0, str(WIRE_DIR))
import phantom_protocol as wire

DISCOVERY = wire.SCHEMA["enums"]["State"]["DISCOVERY"]
CONNECTED_UNREFERENCED = wire.SCHEMA["enums"]["State"]["CONNECTED_UNREFERENCED"]
FAULT_NONE = wire.SCHEMA["enums"]["Fault"]["NONE"]
STATUS_BUNDLE_VALID = 1 << wire.SCHEMA["bitfields"]["telemetry_status_flags"]["COMMISSIONING_BUNDLE_VALID"]
LOOP_NETWORK_BACKPRESSURE = 1 << wire.SCHEMA["bitfields"]["loop_health_flags"]["NETWORK_BACKPRESSURE_SEEN"]
RESULT_OK = wire.SCHEMA["enums"]["ResultCode"]["OK"]
ERR_AUTH = wire.SCHEMA["enums"]["ResultCode"]["ERR_AUTH"]
ERR_SESSION = wire.SCHEMA["enums"]["ResultCode"]["ERR_SESSION"]
ERR_CONTROL_SESSION_BUSY = wire.SCHEMA["enums"]["ResultCode"]["ERR_CONTROL_SESSION_BUSY"]
ERR_UNSUPPORTED = wire.SCHEMA["enums"]["ResultCode"]["ERR_UNSUPPORTED"]
PAYLOAD_UNKNOWN = wire.SCHEMA["enums"]["PayloadState"]["UNKNOWN"]
IPC_REQUEST = struct.Struct("<4sHHI16sQ16sBBBB4sHH16sQQ24s")
IPC_REPLY = struct.Struct("<4sHHI16sQ16sQHH")


class LocalControllerAuthority(object):
    """Deterministic scope-zero authority used only by host unit tests."""
    def __init__(self):
        self.generation = 1
        self.session = None
        self.last_sequence = 0

    def open(self, boot_id, session_id, role, key_slot, nonce, endpoint, wire_sequence, rx_us):
        if role != 0 or key_slot != 0 or wire_sequence != 0:
            return ERR_AUTH
        if self.session is not None and self.session != session_id:
            return ERR_CONTROL_SESSION_BUSY
        self.session = session_id
        self.last_sequence = 0
        return RESULT_OK

    def command(self, boot_id, session_id, endpoint, wire_sequence, rx_us, command_payload):
        if self.session != session_id or wire_sequence <= self.last_sequence:
            return ERR_SESSION
        self.last_sequence = wire_sequence
        return RESULT_OK

    def invalidate(self, boot_id, session_id, endpoint, rx_us):
        if self.session == session_id:
            self.session = None
            self.last_sequence = 0

    def close(self):
        pass


class ControllerIpcAuthority(object):
    """Fixed 120/64-byte AF_UNIX datagram client for controller authorization."""
    def __init__(self, own_path="/run/phantom/network/controller.sock",
                 controller_path="/run/phantom/controller/network.sock", timeout=.25,
                 ipc_group="phantom-ipc"):
        self.own_path = pathlib.Path(own_path)
        self.controller_path = controller_path
        self.timeout = timeout
        self.generation = struct.unpack("<Q", os.urandom(8))[0] or 1
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.own_path.unlink()
        except FileNotFoundError:
            pass
        self.sock.bind(str(self.own_path))
        if ipc_group is not None:
            import grp
            os.chown(str(self.own_path), -1, grp.getgrnam(ipc_group).gr_gid)
        os.chmod(str(self.own_path), 0o660)
        self.sock.setblocking(False)

    def _exchange(self, message_type, boot_id, session_id, role, key_slot, nonce,
                  endpoint, wire_sequence, rx_us, expect_reply=True, command_payload=b"\0" * 24):
        address, port = endpoint
        packed = IPC_REQUEST.pack(b"PHIP", 1, message_type, 0, boot_id, self.generation,
                                  session_id, role, key_slot, 4, 0, socket.inet_aton(address),
                                  socket.htons(port), 0, nonce, wire_sequence, rx_us,
                                  command_payload)
        try:
            self.sock.sendto(packed, self.controller_path)
        except OSError:
            return ERR_SESSION
        if not expect_reply:
            return RESULT_OK
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ERR_SESSION
            readable, unused_write, unused_error = select.select([self.sock], [], [], remaining)
            if not readable:
                return ERR_SESSION
            data = self.sock.recv(65)
            if len(data) != IPC_REPLY.size:
                continue
            magic, version, reply_type, reserved, reply_boot, generation, reply_session, request_sequence, result, tail = IPC_REPLY.unpack(data)
            if (magic, version, reply_type, reserved, reply_boot, generation, reply_session,
                    request_sequence, tail) == (b"PHIP", 1, 2, 0, boot_id, self.generation,
                                                 session_id, wire_sequence, 0):
                return result

    def open(self, boot_id, session_id, role, key_slot, nonce, endpoint, wire_sequence, rx_us):
        return self._exchange(1, boot_id, session_id, role, key_slot, nonce, endpoint,
                              wire_sequence, rx_us)

    def command(self, boot_id, session_id, endpoint, wire_sequence, rx_us, command_payload):
        return self._exchange(3, boot_id, session_id, 0, 0, b"\0" * 16, endpoint,
                              wire_sequence, rx_us, command_payload=command_payload)

    def invalidate(self, boot_id, session_id, endpoint, rx_us):
        self._exchange(4, boot_id, session_id, 0, 0, b"\0" * 16, endpoint, 0, rx_us, False)

    def close(self):
        self.sock.close()
        try:
            self.own_path.unlink()
        except FileNotFoundError:
            pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def systemd_ready(status):
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        notify.connect(address)
        notify.sendall(("READY=1\nSTATUS=" + status).encode("utf-8"))
    finally:
        notify.close()


def load_key(path):
    key_path = pathlib.Path(path)
    mode = key_path.stat().st_mode & 0o777
    if mode & 0o027:
        raise ValueError("control key permissions must be owner/group read only")
    raw = key_path.read_bytes().strip()
    if len(raw) == 64:
        try:
            raw = bytes.fromhex(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            pass
    if len(raw) < 32:
        raise ValueError("control key must contain at least 256 bits")
    return raw


def hex_hash(value, label):
    try:
        raw = bytes.fromhex(value)
    except (TypeError, ValueError):
        raise ValueError(label + " is not hex")
    if len(raw) != 32:
        raise ValueError(label + " must be SHA-256")
    return raw


class Stage3Server(object):
    def __init__(self, config, bundle, manifest, key, boot_path, status_path, authority=None):
        zero_hash = "0" * 64
        if config.get("build_profile") != "Diagnostic" or config.get("qualification_only") is not True or config.get("qualification_evidence_manifest_hash") != zero_hash or config.get("actuator_scope_mask") != 0 or config.get("safety_observation_mask") != 0:
            raise ValueError("network worker requires Diagnostic qualification_only scope 0x00")
        if bundle.get("qualification_only") is not True or bundle.get("qualification_evidence_manifest_hash") != zero_hash or bundle.get("actuator_scope_mask") != 0 or bundle.get("safety_observation_mask") != 0:
            raise ValueError("authoritative bundle is not network-only")
        if (config["network"].get("discovery_service_type"), config["network"].get("discovery_domain"), config["network"].get("ip_family")) != ("_phantom-ev3._udp", "local.", "IPV4"):
            raise ValueError("DNS-SD/IP family contract mismatch")
        self.config = config
        self.bundle = bundle
        self.manifest = manifest
        self.key = key
        self.robot_id = config["robot_id"]
        self.port = int(config["network"]["listen_port_udp"])
        self.rate = float(config["network"]["rx_rate_limit_pps"])
        self.capacity = float(config["network"]["rx_burst_packets"])
        self.retry_window = float(config["network"]["hello_retry_window_ms"]) / 1000.0
        self.session_stale = float(config["network"]["session_stale_ms"]) / 1000.0
        if not (1 <= self.rate <= 10000 and 1 <= self.capacity <= 1024 and .1 <= self.retry_window <= 60 and .2 <= self.session_stale <= 300):
            raise ValueError("network bounds invalid")
        self.boot_path = pathlib.Path(boot_path)
        self.status_path = pathlib.Path(status_path)
        self.boot_id = None
        self.authority = authority if authority is not None else LocalControllerAuthority()
        self.session_id = None
        self.endpoint = None
        self.nonce = None
        self.hello_time = 0.0
        self.last_rx_time = 0.0
        self.last_rx_sequence = 0
        self.tx_sequence = 0
        self.cached_ack = None
        self.last_command_time = None
        self.last_command_sequence = 0
        self.tokens = self.capacity
        self.token_time = time.monotonic()
        self.started = self.token_time
        self.next_telemetry = self.started
        self.next_status = self.started
        self.counters = {"rx": 0, "rx_drop": 0, "hmac_fail": 0, "parser_reject": 0,
                         "hello_accept": 0, "hello_reject": 0, "replay_reject": 0,
                         "pong": 0, "telemetry": 0, "command_scope_zero": 0,
                         "nonzero_motor_writes": 0}
        self.bundle_hash = hashlib.sha256(canonical(bundle)).digest()
        if manifest.get("commissioning_bundle_hash") != self.bundle_hash.hex():
            raise ValueError("bundle/manifest hash mismatch")
        self.spec_hash = hex_hash(manifest["specification_sha256"], "specification_sha256")
        self.protocol_hash = hex_hash(manifest["protocol_schema_hash"], "protocol_schema_hash")
        if self.protocol_hash != wire.schema_hash():
            raise ValueError("protocol schema hash mismatch")
        self.build_id = manifest["build_id"]
        if not isinstance(self.build_id, str) or len(self.build_id) != 64 or self.build_id.lower() != self.build_id:
            raise ValueError("build_id must be 64 lowercase hex symbols")
        self.build_id_bytes = hex_hash(self.build_id, "build_id")

    def event(self, name, **fields):
        record = {"event": name, "monotonic_us": int(time.monotonic() * 1000000)}
        record.update(fields)
        print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)

    def read_boot_id(self):
        value = bytes.fromhex(self.boot_path.read_text(encoding="ascii").strip())
        if len(value) != 16 or value == wire.ZERO_ID:
            raise ValueError("controller boot id invalid")
        if self.boot_id is not None and value != self.boot_id:
            self.end_session("controller_restart")
            self.event("CONTROLLER_RESTART")
        self.boot_id = value

    def end_session(self, reason):
        if self.session_id is not None:
            self.event("SESSION_ENDED", reason=reason)
            self.authority.invalidate(self.boot_id, self.session_id, self.endpoint,
                                      int(time.monotonic() * 1000000))
        self.session_id = self.endpoint = self.nonce = self.cached_ack = None
        self.last_rx_sequence = self.tx_sequence = self.last_command_sequence = 0
        self.last_command_time = None

    def token_allowed(self, now):
        self.tokens = min(self.capacity, self.tokens + (now - self.token_time) * self.rate)
        self.token_time = now
        if self.tokens < 1.0:
            self.counters["rx_drop"] += 1
            return False
        self.tokens -= 1.0
        return True

    @staticmethod
    def cheap_header(data):
        if len(data) < 96 or len(data) > wire.MAX_DATAGRAM_BYTES:
            raise wire.ProtocolError("datagram length")
        fields = wire.HEADER.unpack_from(data)
        magic, version, message_type, header_length, payload_length, flags = fields[:6]
        message = wire.MESSAGES.get(message_type)
        if magic != b"PHNT" or version != 1 or header_length != 64 or flags:
            raise wire.ProtocolError("header")
        if message is None or payload_length != message["length"] or payload_length > wire.MAX_PAYLOAD_BYTES or len(data) != 64 + payload_length + 32:
            raise wire.ProtocolError("exact length")
        return fields, message

    def hello_ack_payload(self, nonce, result=RESULT_OK, key_slot=0, role=0):
        zero = b"\0" * 32
        return struct.pack("<16s32s32sHBB32s32s32s32s32s32s32sHHBBH3f3f3f3f",
                           nonce, wire.id32(self.robot_id), self.build_id_bytes, 0, key_slot, role,
                           self.spec_hash, self.protocol_hash, self.bundle_hash,
                           zero, zero, zero, zero, CONNECTED_UNREFERENCED, 0, 1, 0, result,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                           0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def reject_hello(self, nonce, result, key_slot, role, now):
        self.counters["hello_reject"] += 1
        self.event("HELLO_REJECTED", result_code=result)
        payload = self.hello_ack_payload(nonce, result, key_slot, role)
        return wire.encode(wire.NAMES["HELLO_ACK"]["type"], payload, self.key,
                           wire.ZERO_ID, self.boot_id, 0, int(now * 1000000))

    def start_session(self, packet, address, now):
        payload = packet["payload"]
        robot = wire.read_id32(payload[:32])
        minor, key_slot, role = struct.unpack_from("<HBB", payload, 32)
        nonce = payload[36:52]
        capabilities = struct.unpack_from("<I", payload, 52)[0]
        if packet["session_id"] != wire.ZERO_ID or packet["sequence"] != 0 or packet["controller_boot_id"] != self.boot_id:
            raise wire.ProtocolError("HELLO binding")
        if key_slot not in (0, 1):
            raise wire.ProtocolError("unknown key slot")
        if key_slot != 0 or role != 0 or key_slot != role:
            return self.reject_hello(nonce, ERR_AUTH, key_slot, role, now)
        if robot != self.robot_id:
            return self.reject_hello(nonce, ERR_SESSION, key_slot, role, now)
        if minor != 0 or capabilities != 0:
            return self.reject_hello(nonce, ERR_UNSUPPORTED, key_slot, role, now)
        duplicate = self.session_id is not None and address == self.endpoint and nonce == self.nonce and now - self.hello_time <= self.retry_window
        if duplicate:
            return self.cached_ack
        if self.session_id is not None and now - self.last_rx_time <= self.session_stale:
            return self.reject_hello(nonce, ERR_CONTROL_SESSION_BUSY, key_slot, role, now)
        if self.session_id is not None:
            self.end_session("stale_replaced")
        candidate = os.urandom(16)
        while candidate == wire.ZERO_ID:
            candidate = os.urandom(16)
        result = self.authority.open(self.boot_id, candidate, role, key_slot, nonce, address,
                                     packet["sequence"], int(now * 1000000))
        if result != RESULT_OK:
            return self.reject_hello(nonce, result, key_slot, role, now)
        self.session_id = candidate
        self.endpoint = address
        self.nonce = nonce
        self.hello_time = self.last_rx_time = now
        self.last_rx_sequence = self.tx_sequence = 0
        self.last_command_time = None
        self.last_command_sequence = 0
        self.cached_ack = wire.encode(wire.NAMES["HELLO_ACK"]["type"], self.hello_ack_payload(nonce), self.key, self.session_id, self.boot_id, 0, int(now * 1000000))
        self.counters["hello_accept"] += 1
        self.event("HELLO_ACCEPTED", role="CONTROL")
        self.event("SESSION_CREATED", session="redacted")
        return self.cached_ack

    def send_session(self, name, payload, now):
        self.tx_sequence += 1
        return wire.encode(wire.NAMES[name]["type"], payload, self.key, self.session_id, self.boot_id, self.tx_sequence, int(now * 1000000))

    def process(self, data, address, now=None):
        now = time.monotonic() if now is None else now
        self.counters["rx"] += 1
        try:
            fields, message = self.cheap_header(data)
        except wire.ProtocolError:
            self.counters["parser_reject"] += 1
            return None
        if not self.token_allowed(now):
            return None
        # HELLO key_slot is the only field inspected before HMAC and is used
        # solely as a bounded credential selector. Stage 3 installs CONTROL
        # only, so every other slot is a silent drop rather than an oracle.
        if message["name"] == "HELLO" and data[98] != 0:
            self.counters["hello_reject"] += 1
            return None
        try:
            packet = wire.decode(data, self.key)
        except wire.ProtocolError as error:
            if str(error) == "HMAC":
                self.counters["hmac_fail"] += 1
                self.event("AUTH_FAILURE", category="HMAC")
            else:
                self.counters["parser_reject"] += 1
            return None
        if message["name"] == "HELLO":
            try:
                return self.start_session(packet, address, now)
            except wire.ProtocolError as error:
                self.counters["hello_reject"] += 1
                self.event("HELLO_REJECTED", category=str(error))
                return None
        if self.session_id is None or address != self.endpoint or packet["session_id"] != self.session_id or packet["controller_boot_id"] != self.boot_id:
            self.counters["parser_reject"] += 1
            return None
        if packet["sequence"] <= self.last_rx_sequence:
            self.counters["replay_reject"] += 1
            self.event("STALE_REPLAY_REJECTED")
            return None
        name = packet["message"]
        if name not in ("PING", "COMMAND"):
            self.counters["parser_reject"] += 1
            return None
        self.last_rx_sequence = packet["sequence"]
        self.last_rx_time = now
        if name == "PING":
            self.counters["pong"] += 1
            return self.send_session("PONG", packet["payload"], now)
        if self.authority.command(self.boot_id, self.session_id, self.endpoint,
                                  packet["sequence"], int(now * 1000000), packet["payload"]) != RESULT_OK:
            self.end_session("controller_rejected_command")
            return None
        self.last_command_time = now
        self.last_command_sequence = packet["sequence"]
        self.counters["command_scope_zero"] += 1
        return None

    def telemetry(self, now):
        if self.session_id is None:
            return None
        age = 0xffffffff if self.last_command_time is None else min(0xffffffff, int((now - self.last_command_time) * 1000))
        battery_mv = 0
        try:
            battery_mv = min(65535, int(pathlib.Path("/sys/class/power_supply/lego-ev3-battery/voltage_now").read_text().strip()) // 1000)
        except (OSError, ValueError):
            pass
        status = STATUS_BUNDLE_VALID
        loop_flags = LOOP_NETWORK_BACKPRESSURE if self.counters["rx_drop"] else 0
        payload = wire.telemetry_payload(self.robot_id, self.build_id_bytes, self.bundle_hash, b"\0" * 32,
                                         CONNECTED_UNREFERENCED, FAULT_NONE, status, b"\0" * 16,
                                         self.last_command_sequence, age, (0.0, 0.0, 0.0),
                                         (0.0, 0.0, 0.0), 0.0, 0, battery_mv, loop_flags,
                                         "UNSELECTED", PAYLOAD_UNKNOWN, 1)
        self.counters["telemetry"] += 1
        return self.send_session("TELEMETRY", payload, now)

    def status(self):
        payload = {"schema_version": 1, "profile": "stage3-network-only", "robot_id": self.robot_id,
                   "port": self.port, "controller_boot_id": self.boot_id.hex() if self.boot_id else None,
                   "session_active": self.session_id is not None, "actuator_scope_mask": 0,
                   "qualification_only": True, "counters": self.counters}
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(self.status_path))


def run(args):
    config = read_json(args.config)
    bundle = read_json(args.bundle)
    manifest = read_json(args.manifest)
    authority = ControllerIpcAuthority(args.ipc_own, args.ipc_controller)
    server = Stage3Server(config, bundle, manifest, load_key(args.control_key), args.boot_id,
                          args.status, authority)
    while server.boot_id is None:
        try:
            server.read_boot_id()
        except (OSError, ValueError):
            time.sleep(.05)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16384)
    sock.bind((args.bind, server.port))
    sock.setblocking(False)
    server.status()
    server.event("UDP_LISTENER_STARTED", address=args.bind, port=server.port)
    server.event("NETWORK_READY", port=server.port)
    systemd_ready("UDP listener active on port " + str(server.port))
    next_identity = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= next_identity:
            try:
                server.read_boot_id()
            except (OSError, ValueError):
                server.end_session("controller_identity_unavailable")
            next_identity = now + .25
        readable, unused_write, unused_error = select.select([sock], [], [], .01)
        if readable:
            for unused in range(32):
                try:
                    data, address = sock.recvfrom(1025)
                except BlockingIOError:
                    break
                response = server.process(data, address, now)
                if response is not None:
                    sock.sendto(response, address)
        if server.session_id is not None and now - server.last_rx_time > server.session_stale:
            server.end_session("timeout")
        if server.session_id is not None and now >= server.next_telemetry:
            data = server.telemetry(now)
            if data is not None:
                sock.sendto(data, server.endpoint)
            server.next_telemetry = now + .05
        if now >= server.next_status:
            server.status()
            server.next_status = now + 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/opt/phantom/current/config.generated.json")
    parser.add_argument("--bundle", default="/opt/phantom/current/commissioning-bundle.generated.json")
    parser.add_argument("--manifest", default="/opt/phantom/current/build-manifest.json")
    parser.add_argument("--control-key", default="/var/lib/phantom/secrets/control.psk")
    parser.add_argument("--boot-id", default="/run/phantom/controller/boot-id")
    parser.add_argument("--status", default="/run/phantom/network-status.json")
    parser.add_argument("--ipc-own", default="/run/phantom/network/controller.sock")
    parser.add_argument("--ipc-controller", default="/run/phantom/controller/network.sock")
    parser.add_argument("--bind", default="0.0.0.0")
    try:
        run(parser.parse_args())
    except ValueError as error:
        detail = str(error).lower()
        event = "BUNDLE_MISMATCH" if "bundle" in detail else "CONFIG_MISMATCH"
        print(json.dumps({"event": event, "category": "startup_validation"},
                         sort_keys=True, separators=(",", ":")), flush=True)
        raise


if __name__ == "__main__":
    main()
