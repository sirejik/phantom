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

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phantom_configgen", str(ROOT / "tools" / "configgen.py"))
CONFIGGEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIGGEN)


def source(name):
    return CONFIGGEN.load(ROOT / "config" / "source" / (name + ".json"))


def schema(name):
    return CONFIGGEN.load(ROOT / "config" / "schema" / (name + ".schema.json"))


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

class GeneratedArtifactTests(unittest.TestCase):
    def test_generator_works_without_documentation_and_is_stable_after_doc_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config/source", root / "config/source")
            shutil.copytree(ROOT / "config/schema", root / "config/schema")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root), patch.object(sys, "argv", ["configgen"]):
                CONFIGGEN.main()
                before = {p.name: p.read_bytes() for p in (root / "config/generated").iterdir()}
                (root / "docs").mkdir()
                (root / "docs/requirements.md").write_bytes(b"changed documentation\n")
                CONFIGGEN.main()
                self.assertEqual(before, {p.name: p.read_bytes() for p in (root / "config/generated").iterdir()})
                with patch.object(sys, "argv", ["configgen", "--check"]):
                    CONFIGGEN.main()

    def test_manifest_publishes_stage_gates_and_ipc_identity(self):
        manifest = json.loads((ROOT / "config" / "generated" / "config-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("measured_gates", manifest)
        self.assertEqual(sorted(CONFIGGEN.STAGE_ORDER), sorted(manifest["measured_gates"]))
        self.assertEqual(manifest["ready_gate"], manifest["measured_gates"]["READY"])
        self.assertRegex(manifest["ipc_schema_hash"], "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
