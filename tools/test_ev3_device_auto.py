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


if __name__ == "__main__":
    unittest.main()
