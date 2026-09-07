#!/usr/bin/env python3
"""Regression tests for the EV3 on-device acceptance runner."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    sys.modules.setdefault("grp", types.ModuleType("grp"))
SPEC = importlib.util.spec_from_file_location(
    "phantom_ev3_device_auto", str(ROOT / "deploy" / "scripts" / "device-auto.py"))
DEVICE_AUTO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEVICE_AUTO)


class WallClockStateTests(unittest.TestCase):
    def test_reproducible_manifest_does_not_need_build_timestamp(self):
        manifest = {
            "schema_version": 2,
            "source_date_epoch_or_reproducible_epoch": 0,
        }
        status, unused_detail, evidence = DEVICE_AUTO.wall_clock_state(
            1788706800, "NTP synchronized: no\n")

        self.assertNotIn("built_at", manifest)
        self.assertEqual("PASS", status)
        self.assertEqual("no", evidence["ntp_synchronized"])
        self.assertEqual("HOST_CORRELATION_REQUIRED", evidence["chronology_trust"])

    def test_synchronised_ntp_is_trusted(self):
        status, unused_detail, evidence = DEVICE_AUTO.wall_clock_state(
            1788706800, "NTP synchronized: yes\n")

        self.assertEqual("PASS", status)
        self.assertEqual("NTP_SYNCHRONIZED", evidence["chronology_trust"])

    def test_bounded_timedate_timeout_requires_host_correlation(self):
        status, unused_detail, evidence = DEVICE_AUTO.wall_clock_state(
            1788706800, "", "TIMEOUT")

        self.assertEqual("PASS", status)
        self.assertEqual("unknown", evidence["ntp_synchronized"])
        self.assertEqual("TIMEOUT", evidence["timedate_query_status"])
        self.assertEqual("HOST_CORRELATION_REQUIRED", evidence["chronology_trust"])

    def test_uninitialised_calendar_fails_closed(self):
        status, unused_detail, evidence = DEVICE_AUTO.wall_clock_state(
            42, "NTP synchronized: no\n")

        self.assertEqual("FAIL", status)
        self.assertEqual("HOST_CORRELATION_REQUIRED", evidence["chronology_trust"])


class ZeroOutputAuditTests(unittest.TestCase):
    """The Stage-3 zero-output proof must rest on observed state, not on a counter
    that the network worker never increments."""

    SOURCE = (ROOT / "deploy" / "scripts" / "device-auto.py").read_text(encoding="utf-8")

    def test_runner_does_not_read_the_removed_tautological_counter(self):
        # It always read zero, so the audit passed whether or not the process
        # could reach a motor. Reading it now would make the check fail closed
        # for the wrong reason: the key is simply absent from the status file.
        self.assertNotIn('counters.get("nonzero_motor_writes")', self.SOURCE)

    def test_audit_uses_sysfs_dac_and_a_counter_that_is_actually_written(self):
        audit = self.SOURCE[self.SOURCE.index("ev3-stage3-zero-output-audit") - 900:]
        audit = audit[:audit.index("return write_report")]
        self.assertIn("zero_state(motors)", audit)
        self.assertIn("motor_write_attempts_rejected", audit)
        self.assertIn('access_checks["phantom-net-motor-write-denied"]', audit)

    def test_zero_state_rejects_a_moving_or_coasting_motor(self):
        class Node(object):
            def __init__(self, values):
                self.values = values

            def __truediv__(self, name):
                return self.values[name]

        stationary = {"duty_cycle_sp": "0", "duty_cycle": "0", "speed": "0",
                      "state": "", "stop_action": "brake"}
        original = DEVICE_AUTO.text
        try:
            DEVICE_AUTO.text = lambda value: value
            ok, unused = DEVICE_AUTO.zero_state({"outA": Node(dict(stationary))})
            self.assertTrue(ok)
            for field, bad in (("speed", "120"), ("duty_cycle", "40"),
                               ("state", "running"), ("stop_action", "coast")):
                values = dict(stationary)
                values[field] = bad
                ok, unused = DEVICE_AUTO.zero_state({"outA": Node(values)})
                self.assertFalse(ok, field)
        finally:
            DEVICE_AUTO.text = original


class StatusJsonTests(unittest.TestCase):
    def test_empty_status_file_is_structured_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "network-status.json"
            path.write_text("", encoding="utf-8")
            value, evidence = DEVICE_AUTO.read_json_object(path)

        self.assertIsNone(value)
        self.assertEqual("EMPTY", evidence["category"])

    def test_malformed_status_file_is_structured_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "network-status.json"
            path.write_text("{", encoding="utf-8")
            value, evidence = DEVICE_AUTO.read_json_object(path)

        self.assertIsNone(value)
        self.assertEqual("MALFORMED", evidence["category"])
        self.assertIn("detail", evidence)

    def test_valid_status_object_is_returned(self):
        expected = {"counters": {"hmac_fail": 1, "replay_reject": 1}}
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "network-status.json"
            path.write_text(json.dumps(expected), encoding="utf-8")
            value, evidence = DEVICE_AUTO.read_json_object(path)

        self.assertEqual(expected, value)
        self.assertIsNone(evidence)

    def test_missing_status_file_is_structured_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            value, evidence = DEVICE_AUTO.read_json_object(pathlib.Path(directory) / "missing.json")

        self.assertIsNone(value)
        self.assertEqual("MISSING", evidence["category"])

    def test_boot_id_validation_prevents_identifier_length_cascade(self):
        self.assertFalse(DEVICE_AUTO.valid_boot_id(""))
        self.assertFalse(DEVICE_AUTO.valid_boot_id("gg" * 16))
        self.assertTrue(DEVICE_AUTO.valid_boot_id("42" * 16))


class DeploymentRegressionTests(unittest.TestCase):
    def test_controller_systemd_sandbox_allows_motor_lease_path(self):
        unit = (ROOT / "deploy" / "systemd" / "phantom-controller.service").read_text(encoding="utf-8")
        writable = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
        self.assertIn("/run/phantom/motor-control.lock", writable.split("=", 1)[1].split())

    def test_installer_checks_each_required_service_and_restores_metadata(self):
        installer = (ROOT / "deploy" / "scripts" / "install-release").read_text(encoding="utf-8")
        self.assertIn("for unit in $runtime_services", installer)
        self.assertIn('systemctl is-active --quiet "$unit"', installer)
        self.assertNotIn("systemctl is-active --quiet phantom-safety.service phantom-wifi-autoconnect.service", installer)
        self.assertIn('install_runtime_metadata "$previous"', installer)
        self.assertIn('runtime_metadata_matches "$previous"', installer)
        self.assertIn("network_group=$(sed -n 's/^Group=//p'", installer)
        self.assertIn('chown "root:$network_group"', installer)
        self.assertIn("! -name motor-control.lock", installer)
        rollback = installer[installer.index("rollback(){"):installer.index("fail_with_rollback(){")]
        self.assertIn("all_services_active", rollback)

    def test_runner_does_not_probe_network_after_systemd_prerequisite_failure(self):
        source = (ROOT / "deploy" / "scripts" / "device-auto.py").read_text(encoding="utf-8")
        gated = source[source.index("if not runtime_services_ok:"):source.index("final_safe, final_evidence")]
        self.assertIn('add("ev3-dns-sd-stage3", "NOT_RUN"', gated)
        self.assertIn('add("ev3-udp-session-stage3", "NOT_RUN"', gated)
        self.assertIn('add("ev3-network-security-stage3", "NOT_RUN"', gated)

    def test_runner_preserves_loaded_manifest_on_unhandled_failure(self):
        source = (ROOT / "deploy" / "scripts" / "device-auto.py").read_text(encoding="utf-8")
        self.assertIn("report_manifest = manifest", source)
        self.assertIn("write_report(report_manifest)", source)


if __name__ == "__main__":
    unittest.main()
