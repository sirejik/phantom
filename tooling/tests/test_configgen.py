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


def robot_fixture():
    """Synthetic test input, never a production source or measured default."""
    return {"schema_version": 1, "revision": 1, "bundle_id": "test-unqualified",
            "mechanical_revision": "test-fixture", "qualification_status": "UNQUALIFIED",
            "qualification_only": False, "qualification_evidence_manifest_hash": "0" * 64,
            "actuator_scope_mask": 15, "safety_observation_mask": 15,
            "robot_geometry": {"branch_sign": 1, "l1_m": None, "l2_m": None,
                               "shoulder_height_m": None, "marker_mounts": {}},
            "drive_calibration": {"revision": 1, "status": "MEASURED_REQUIRED",
                                  "axes": {axis: None for axis in "ABCD"}},
            "collision_model": {"revision": 1, "status": "MEASURED_REQUIRED", "primitives": []},
            "joint_safe_sets": {"format": "GRID3D_V1", "status": "MEASURED_REQUIRED", "profiles": {}},
            "payload_profiles": {"status": "MEASURED_REQUIRED", "profiles": {}},
            "safety_envelope": {key: None for key in
                                ("external_power_cut_present", "external_power_cut_tested",
                                 "payload_cog_offset_max_m", "payload_mass_max_kg",
                                 "pinch_exclusion_margin_m", "swept_volume_margin_m",
                                 "tcp_static_moment_max_Nm")}}


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

    def test_non_finite_observed_data_is_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            self.assertRaisesRegex(ValueError, "non-finite", CONFIGGEN.validate_schema,
                                   value, {"type": "number", "minimum": 0})
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "observed.json"
            path.write_text('{"angle":NaN}')
            self.assertRaisesRegex(ValueError, "non-finite", CONFIGGEN.load, path)

    def test_last_key_wins_is_not_used_as_a_resolution(self):
        self.assertRaises(ValueError, CONFIGGEN._reject_duplicates, [("k", 1), ("k", 2)])


class SchemaValidatorTests(unittest.TestCase):
    def test_json_const_and_enum_do_not_confuse_booleans_with_numbers(self):
        for value, rule in ((True, {"const": 1}), (False, {"const": 0}),
                            (1, {"const": True}), (True, {"enum": [-1, 1]}),
                            ({"enabled": 1}, {"const": {"enabled": True}})):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                CONFIGGEN.validate_schema(value, rule)
        CONFIGGEN.validate_schema(1.0, {"const": 1})
        CONFIGGEN.validate_schema(True, {"enum": [True, False]})

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


class AdmissionTests(unittest.TestCase):
    def test_removing_calibration_does_not_bypass_schema(self):
        obj = robot_fixture()
        del obj["drive_calibration"]["axes"]["B"]
        self.assertRaisesRegex(ValueError, "missing B", CONFIGGEN.validate_schema,
                               obj, schema("commissioning_bundle"))

    def test_geometry_range_is_checked_at_its_source(self):
        obj = robot_fixture()
        obj["robot_geometry"]["l1_m"] = -1
        self.assertRaisesRegex(ValueError, "minimum", CONFIGGEN.validate_schema,
                               obj, schema("commissioning_bundle"))

    def test_unfilled_values_block_release_without_a_registry(self):
        bundle = robot_fixture()
        blocked = CONFIGGEN.qualification_blockers(bundle)
        self.assertIn("commissioning_bundle.json#/robot_geometry/l1_m", blocked)
        self.assertFalse((ROOT / "config/shared/measured-parameters.json").exists())

    def test_measurement_is_read_from_its_owner(self):
        bundle = robot_fixture()
        bundle["robot_geometry"]["l1_m"] = 0.215
        self.assertNotIn("commissioning_bundle.json#/robot_geometry/l1_m",
                         CONFIGGEN.qualification_blockers(bundle))

    def test_qualified_label_does_not_replace_missing_values(self):
        bundle = robot_fixture()
        bundle["qualification_status"] = "QUALIFIED"
        bundle["qualification_evidence_manifest_hash"] = "a" * 64
        self.assertTrue(CONFIGGEN.qualification_blockers(bundle))

    def test_quest_receives_only_bundle_identity(self):
        objects = CONFIGGEN.source_objects()
        self.assertNotIn("commissioning_bundle", objects["quest"])
        self.assertNotIn("qualification_evidence_manifest_hash", objects["quest"]["qualification"])
        self.assertNotIn("drive_calibration", objects["quest"])

