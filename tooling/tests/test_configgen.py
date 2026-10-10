#!/usr/bin/env python3
"""Boundary tests for the strict PHANTOM configuration gate."""
import copy
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("phantom_configgen", str(ROOT / "tooling" / "internal" / "configgen.py"))
CONFIGGEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGGEN)


def source(name):
    return CONFIGGEN.load_source(name)


def schema(name):
    return CONFIGGEN.load(CONFIGGEN.schema_path(name))


class StrictParsingTests(unittest.TestCase):
    def test_duplicate_mapping_keys_are_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write('{"a":1,"a":2}')
            path = pathlib.Path(handle.name)
        try:
            with self.assertRaises(ValueError) as caught:
                CONFIGGEN.load(path)
            self.assertIn("duplicate mapping key", str(caught.exception))
        finally:
            path.unlink()

    def test_last_key_wins_is_not_used_as_a_resolution(self):
        self.assertRaises(ValueError, CONFIGGEN._reject_duplicates, [("k", 1), ("k", 2)])


class SchemaValidatorTests(unittest.TestCase):
    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaises(ValueError) as caught:
            CONFIGGEN.validate_schema(1, {"type": "integer", "exclusiveMinimum": 0})
        self.assertIn("unsupported schema keywords", str(caught.exception))

    def test_unknown_config_field_is_rejected(self):
        obj = source("ev3-network-only")
        obj["network"]["undeclared_knob"] = 1
        self.assertRaises(ValueError, CONFIGGEN.validate_schema, obj, schema("ev3"))

    def test_missing_required_field_is_rejected(self):
        obj = source("ev3-network-only")
        del obj["safety"]["loop_safe_hold_ms"]
        self.assertRaises(ValueError, CONFIGGEN.validate_schema, obj, schema("ev3"))

    def test_out_of_range_value_is_rejected(self):
        obj = source("ev3-network-only")
        obj["safety"]["controller_heartbeat_timeout_ms"] = 5
        self.assertRaises(ValueError, CONFIGGEN.validate_schema, obj, schema("ev3"))

    def test_quest_network_timings_are_declared(self):
        obj = source("quest")
        for field in ("hello_retry_ms", "hello_max_attempts", "ping_interval_ms",
                      "ping_timeout_ms", "max_missed_pongs", "reconnect_delay_ms"):
            self.assertIn(field, obj["network"])
        CONFIGGEN.validate_schema(obj, schema("quest"))

    def test_array_items_are_validated(self):
        CONFIGGEN.validate_schema([1, 2], {"type": "array", "items": {"type": "integer"}})
        self.assertRaises(ValueError, CONFIGGEN.validate_schema, [1, "x"],
                          {"type": "array", "items": {"type": "integer"}})


class ContractTests(unittest.TestCase):
    def test_loop_thresholds_cannot_exceed_safety_deadlines(self):
        for field,value in (("loop_safe_hold_ms",61),("loop_fault_ms",101)):
            obj=source("ev3-network-only");obj["safety"][field]=value
            with self.assertRaisesRegex(ValueError,"safety deadlines"):
                CONFIGGEN.validate("ev3-network-only",obj)
    def test_loop_thresholds_must_be_two_level(self):
        obj = source("ev3-network-only")
        obj["safety"]["loop_safe_hold_ms"] = obj["safety"]["loop_fault_ms"]
        self.assertRaises(ValueError, CONFIGGEN.validate, "ev3-network-only", obj)

    def test_heartbeat_timeout_must_cover_a_heartbeat_period(self):
        obj = source("ev3-network-only")
        obj["safety"]["controller_heartbeat_rate_hz"] = 20
        obj["safety"]["controller_heartbeat_timeout_ms"] = 40
        self.assertRaises(ValueError, CONFIGGEN.validate, "ev3-network-only", obj)

    def test_release_scope_contract_is_enforced(self):
        obj = source("ev3")
        obj["actuator_scope_mask"] = 7
        self.assertRaises(ValueError, CONFIGGEN.validate, "ev3", obj)

    def test_actuator_scope_must_be_safety_observed(self):
        obj = source("ev3-network-only")
        obj["actuator_scope_mask"] = 8
        self.assertRaises(ValueError, CONFIGGEN.validate, "ev3-network-only", obj)


class MeasuredLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: source(name) for name in (
            "commissioning_bundle", "commissioning_bundle-network-only", "ev3",
            "ev3-network-only", "quest", "quest-network-only")}
        self.measured = source("measured_parameters")

    def test_current_registry_blocks_ready_but_not_build(self):
        gates, blocked = CONFIGGEN.check_measured_registry(self.sources, self.measured)
        self.assertEqual("BLOCKED_UNQUALIFIED_MEASURED_VALUES", gates["READY"])
        self.assertEqual([], blocked["BUILD"])

    def test_a_real_measurement_with_evidence_is_accepted(self):
        measured = copy.deepcopy(self.measured)
        entry = measured["parameters"]["commissioning_bundle.json#/robot_geometry/l1_m"]
        entry["value"] = 0.215
        entry["evidence"] = "results/mechanical/l1-2026-09-07.json"
        gates, blocked = CONFIGGEN.check_measured_registry(self.sources, measured)
        self.assertNotIn("commissioning_bundle.json#/robot_geometry/l1_m", blocked["READY"])
        self.assertEqual("BLOCKED_UNQUALIFIED_MEASURED_VALUES", gates["READY"])

    def test_value_without_evidence_is_rejected(self):
        measured = copy.deepcopy(self.measured)
        measured["parameters"]["commissioning_bundle.json#/robot_geometry/l1_m"]["value"] = 0.215
        with self.assertRaises(ValueError) as caught:
            CONFIGGEN.check_measured_registry(self.sources, measured)
        self.assertIn("value and evidence together", str(caught.exception))

    def test_evidence_without_value_is_rejected(self):
        measured = copy.deepcopy(self.measured)
        measured["parameters"]["commissioning_bundle.json#/robot_geometry/l1_m"]["evidence"] = "x"
        self.assertRaises(ValueError, CONFIGGEN.check_measured_registry, self.sources, measured)

    def test_unresolved_build_stage_parameter_fails_the_generator(self):
        measured = copy.deepcopy(self.measured)
        measured["parameters"]["commissioning_bundle.json#/robot_geometry/l1_m"]["required_before"] = "BUILD"
        with self.assertRaises(ValueError) as caught:
            CONFIGGEN.check_measured_registry(self.sources, measured)
        self.assertIn("required at BUILD", str(caught.exception))

    def test_unregistered_placeholder_is_rejected(self):
        sources = copy.deepcopy(self.sources)
        sources["quest"]["qr"]["required_only_before_ready"] = "MEASURED_REQUIRED"
        self.assertRaises(ValueError, CONFIGGEN.check_measured_registry, sources, self.measured)

