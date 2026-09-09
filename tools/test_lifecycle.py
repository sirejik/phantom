#!/usr/bin/env python3
"""Static regression contract for independent, fixed-pair PHANTOM lifecycle phases."""
import pathlib
import json
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


ROUTINE_EV3 = (
    "scripts/ev3-transfer.ps1", "scripts/ev3-install.ps1", "scripts/ev3-start.ps1",
    "scripts/ev3-recover.ps1", "scripts/ev3-device-integration-test.ps1",
)
ROUTINE_QUEST = (
    "scripts/quest-install.ps1", "scripts/quest-start.ps1",
    "scripts/quest-device-integration-test.ps1",
)


class LifecycleTests(unittest.TestCase):
    def test_lifecycle_result_schema_has_common_required_fields(self):
        schema = json.loads(read("config/schema/lifecycle_result.schema.json"))
        expected = {"schema_version", "phase", "component", "profile", "status", "reason", "duration_ms", "terminal_state", "hardware_evidence_state"}
        self.assertTrue(expected.issubset(schema["required"]))
        self.assertIn("DEVICE INTEGRATION TEST", schema["properties"]["phase"]["enum"])
        self.assertIn(2, schema["properties"]["schema_version"]["enum"])

    def test_independent_phases_do_not_hide_work(self):
        self.assertNotIn("systemctl start", read("deploy/scripts/install-release"))
        self.assertNotIn("run-device-integration-test", read("deploy/scripts/start-release"))
        self.assertIn("'INSTALL:EV3' {'ev3-install.ps1'}", read("scripts/phantom.ps1"))
        self.assertNotIn("'INSTALL:EV3' {'ev3-deploy-install.ps1'}", read("scripts/phantom.ps1"))

    def test_routine_phases_never_provision_or_repin(self):
        for path in ROUTINE_EV3 + ROUTINE_QUEST:
            source = read(path)
            for forbidden in ("ssh-keyscan", "provision-fixed-pair", "ev3-provision-maintenance", "quest-provision-credential"):
                self.assertNotIn(forbidden, source, path)
        self.assertNotIn("ControlMaster", read("scripts/ev3-deploy-common.ps1"))

    def test_private_fixed_pair_is_outside_repo_and_exact(self):
        state = read("scripts/pair-state.ps1")
        self.assertIn("LocalApplicationData", state)
        self.assertIn("PHANTOM_PAIR_STATE_ROOT", state)
        self.assertIn("quest_adb_serial", state)
        self.assertIn("ev3_host_key_fingerprint", state)
        self.assertIn("IdentityFile", read("scripts/ev3-provision-maintenance.ps1"))
        self.assertNotIn("Select-Object -First 1", state)
        for path in ROUTINE_QUEST:
            self.assertIn("Get-PhantomQuestDevice", read(path), path)
        for path in ROUTINE_EV3:
            self.assertNotRegex(read(path), r"\[string\]\$Target", path)

    def test_provision_is_explicit_idempotent_and_record_written_last(self):
        provision = read("scripts/provision-fixed-pair.ps1")
        self.assertIn("'PROVISION:PAIR'", read("scripts/phantom.ps1"))
        self.assertIn("ALREADY_PROVISIONED", provision)
        self.assertIn("PROVISION_CORRUPT", provision)
        for token in ("RotateSshKey", "RotateControlSecret", "RepinHost"):
            self.assertIn(token, provision)
        self.assertGreater(provision.index("Write-PhantomPairState"), provision.index("quest-provision-credential.ps1"))

    def test_canonical_fail_fast_errors_are_present(self):
        source = "\n".join(read(p) for p in ("scripts/pair-state.ps1", "scripts/ev3-deploy-common.ps1", "scripts/ev3-provision-maintenance.ps1"))
        for code in ("PROVISION_REQUIRED", "PROVISION_CORRUPT", "QUEST_NOT_FOUND", "QUEST_IDENTITY_MISMATCH", "HOST_KEY_MISMATCH", "DEVICE_NOT_FOUND"):
            self.assertIn(code, source)

    def test_transfer_is_content_addressed_idempotent_and_atomic(self):
        source = read("scripts/ev3-transfer.ps1")
        for token in ("SKIPPED_ALREADY_PRESENT", "ARTIFACT_MISMATCH", ".partial", "sha256sum", "mv -f", "throughput_bytes_per_second"):
            self.assertIn(token, source)

    def test_start_preserves_first_failure_and_never_rolls_back_or_repairs_wifi(self):
        source = read("deploy/scripts/start-release")
        for token in ("first_failed_service", "first_failure_at_ms", "ExecMainCode", "ExecMainStatus", "list-dependencies", 'fail_start "$unit"'):
            self.assertIn(token, source)
        self.assertNotIn("rollback-release", source)
        self.assertNotIn("wifi-autoconnect", source)
        self.assertIn("NETWORK_NOT_READY", source)
        self.assertIn("APP_FORCE_STOP_REQUESTED", read("scripts/quest-start.ps1"))

    def test_start_and_transport_operations_are_bounded(self):
        start = read("deploy/scripts/start-release")
        self.assertIn('timeout "$step_timeout" systemctl start', start)
        self.assertIn('timeout "$step_timeout" sh -c', start)
        self.assertIn("WaitForExit($TimeoutSeconds*1000)", read("scripts/pair-state.ps1"))
        self.assertIn("WaitForExit($TimeoutSeconds*1000)", read("scripts/ev3-deploy-common.ps1"))
        for path in ROUTINE_QUEST:
            self.assertNotRegex(read(path), r"&\s*\$adb\b", path)

    def test_install_preserves_quest_data_and_leaves_ev3_stopped(self):
        quest = read("scripts/quest-install.ps1")
        ev3 = read("deploy/scripts/install-release")
        self.assertIn("install -r -g", quest)
        self.assertNotIn("uninstall", quest)
        self.assertNotIn("pm clear", quest)
        self.assertIn("runtime intentionally remains stopped", ev3)
        self.assertNotIn("systemctl start", ev3)

    def test_reports_have_common_contract_and_no_device_serial(self):
        for path in ("scripts/ev3-transfer.ps1", "scripts/quest-install.ps1", "scripts/quest-start.ps1", "deploy/scripts/start-release", "deploy/scripts/device-integration-test.py", "scripts/quest-device-integration-test.ps1"):
            source = read(path)
            for field in ("schema_version", "phase", "component", "profile", "status", "reason", "duration_ms", "terminal_state", "hardware_evidence_state"):
                self.assertIn(field, source, (path, field))
            self.assertNotIn("quest_adb_serial=", source)

    def test_debug_and_device_test_do_not_change_safety_or_deploy(self):
        ev3_start = read("scripts/ev3-start.ps1")
        quest_start = read("scripts/quest-start.ps1")
        self.assertIn("PHANTOM_START_VERBOSITY", ev3_start)
        self.assertNotRegex(ev3_start + quest_start, r"\[switch\]\$Debug\b")
        self.assertNotIn("actuator_scope_mask", ev3_start)
        device = read("scripts/ev3-device-integration-test.ps1") + read("scripts/quest-device-integration-test.ps1")
        for token in ("ev3-build.ps1", "install-release", "rollback-release", "adb install"):
            self.assertNotIn(token, device)

    def test_build_and_results_are_disposable_but_secrets_are_not(self):
        build_clean = read("scripts/build-clean.ps1")
        results_clean = read("scripts/results-clean.ps1")
        self.assertIn("[switch]$All", build_clean)
        self.assertIn("BackUpThisFolder_ButDontShipItWithYourGame", build_clean)
        self.assertIn(".secrets", build_clean)
        self.assertIn("param([switch]$Apply)", results_clean)
        self.assertIn("if(!$Apply)", results_clean)

    def test_protocol_contract_identity_is_used_by_build_and_runtime(self):
        for path in ("scripts/ev3-armel-docker.ps1", "scripts/quest-build.ps1", "scripts/ev3-host-build.ps1"):
            source = read(path)
            self.assertIn("protocolcontract", source.lower().replace("_", ""), path)
        for path in ("scripts/ev3-armel-docker.ps1", "scripts/ev3-host-build.ps1"):
            self.assertIn("semantics.yaml", read(path), path)
        self.assertIn('"bin/semantics.yaml"', read("deploy/scripts/install-release"))
        self.assertIn("PHANTOM-BUILD-V3", read("scripts/ev3-armel-docker.ps1"))
        self.assertIn("PHANTOM-BUILD-V3", read("scripts/ev3-host-build.ps1"))
        self.assertIn("PHANTOM-BUILD-V3", read("PhantomQuest/Assets/Phantom/Editor/PhantomBuild.cs"))
        self.assertIn("wire.contract_hash()", read("ev3/network/phantom_network.py"))
        self.assertIn("WireV1.ProtocolContractSha256", read("PhantomQuest/Assets/Phantom/Networking/Stage3NetworkClient.cs"))

    def test_stage3_profile_is_network_only(self):
        source = read("config/source/ev3-network-only.json")
        self.assertRegex(source, r'"actuator_scope_mask"\s*:\s*0')
        self.assertRegex(source, r'"safety_observation_mask"\s*:\s*0')


if __name__ == "__main__":
    unittest.main()