class CompositionTests(unittest.TestCase):
    def test_unknown_host_setting_is_rejected(self):
        original = CONFIGGEN.load
        def changed(path):
            value = original(path)
            if path.parent.name == "ev3" and path.name == "project.json":
                value["build"] = {"toolchain": {"unused_option": True}}
            return value
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            self.assertRaisesRegex(ValueError, "unexpected/missing", CONFIGGEN.source_objects)

    def test_profile_contract_is_derived_and_cannot_be_overridden(self):
        original = CONFIGGEN.load
        for component, fields in (("ev3", {"qualification_only": False,
                                           "actuator_scope_mask": 15,
                                           "safety_observation_mask": 15}),
                                  ("quest", {"qualification": {"required_user_inputs": "FULL_ARM"}})):
            def changed(path):
                value = original(path)
                if path.parent.name == component and path.name == "project.json":
                    value["runtime"].update(fields)
                return value
            with patch.object(CONFIGGEN, "load", side_effect=changed):
                self.assertRaisesRegex(ValueError, "derived fields overridden", CONFIGGEN.source_objects)
        objects = CONFIGGEN.source_objects()
        for name, component in CONFIGGEN.VARIANTS:
            obj = objects[name] if component == "ev3" else objects[name]["qualification"]
            diagnostic = name.endswith("network-only")
            self.assertEqual(obj["qualification_only"], diagnostic)
            self.assertEqual(obj["actuator_scope_mask"], 0 if diagnostic else 15)
            self.assertEqual(obj["safety_observation_mask"], 0 if diagnostic else 15)
            if component == "quest":
                self.assertEqual(obj["required_user_inputs"], "NONE" if diagnostic else "FULL_ARM")

    def test_setting_repeated_in_optional_profiles_must_move_to_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            for profile in ("release", "diagnostic"):
                (root / "config/ev3" / (profile + ".json")).write_text(
                    '{"runtime":{"network":{"command_timeout_ms":200}}}', encoding="utf-8")
            with patch.object(CONFIGGEN, "ROOT", root):
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
                value["network"]["port_udp"] = 32000
            return value
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            sources = CONFIGGEN.source_objects()
        for suffix in ("", "-network-only"):
            for name, port in (("ev3", "listen_port_udp"), ("quest", "default_port")):
                self.assertEqual(sources[name + suffix]["robot_id"], "phantom01")
                self.assertEqual(sources[name + suffix]["network"][port], 32000)

    def test_build_never_composes_robot_measurements(self):
        sources = CONFIGGEN.source_objects()
        self.assertEqual(set(sources), {"ev3", "ev3-network-only", "quest", "quest-network-only"})
        for obj in sources.values():
            for field in ("drive_calibration", "robot_geometry", "collision_model", "qualification_evidence_manifest_hash"):
                self.assertNotIn(field, obj)
        self.assertFalse((ROOT / "config/shared/robot.json").exists())

    def test_robot_data_cannot_be_reintroduced_as_project_settings(self):
        original = CONFIGGEN.load
        def changed(path):
            obj = original(path)
            if path == ROOT / "config/ev3/project.json":
                obj["commissioning"] = robot_fixture()
            return obj
        with patch.object(CONFIGGEN, "load", side_effect=changed):
            self.assertRaisesRegex(ValueError, "project sections", CONFIGGEN.source_objects)

    def test_bootstrap_has_no_measurements_or_actuator_authority(self):
        descriptor = CONFIGGEN.bootstrap_descriptor()
        CONFIGGEN.validate_schema(descriptor, CONFIGGEN.load(ROOT / "schemas/ev3/network-only-session.schema.json"))
        self.assertEqual(descriptor["actuator_scope_mask"], 0)
        self.assertEqual(descriptor["safety_observation_mask"], 0)
        self.assertNotIn("robot_geometry", descriptor)
        self.assertNotIn("drive_calibration", descriptor)

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
    def test_unchanged_candidate_is_not_replaced_while_in_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root):
                CONFIGGEN.prepare()
                with patch("os.replace", side_effect=PermissionError("file in use")):
                    CONFIGGEN.prepare()
                pair = root / "config/shared/pair.json"
                value = json.loads(pair.read_text());value["network"]["port_udp"] = 32000
                pair.write_text(json.dumps(value), encoding="utf-8")
                with patch("os.replace", side_effect=PermissionError("file in use")):
                    self.assertRaises(PermissionError, CONFIGGEN.prepare)

    def test_late_validation_failure_does_not_publish_partial_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root):
                CONFIGGEN.prepare()
                outputs = list((root / "build/config").rglob("*.json"))
                before = {path: path.read_bytes() for path in outputs}
                pair = root / "config/shared/pair.json"
                value = json.loads(pair.read_text());value["network"]["port_udp"] = 32000
                pair.write_text(json.dumps(value), encoding="utf-8")
                profile = root / "config/quest/release.json"
                value = {"runtime": {"network": {"undeclared": 42}}}
                profile.write_text(json.dumps(value), encoding="utf-8")
                self.assertRaisesRegex(ValueError, "additional properties", CONFIGGEN.prepare)
                self.assertEqual(before, {path: path.read_bytes() for path in outputs})

    def test_check_requires_no_build_outputs_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root), patch.object(sys, "argv", ["configgen", "--check"]):
                CONFIGGEN.main()
            self.assertFalse((root / "build").exists())

    def test_documentation_does_not_affect_config_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root):
                before, _ = CONFIGGEN.compile_configs()
                (root / "docs").mkdir()
                (root / "docs/requirements.md").write_bytes(b"changed documentation\n")
                self.assertEqual(before, CONFIGGEN.compile_configs()[0])

    def test_manifest_reports_actual_blockers_and_ipc_identity(self):
        _, manifest = CONFIGGEN.compile_configs()
        self.assertNotIn("measured_gates", manifest)
        self.assertNotIn("qualification_blockers", manifest)
        self.assertEqual(manifest["runtime_admission"], "ROBOT_DATA_REQUIRED_FOR_MOTION")
        self.assertEqual(manifest["bootstrap_descriptor_hash"], CONFIGGEN.bootstrap_hash())
        self.assertRegex(manifest["ipc_schema_hash"], "^[0-9a-f]{64}$")


