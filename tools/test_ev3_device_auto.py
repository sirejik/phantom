#!/usr/bin/env python3
"""Regression tests for the EV3 on-device acceptance runner."""
import importlib.util
import pathlib
import sys
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


if __name__ == "__main__":
    unittest.main()
