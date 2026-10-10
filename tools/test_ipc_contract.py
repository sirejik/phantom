#!/usr/bin/env python3
"""Cross-implementation checks for the EV3-local IPC contract.

Three encodings used to exist for the same 120/64-byte structures: the Python
worker, the C++ boundary and the C++ test builder. They now all derive from
protocol/ipc_schema.yaml. This module proves the Python side matches the shared
golden vectors and the generated C++ header; ev3/tests/ipc_vector_tests.cpp
proves the same for C++, so an offset change cannot pass unnoticed on either
side.
"""
import hashlib
import json
import pathlib
import re
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "protocol" / "generated"))
import ipc_layout  # noqa: E402

VECTORS = json.loads((ROOT / "protocol" / "golden_vectors" / "ipc_v1.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "protocol" / "ipc_schema.yaml").read_text(encoding="utf-8"))
CPP_HEADER = (ROOT / "protocol" / "generated" / "ipc_constants.hpp").read_text(encoding="utf-8")

STRUCTS = {
    "ControllerRequestV1": (ipc_layout.CONTROLLER_REQUEST, ipc_layout.CONTROLLER_REQUEST_OFFSETS,
                            ipc_layout.CONTROLLER_REQUEST_BYTES),
    "ControllerReplyV1": (ipc_layout.CONTROLLER_REPLY, ipc_layout.CONTROLLER_REPLY_OFFSETS,
                          ipc_layout.CONTROLLER_REPLY_BYTES),
    "ControllerTelemetrySnapshotV1": (ipc_layout.CONTROLLER_TELEMETRY_SNAPSHOT,
                                      ipc_layout.CONTROLLER_TELEMETRY_SNAPSHOT_OFFSETS,
                                      ipc_layout.CONTROLLER_TELEMETRY_SNAPSHOT_BYTES),
}


def cpp_constant(name):
    match = re.search(r"constexpr std::size_t %s = (\d+);" % re.escape(name), CPP_HEADER)
    return None if match is None else int(match.group(1))


def cpp_prefix(message):
    return "k" + message.replace("V1", "")


def title(name):
    return "".join(part.title() for part in name.lower().split("_"))


class GoldenVectorTests(unittest.TestCase):
    def test_every_schema_message_has_a_vector(self):
        names = {vector["name"] for vector in VECTORS["vectors"]}
        self.assertEqual({message["name"] for message in SCHEMA["messages"]}, names)
        self.assertEqual(set(STRUCTS), names)

    def test_vector_bytes_match_their_declared_hash_and_length(self):
        for vector in VECTORS["vectors"]:
            raw = bytes.fromhex(vector["bytes_hex"])
            self.assertEqual(vector["length"], len(raw), vector["name"])
            self.assertEqual(vector["sha256"], hashlib.sha256(raw).hexdigest(), vector["name"])

    def test_python_struct_sizes_and_offsets_match_the_vectors(self):
        for vector in VECTORS["vectors"]:
            packer, offsets, size = STRUCTS[vector["name"]]
            self.assertEqual(vector["length"], size, vector["name"])
            self.assertEqual(vector["length"], packer.size, vector["name"])
            raw = bytes.fromhex(vector["bytes_hex"])
            for field in vector["fields"]:
                self.assertIn(field["name"], offsets, vector["name"] + "." + field["name"])
                self.assertEqual(field["offset"], offsets[field["name"]],
                                 vector["name"] + "." + field["name"] + " offset")
                self.assertEqual(bytes.fromhex(field["hex"]),
                                 raw[field["offset"]:field["offset"] + field["size"]],
                                 vector["name"] + "." + field["name"] + " bytes")

    def test_python_round_trips_every_vector(self):
        for vector in VECTORS["vectors"]:
            packer, unused_offsets, unused_size = STRUCTS[vector["name"]]
            raw = bytes.fromhex(vector["bytes_hex"])
            self.assertEqual(raw, packer.pack(*packer.unpack(raw)), vector["name"])


class GeneratedHeaderAgreementTests(unittest.TestCase):
    def test_cpp_header_declares_the_same_sizes(self):
        for message in SCHEMA["messages"]:
            declared = cpp_constant(cpp_prefix(message["name"]) + "Bytes")
            self.assertIsNotNone(declared, message["name"])
            self.assertEqual(message["length"], declared, message["name"])

    def test_cpp_header_declares_the_same_field_offsets(self):
        checked = 0
        for vector in VECTORS["vectors"]:
            prefix = cpp_prefix(vector["name"])
            for field in vector["fields"]:
                offset = cpp_constant(prefix + "Offset" + title(field["name"]))
                size = cpp_constant(prefix + "Size" + title(field["name"]))
                self.assertIsNotNone(offset, vector["name"] + "." + field["name"])
                self.assertEqual(field["offset"], offset, vector["name"] + "." + field["name"])
                self.assertEqual(field["size"], size, vector["name"] + "." + field["name"])
                checked += 1
        self.assertGreaterEqual(checked, 40)

    def test_message_type_numbers_agree(self):
        for name, value in SCHEMA["message_types"].items():
            self.assertEqual(value, ipc_layout.MESSAGE_TYPES[name])
            self.assertIn("  %s = %d," % (name, value), CPP_HEADER)


class WorkerUsesGeneratedLayoutTests(unittest.TestCase):
    def test_request_packing_places_fields_at_generated_offsets(self):
        offsets = ipc_layout.CONTROLLER_REQUEST_OFFSETS
        packed = ipc_layout.CONTROLLER_REQUEST.pack(
            ipc_layout.MAGIC, ipc_layout.IPC_VERSION, ipc_layout.MESSAGE_TYPES["SESSION_OPEN"], 0,
            b"B" * 16, 77, b"S" * 16, 0, 0, 4, 0, bytes((127, 0, 0, 1)), struct.pack(">H", 30470),
            0, b"\0" * 16, 0, 1234, b"\0" * 24)
        self.assertEqual(ipc_layout.CONTROLLER_REQUEST_BYTES, len(packed))
        self.assertEqual(b"PHIP", packed[offsets["magic"]:offsets["magic"] + 4])
        self.assertEqual(4, packed[offsets["remote_family"]])
        self.assertEqual(struct.pack(">H", 30470),
                         packed[offsets["remote_port_network_order"]:offsets["remote_port_network_order"] + 2])
        self.assertEqual(77, struct.unpack_from("<Q", packed, offsets["session_generation"])[0])
        self.assertEqual(1234, struct.unpack_from("<Q", packed, offsets["rx_monotonic_us"])[0])
        self.assertEqual(b"\0" * 24, packed[offsets["command_payload"]:])


if __name__ == "__main__":
    unittest.main()