class CompositionTests(unittest.TestCase):
    def test_setting_repeated_in_both_profiles_must_move_to_base(self):
        original = CONFIGGEN.load
        def changed(path):
            value = original(path)
            if "profiles" in path.parts and "runtime" in path.parts:
                value["repeated"] = 42
            return value
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            self.assertRaisesRegex(ValueError, "both profiles", CONFIGGEN.source_objects)

    def test_overlay_preserves_null_and_replaces_arrays(self):
        base = {"object": {"keep": 4, "value": 5}, "items": [1, 2]}
        self.assertEqual(CONFIGGEN.overlay(base, {"object": {"value": None}, "items": []}),
                         {"object": {"keep": 4, "value": None}, "items": []})
        self.assertEqual(base["object"]["value"], 5)

    def test_redundant_profile_setting_is_rejected(self):
        self.assertRaisesRegex(ValueError, "redundant", CONFIGGEN.overlay,
                               {"network": {"timeout": 10}}, {"network": {"timeout": 10}})

    def test_shared_and_derived_fields_cannot_be_shadowed(self):
        self.assertRaisesRegex(ValueError, "overridden", CONFIGGEN.inject,
                               {"robot_id": "other"}, {"robot_id": "pair"}, "ev3")

    def test_shared_change_reaches_all_components_and_profiles(self):
        original = CONFIGGEN.load
        def changed(path):
            value = original(path)
            if path.name == "pair.json":
                value["robot_id"] = "another-robot"
                value["network"]["port_udp"] = 32000
            return value
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            sources = CONFIGGEN.source_objects()
        for suffix in ("", "-network-only"):
            for name, port in (("ev3", "listen_port_udp"), ("quest", "default_port")):
                self.assertEqual(sources[name + suffix]["robot_id"], "another-robot")
                self.assertEqual(sources[name + suffix]["network"][port], 32000)

    def test_bundle_hash_is_calculated_for_both_quest_profiles(self):
        sources = CONFIGGEN.source_objects()
        for suffix in ("", "-network-only"):
            digest = __import__('hashlib').sha256(CONFIGGEN.canonical(sources["commissioning_bundle" + suffix])).hexdigest()
            self.assertEqual(sources["quest" + suffix]["commissioning_bundle"]["expected_hash"], digest)

    def test_packet_limits_come_from_the_wire_schema(self):
        original = CONFIGGEN.load
        def changed(path):
            value = original(path)
            if path.name == "wire-schema.json":
                value["max_datagram_bytes"] = 2048
            return value
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            sources = CONFIGGEN.source_objects()
        self.assertEqual(sources["ev3"]["network"]["max_packet_bytes"], 2048)
        self.assertEqual(sources["ev3-network-only"]["network"]["max_payload_bytes"], 1952)


class GeneratedArtifactTests(unittest.TestCase):
    def test_late_validation_failure_does_not_publish_partial_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            outputs = list((root / "config").glob("*/generated/*.json"))
            before = {path: path.read_bytes() for path in outputs}
            pair = root / "config/shared/pair.json"
            value = json.loads(pair.read_text())
            value["robot_id"] = "changed-id"
            pair.write_text(json.dumps(value), encoding="utf-8")
            measured = root / "config/shared/measured-parameters.json"
            value = json.loads(measured.read_text())
            value["parameters"].pop(next(iter(value["parameters"])))
            measured.write_text(json.dumps(value), encoding="utf-8")
            with patch.object(CONFIGGEN, "ROOT", root), patch.object(sys, "argv", ["configgen"]):
                self.assertRaisesRegex(ValueError, "registry mismatch", CONFIGGEN.main)
            self.assertEqual(before, {path: path.read_bytes() for path in outputs})

    def test_generator_works_without_documentation_and_is_stable_after_doc_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root), patch.object(sys, "argv", ["configgen"]):
                CONFIGGEN.main()
                before = {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / "config").rglob("*.json")}
                (root / "docs").mkdir()
                (root / "docs/requirements.md").write_bytes(b"changed documentation\n")
                CONFIGGEN.main()
                self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / "config").rglob("*.json")})
                with patch.object(sys, "argv", ["configgen", "--check"]):
                    CONFIGGEN.main()

    def test_manifest_publishes_stage_gates_and_ipc_identity(self):
        manifest = json.loads((ROOT / "config/shared/generated/manifest.json").read_text(encoding="utf-8"))
        self.assertIn("measured_gates", manifest)
        self.assertEqual(sorted(CONFIGGEN.STAGE_ORDER), sorted(manifest["measured_gates"]))
        self.assertEqual(manifest["ready_gate"], manifest["measured_gates"]["READY"])
        self.assertRegex(manifest["ipc_schema_hash"], "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