class RuntimeLifecycleTests(unittest.TestCase):
    def test_build_outputs_exclude_robot_data_and_test_fixtures(self):
        outputs, _ = CONFIGGEN.compile_configs()
        self.assertEqual(len(outputs), 5)
        self.assertFalse(any("commissioning-bundle" in str(path) or "test-fixtures" in str(path) for path in outputs))

    def test_software_identity_is_independent_of_external_robot_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            with patch.object(CONFIGGEN, "ROOT", root):
                before = CONFIGGEN.compile_configs()[0]
                robot = root / "robot-data"
                robot.mkdir()
                (robot / "commissioning.json").write_text(json.dumps(robot_fixture()))
                self.assertEqual(before, CONFIGGEN.compile_configs()[0])
                (robot / "commissioning.json").write_text("corrupt device data")
                self.assertEqual(before, CONFIGGEN.compile_configs()[0])

    def test_test_preparation_preserves_persistent_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(ROOT / "config", root / "config")
            shutil.copytree(ROOT / "schemas", root / "schemas")
            shutil.copytree(ROOT / "protocol/generated", root / "protocol/generated")
            (root / "robot-data").mkdir()
            robot = root / "robot-data/commissioning.json"
            robot.write_bytes(b"existing robot-owned data")
            with patch.object(CONFIGGEN, "ROOT", root):
                CONFIGGEN.prepare(for_tests=True)
            self.assertEqual(robot.read_bytes(), b"existing robot-owned data")
            self.assertTrue((root / "build/config/test-fixtures/network-only-session.json").is_file())

    def test_startup_reference_schema_rejects_missing_initial_angle(self):
        ref = {"schema_version": 1, "controller_boot_id": "a" * 32,
               "commissioning_bundle_hash": "b" * 64, "safety_observation_mask": 1,
               "captured_monotonic_us": 100,
               "joint_references": {"A": {"reference_encoder_count": 12,
                                          "reference_physical_angle_rad": 0.3, "sample_id": 1},
                                    "B": None, "C": None}, "gripper_reference": None}
        owned = CONFIGGEN.load(ROOT / "schemas/ev3/startup-reference.schema.json")
        CONFIGGEN.validate_schema(ref, owned)
        del ref["joint_references"]["A"]["reference_physical_angle_rad"]
        self.assertRaisesRegex(ValueError, "reference_physical_angle_rad", CONFIGGEN.validate_schema, ref, owned)


if __name__ == "__main__":
    unittest.main()
