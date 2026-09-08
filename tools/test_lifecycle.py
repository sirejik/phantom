#!/usr/bin/env python3
"""Regression contract for independent PHANTOM lifecycle phases."""
import pathlib,re,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(path):return (ROOT/path).read_text(encoding="utf-8")

class LifecycleTests(unittest.TestCase):
    def test_01_removed_pre_install_phase(self):
        self.assertFalse((ROOT/"scripts/pre-install-auto.ps1").exists());self.assertFalse((ROOT/"config/schema/pre_install_report.schema.json").exists())
    def test_02_device_test_has_no_preinstall_result_dependency(self):
        for path in ("scripts/ev3-device-integration-test.ps1","scripts/quest-device-integration-test.ps1"):
            self.assertNotIn("results/pre-install",read(path))
    def test_03_install_does_not_start(self):self.assertNotIn("systemctl start",read("deploy/scripts/install-release"))
    def test_04_start_does_not_run_device_test(self):self.assertNotIn("run-device-integration-test",read("deploy/scripts/start-release"))
    def test_05_deploy_does_not_provision(self):
        for path in ("scripts/ev3-transfer.ps1","scripts/ev3-install.ps1","scripts/ev3-start.ps1","scripts/quest-install.ps1","scripts/quest-start.ps1"):
            source=read(path);self.assertNotIn("provision-credential",source);self.assertNotIn("ssh-keyscan",source)
    def test_06_missing_control_psk_is_explicit(self):self.assertIn("PROVISION_REQUIRED",read("scripts/quest-start.ps1"))
    def test_07_quest_update_preserves_app_data(self):
        source=read("scripts/quest-install.ps1");self.assertIn("install -r -g",source);self.assertNotIn("uninstall",source);self.assertNotIn("pm clear",source)
    def test_08_stage3_does_not_require_commissioning_psk(self):
        source=read("config/source/quest-network-only.json");self.assertRegex(source,r'"commissioning_key_id"\s*:\s*null')
    def test_09_results_absent_is_supported(self):
        for path in ("scripts/ev3-transfer.ps1","scripts/quest-start.ps1"):
            self.assertIn("New-Item -ItemType Directory",read(path))
    def test_10_stale_results_are_not_read(self):
        for path in ("scripts/ev3-install.ps1","scripts/ev3-start.ps1","scripts/quest-start.ps1"):
            self.assertNotRegex(read(path),r"Get-Content[^\n]*results")
    def test_11_build_is_disposable(self):self.assertIn("[switch]$All",read("scripts/build-clean.ps1"))
    def test_12_dirty_tree_does_not_block_build(self):
        for path in ("scripts/ev3-armel-docker.ps1","scripts/quest-build.ps1"):
            self.assertNotIn("working tree must be clean",read(path).lower())
    def test_13_component_build_commands_are_separate(self):
        self.assertTrue((ROOT/"scripts/ev3-build.ps1").exists());self.assertTrue((ROOT/"scripts/quest-build.ps1").exists())
    def test_14_diagnostic_is_default_without_release_loop(self):
        source=read("scripts/ev3-armel-docker.ps1");self.assertIn('$Profile="Diagnostic"',source);self.assertNotIn('foreach($profile in @("Release","Diagnostic"))',source)
    def test_15_unchanged_units_skip(self):self.assertIn('cmp -s "$release/systemd/$unit"',read("deploy/scripts/install-release"))
    def test_16_changed_units_reload(self):self.assertIn('test "$units_changed" = 0 || systemctl daemon-reload',read("deploy/scripts/install-release"))
    def test_17_tmpfiles_equivalence(self):self.assertIn('tmpfiles_changed',read("deploy/scripts/install-release"))
    def test_18_install_leaves_stopped(self):self.assertIn("runtime intentionally remains stopped",read("deploy/scripts/install-release"))
    def test_19_start_stops_at_first_failure(self):self.assertIn('fail_start "$unit"',read("deploy/scripts/start-release"))
    def test_20_start_captures_diagnostics(self):
        source=read("deploy/scripts/start-release");self.assertIn("ExecMainCode",source);self.assertIn("journalctl",source)
    def test_21_start_has_no_rollback(self):self.assertNotIn("rollback-release",read("deploy/scripts/start-release"))
    def test_22_device_test_does_not_deploy(self):
        source=read("scripts/ev3-device-integration-test.ps1")+read("scripts/quest-device-integration-test.ps1")
        for token in ("ev3-build.ps1","install-release","rollback-release","adb install"):self.assertNotIn(token,source)
    def test_23_no_pid_automatic_variable_assignment(self):self.assertNotRegex(read("scripts/quest-start.ps1"),r"(?im)^\s*\$pid\s*=")
    def test_24_ssh_uses_central_target(self):
        source=read("scripts/ev3-deploy-common.ps1");self.assertIn(".ev3-ssh/config",source);self.assertIn("phantom-ev3",source)
    def test_25_powershell_ssh_quoting_is_escaped(self):
        source=read("scripts/ev3-transfer.ps1");self.assertIn("`$(sha256sum",source);self.assertNotRegex(source,r'(?m)^\s*[^#\"\']*\|\|')
    def test_26_stable_execution_policy_launcher(self):
        self.assertIn("-ExecutionPolicy Bypass",read("scripts/phantom.cmd"));self.assertIn("ValueFromRemainingArguments",read("scripts/phantom.ps1"))
    def test_27_cleaner_selects_unity_backups(self):self.assertIn("BackUpThisFolder_ButDontShipItWithYourGame",read("scripts/build-clean.ps1"))
    def test_28_cleaner_all_selects_build_children(self):self.assertIn("if($All)",read("scripts/build-clean.ps1"))
    def test_29_cleaner_rejects_secrets_and_provisioning(self):
        source=read("scripts/build-clean.ps1");self.assertIn(".secrets",source);self.assertIn("Build root escaped repository build directory",source);self.assertNotIn(".ev3-ssh",source)
    def test_30_debug_uses_same_start_helper(self):self.assertIn("PHANTOM_START_VERBOSITY",read("scripts/ev3-start.ps1"))
    def test_31_debug_does_not_change_safety_core(self):self.assertNotIn("actuator_scope_mask",read("scripts/ev3-start.ps1"))
    def test_32_deep_debug_is_not_qualification_evidence(self):
        self.assertIn("qualification_eligible=false",read("docs/PHANTOM/ENGINEERING.md"));self.assertIn("qualification_eligible=($profile-ne\"DeepDebug\")",read("scripts/ev3-armel-docker.ps1"))
    def test_33_stage3_no_motion_profile(self):
        source=read("config/source/ev3-network-only.json");self.assertRegex(source,r'"actuator_scope_mask"\s*:\s*0');self.assertRegex(source,r'"safety_observation_mask"\s*:\s*0')
    def test_34_quest_credential_persistence_regression_exists(self):
        source=read("scripts/quest-credential-persistence-test.ps1");self.assertGreaterEqual(source.count("quest-install.ps1"),2);self.assertGreaterEqual(source.count("quest-start.ps1"),2)
    def test_35_build_runs_exact_artifact_validation(self):
        self.assertIn("artifact_check.py --component QUEST",read("scripts/quest-build.ps1"));self.assertIn("artifact_check.py --component EV3",read("scripts/ev3-build.ps1"))
    def test_36_recovery_restores_versioned_metadata_and_stays_stopped(self):
        source=read("deploy/scripts/rollback-release");self.assertIn("restore-metadata",source);self.assertIn("runtime intentionally remains stopped",source);self.assertNotIn("systemctl start",source)
    def test_37_debug_failure_snapshots_are_bounded_and_nonsecret(self):
        quest=read("scripts/quest-start.ps1");ev3=read("deploy/scripts/start-release")
        self.assertIn("logcat -d",quest);self.assertIn("journalctl",ev3);self.assertNotIn("control.psk",quest+ev3)
    def test_38_dispatcher_install_does_not_hide_transfer(self):
        source=read("scripts/phantom.ps1")
        self.assertIn("'INSTALL:EV3' {'ev3-install.ps1'}",source)
        self.assertNotIn("'INSTALL:EV3' {'ev3-deploy-install.ps1'}",source)
    def test_39_results_cleaner_is_dry_run_and_repository_scoped(self):
        source=read("scripts/results-clean.ps1")
        self.assertIn("param([switch]$Apply)",source)
        self.assertIn("Join-Path $repository 'results'",source)
        self.assertIn("if(!$Apply)",source)
    def test_40_install_rejects_links_duplicates_and_unlisted_files(self):
        source=read("deploy/scripts/install-release")
        self.assertIn("member.issym() or member.islnk()",source)
        self.assertIn("duplicate archive member",source)
        self.assertIn("listed != actual",source)

if __name__=="__main__":unittest.main()
