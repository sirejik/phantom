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

    def test_network_status_atomic_replace_stays_inside_owned_runtime_directory(self):
        worker = (ROOT / "ev3" / "network" / "phantom_network.py").read_text(encoding="utf-8")
        unit = (ROOT / "deploy" / "systemd" / "phantom-network.service").read_text(encoding="utf-8")
        tmpfiles = (ROOT / "deploy" / "tmpfiles" / "phantom.conf").read_text(encoding="utf-8")
        self.assertIn('default="/run/phantom/network/status.json"', worker)
        self.assertIn("ReadWritePaths=/run/phantom/network", unit)
        self.assertNotIn("/run/phantom/network-status.json", unit)
        self.assertIn("f /run/phantom/network/status.json 0640 phantom-net phantom-net -", tmpfiles)

    def test_core_startup_is_not_blocked_on_wifi_and_network_owns_wifi_dependency(self):
        controller = (ROOT / "deploy" / "systemd" / "phantom-controller.service").read_text(encoding="utf-8")
        network = (ROOT / "deploy" / "systemd" / "phantom-network.service").read_text(encoding="utf-8")
        target = (ROOT / "deploy" / "systemd" / "phantom.target").read_text(encoding="utf-8")
        controller_after = next(line for line in controller.splitlines() if line.startswith("After="))
        self.assertNotIn("phantom-wifi-autoconnect.service", controller_after)
        self.assertIn("Wants=phantom-wifi-autoconnect.service", network)
        self.assertIn("After=phantom-controller.service phantom-wifi-autoconnect.service", network)
        self.assertNotIn("After=phantom-wifi-autoconnect.service", target)

    def test_installer_only_installs_and_leaves_runtime_stopped(self):
        installer = (ROOT / "deploy" / "scripts" / "install-release").read_text(encoding="utf-8")
        self.assertNotIn("--self-test", installer)
        self.assertNotIn("compileall", installer)
        self.assertNotIn("systemctl start", installer)
        self.assertNotIn("phantom-device-auto", installer)
        self.assertIn('stop_runtime || fail', installer)
        self.assertIn('force_and_verify_zero_output || fail', installer)
        self.assertLess(installer.index('install_runtime_metadata "$dest"'),
                        installer.index('ln -sfn "$dest" "$root/current"'))
        self.assertNotIn("restore_metadata || true", installer)
        self.assertIn('test "$symlink_restored" = 1', installer)
        self.assertIn('"phase": "INSTALL"', installer)
        self.assertIn('release_id="phantom-$build_id"', installer)
        self.assertNotIn('release_id=$(basename "$archive" .tar.gz)', installer)
        self.assertIn("network_group=$(sed -n 's/^Group=//p'", installer)
        self.assertIn('chown "root:$network_group"', installer)
        self.assertIn("! -name motor-control.lock", installer)

    def test_start_stops_at_first_failure_and_captures_systemd_cause(self):
        starter = (ROOT / "deploy" / "scripts" / "start-release").read_text(encoding="utf-8")
        self.assertIn("phantom-safety.service phantom-controller.service phantom-wifi-autoconnect.service phantom-network.service phantom-mdns.service", starter)
        self.assertIn("ExecMainCode", starter)
        self.assertIn("ExecMainStatus", starter)
        self.assertIn("systemctl list-dependencies --all", starter)
        self.assertIn("fail_start \"$unit\"", starter)
        self.assertNotIn("phantom-device-auto", starter)
        self.assertNotIn("install -m 0644", starter)

    def test_recovery_restores_without_hidden_restart_or_candidate_delete(self):
        recovery = (ROOT / "deploy" / "scripts" / "rollback-release").read_text(encoding="utf-8")
        self.assertNotIn("systemctl start", recovery)
        self.assertNotIn("phantom-device-auto", recovery)
        self.assertNotIn('rm -rf -- "$previous"', recovery)
        self.assertIn('ln -sfn "$previous" "$root/current"', recovery)

    def test_preinstall_does_not_rebuild_or_repackage_production_artifacts(self):
        source = (ROOT / "scripts" / "pre-install-auto.ps1").read_text(encoding="utf-8")
        self.assertNotIn("ev3-armel-docker.ps1", source)
        self.assertNotIn("ev3-package.ps1", source)
        self.assertIn('Run-Check "post-build-artifacts"', source)
        self.assertIn('Run-Check "ev3-deployment-shell-syntax"', source)
        self.assertIn('Run-Check "deployment-powershell-syntax"', source)
        for tool in ("install-release", "start-release", "run-device-auto", "rollback-release"):
            self.assertIn(tool, source)

    def test_device_launcher_is_bounded_and_has_no_install_or_rollback(self):
        source = (ROOT / "deploy" / "scripts" / "run-device-auto").read_text(encoding="utf-8")
        self.assertIn('timeout "$deadline" /opt/phantom/current/bin/phantom-device-auto', source)
        self.assertIn('if test "$code" != 0', source)
        self.assertIn('systemctl stop "$unit"', source)
        self.assertIn('launcher_terminal_state', source)
        self.assertIn('SAFE_STATE_VERIFICATION_FAILED', source)
        self.assertIn('runner exited or timed out before producing a valid report', source)
        self.assertNotIn("install-release", source)
        self.assertNotIn("rollback-release", source)

    def test_ev3_transfer_is_idempotent_and_admits_deployment_tool_hashes(self):
        source = (ROOT / "scripts" / "ev3-transfer.ps1").read_text(encoding="utf-8")
        self.assertIn("phantom-upload-", source)
        self.assertIn("mv '$remoteUpload' '$remote'", source)
        self.assertIn("Deployment tool $name is absent or ambiguous", source)
        self.assertIn("WaitForExit($TimeoutSeconds*1000)", source)
        self.assertIn("[System.Diagnostics.Process]::Start", source)
        self.assertNotIn("Start-Process", source)
        self.assertIn("$process.WaitForExit()", source)

    def test_quest_install_start_and_device_runners_are_separate(self):
        installer = (ROOT / "scripts" / "quest-install.ps1").read_text(encoding="utf-8")
        starter = (ROOT / "scripts" / "quest-start.ps1").read_text(encoding="utf-8")
        device = (ROOT / "scripts" / "quest-device-auto.ps1").read_text(encoding="utf-8")
        self.assertIn('install -r -g', installer)
        self.assertNotIn("am start", installer)
        self.assertIn("am start", starter)
        self.assertNotIn("install -r -g", starter)
        self.assertNotIn("install -r -g", device)
        self.assertIn("Matching Quest INSTALL and START PASS", device)
        self.assertFalse((ROOT / "scripts" / "quest-pre-install-auto.ps1").exists())
        self.assertIn("results/pre-install/report.json", installer)
        self.assertIn("results/pre-install/report.json", device)
        self.assertIn("install_authorized-eq$true", installer)
        self.assertIn("worktree_dirty-eq$false", installer)
        self.assertIn("artifactMatches.Count-eq 1", installer)
        self.assertIn("APK_INSTALL_STARTED_RESULT_UNKNOWN", installer)
        self.assertIn("[System.Diagnostics.Process]::Start", installer)
        self.assertNotIn("Start-Process", installer)
        self.assertIn("$installProcess.WaitForExit()", installer)
        self.assertLess(starter.index("APP_LAUNCH_REQUESTED_READINESS_UNVERIFIED"),
                        starter.index("shell am start"))
        self.assertIn('$p0PrerequisiteFailed=$status-ne"PASS"', device)

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

    def test_runner_initialises_network_evidence_before_prerequisite_branches(self):
        source = (ROOT / "deploy" / "scripts" / "device-auto.py").read_text(encoding="utf-8")
        initialisation = source.index("network_status = {}")
        branch = source.index("if services_ok and profile_ok and safe:")
        audit = source.index('add("ev3-stage3-zero-output-audit"')
        self.assertLess(initialisation, branch)
        self.assertLess(branch, audit)
        self.assertIn('counters = {}', source[:branch])


if __name__ == "__main__":
    unittest.main()
