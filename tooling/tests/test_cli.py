"""Host lifecycle regression tests: no real ADB/SSH or attached hardware."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tooling.cli import parser
from tooling.common.process import ToolError, contained, run
from tooling.common.pair import Pair, check_quest
from tooling.commands import builds, devices, product_tests, logs, checks


class ConfigCommandTests(unittest.TestCase):
    def test_internal_runner_can_import_shared_modules(self):
        # Reproduces the embedded Python failure: script directory alone cannot
        # import the tooling package from a subprocess.
        result = checks.internal('artifact_check', '--help')
        self.assertEqual(result.returncode, 0)

    def test_schema_check_validates_host_settings_without_devices(self):
        with patch.object(checks, 'internal') as invoke:
            checks.execute(SimpleNamespace(command='check', target='schemas'))
        self.assertEqual([call.args[0] for call in invoke.call_args_list], ['protocolgen', 'configgen'])


class ProcessTests(unittest.TestCase):
    def test_nonzero_exit_is_not_success(self):
        with self.assertRaises(ToolError):
            run([sys.executable, '-c', 'raise SystemExit(7)'])

    def test_timeout_terminates_process(self):
        with self.assertRaisesRegex(ToolError, 'TIMEOUT'):
            run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.1)

    def test_arguments_are_not_shell_text(self):
        literal = 'a b; $(ignored) & `ignored`'
        result = run([sys.executable, '-c', 'import sys; print(sys.argv[1])', literal])
        self.assertEqual(result.stdout.strip(), literal)

    def test_cleanup_rejects_escape_before_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ToolError):
                contained(root / 'child/../../outside', root)
            self.assertEqual(contained(root / 'child', root), (root / 'child').resolve())


class UnityTests(unittest.TestCase):
    def test_only_fresh_nonempty_pass_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'results.xml'
            for xml in ('broken', '<test-run result="Passed" total="0" passed="0" failed="0"/>',
                        '<test-run result="Failed" total="3" passed="2" failed="1"/>'):
                report.write_text(xml)
                with self.assertRaises((ToolError, ValueError)):
                    product_tests.unity_report(report)
            report.write_text('<test-run result="Passed" total="3" passed="3" failed="0"/>')
            product_tests.unity_report(report)

    def test_old_xml_cannot_mask_failed_editor_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'results.xml'
            report.write_text('<test-run result="Passed" total="3" passed="3" failed="0"/>')
            args = parser().parse_args(['test', '--target', 'quest', '--suite', 'unity', '--output', str(report)])
            with patch.object(product_tests.environment, 'executable', return_value='fake-unity'), \
                    patch.object(product_tests, 'run', side_effect=ToolError('license missing')):
                with self.assertRaises(ToolError):
                    product_tests.execute(args)
            self.assertFalse(report.exists())


class PairTests(unittest.TestCase):
    def test_first_setup_creates_key_files_without_contacting_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = Pair(Path(directory) / 'pair')
            args = parser().parse_args(['install', '--target', 'ev3', '--artifact', 'unused',
                                       '--quest-serial', 'fake-quest', '--host-fingerprint', 'SHA256:' + 'A' * 43])
            pair.initialize(args)
            self.assertTrue(pair.key.is_file())
            self.assertTrue(Path(str(pair.key) + '.pub').is_file())
            self.assertEqual(len(pair.secret.read_bytes()), 32)
            self.assertFalse(pair.state['quest_credential_staged'])

    def pair(self, directory):
        pair = Pair(directory)
        pair.key.parent.mkdir(parents=True)
        pair.secret.parent.mkdir()
        pair.key.write_bytes(b'fake-private-file')
        pair.secret.write_bytes(bytes(range(32)))
        public = base64.b64encode(b'fixture-public-key').decode()
        fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(b'fixture-public-key').digest()).decode().rstrip('=')
        pair.known_hosts.write_text('ev3dev.local ssh-ed25519 ' + public + '\n')
        pair.state = dict(provision_schema_version=1, provision_status='complete', ev3_hostname='ev3dev.local',
                          ev3_host_key_fingerprint=fingerprint, quest_adb_serial='test-serial',
                          robot_id='custom-robot', control_key_id='custom-control')
        with patch('tooling.common.pair.private'):
            pair.save()
            pair.pin()
        return pair

    def test_normal_update_preserves_keys_and_custom_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.pair(directory)
            before = (pair.key.read_bytes(), pair.secret.read_bytes(), pair.record.read_bytes())
            args = parser().parse_args(['install', '--target', 'quest', '--artifact', 'ignored.apk'])
            with patch('tooling.common.pair.private'), patch('tooling.common.pair.run') as process:
                pair.initialize(args)
                process.assert_not_called()
            self.assertEqual(before, (pair.key.read_bytes(), pair.secret.read_bytes(), pair.record.read_bytes()))

    def test_missing_key_never_rotates_implicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.pair(directory)
            pair.key.unlink()
            args = parser().parse_args(['install', '--target', 'ev3', '--artifact', 'ignored.tar.gz'])
            with patch('tooling.common.pair.run') as process:
                with self.assertRaises(ToolError):
                    pair.initialize(args)
                process.assert_not_called()

    def test_mismatched_identity_and_rotation_require_explicit_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.pair(directory)
            for flags in (['--rotate-control-secret'], ['--repin-host']):
                args = parser().parse_args(['install', '--target', 'ev3', '--artifact', 'ignored', *flags])
                with self.assertRaises(ToolError):
                    pair.initialize(args)

    def test_custom_ssh_configuration_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.pair(directory)
            pair.config.write_text('User other\n')
            with self.assertRaises(ToolError):
                pair.pin()
            self.assertEqual(pair.config.read_text(), 'User other\n')

    def test_wrong_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.pair(directory)
            pair.state['ev3_host_key_fingerprint'] = 'SHA256:' + 'A' * 43
            with self.assertRaises(ToolError):
                pair.pin()

    def test_wrong_or_unauthorized_quest_is_rejected(self):
        with patch('tooling.common.pair.authorized_devices', return_value=[]):
            with self.assertRaises(ToolError):
                check_quest('test-serial')
        with patch('tooling.common.pair.authorized_devices', return_value=['test-serial']), \
                patch('tooling.common.pair.adb', return_value='other-device'):
            with self.assertRaises(ToolError):
                check_quest('test-serial')


class DeviceTests(unittest.TestCase):
    def test_remote_identity_mismatch_writes_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            result = subprocess.CompletedProcess([], 0, '__PHANTOM_PHASE_REPORT__\n{"status":"PASS","build_id":"other"}', '')
            with patch.object(devices, 'ssh', return_value=result):
                with self.assertRaises(ToolError):
                    devices.remote_report(None, 'ignored', '/report', report, 'expected', 1)
            self.assertEqual(json.loads(report.read_text())['status'], 'FAIL')

    def test_quest_bad_start_forces_stop(self):
        args = parser().parse_args(['start', '--target', 'quest'])
        with patch.object(devices, 'launch_wait', return_value=('123', {'schema_version': 1, 'build_id': 'bad'})), \
                patch.object(devices, 'adb') as adb:
            with self.assertRaises(ToolError):
                devices.start_quest(args, 'fake', Path('unused'))
            adb.assert_called_with('fake', 'shell', 'am', 'force-stop', args.package)

    def test_quest_failed_integration_forces_stop(self):
        args = parser().parse_args(['integration-test', '--target', 'quest', '--build-id', '1' * 64])
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(devices, 'launch_wait', return_value=('123', {'status': 'FAIL'})), \
                patch.object(devices, 'adb') as adb, patch.object(devices.time, 'sleep'):
            with self.assertRaises(ToolError):
                devices.integration_quest(args, 'fake', Path(directory))
            adb.assert_called_with('fake', 'shell', 'am', 'force-stop', args.package)
            report = Path(directory) / args.build_id / 'report.json'
            self.assertEqual(json.loads(report.read_text())['status'], 'FAIL')

    def test_failed_log_pull_never_runs_analyzer(self):
        args = parser().parse_args(['logs', '--target', 'quest'])
        pair = SimpleNamespace(state={'quest_adb_serial': 'fake'})
        with tempfile.TemporaryDirectory() as directory:
            args.output = Path(directory)
            with patch.object(logs, 'Pair') as pair_type, patch.object(logs, 'check_quest'), \
                    patch.object(logs, 'adb', side_effect=ToolError('pull failed')), patch.object(logs, 'analyze') as analyze:
                pair_type.return_value.read.return_value = pair
                with self.assertRaises(ToolError):
                    logs.execute(args)
                analyze.assert_not_called()

    def test_journal_summary_never_claims_hardware_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'journal.jsonl'
            file.write_text('{"_SYSTEMD_UNIT":"phantom-network.service","PRIORITY":"3"}\n')
            result = logs.ev3_summary([file])
            self.assertEqual(result['warning_or_error_records'], 1)
            self.assertEqual(result['hardware_verdict'], 'NOT_MEASURED')


class BuildTests(unittest.TestCase):
    def test_linux_cross_build_uses_the_staging_owner(self):
        stage = Path('private-stage')
        with patch.object(builds.os, 'name', 'posix'), \
                patch.object(builds.os, 'getuid', return_value=1001, create=True), \
                patch.object(builds.os, 'getgid', return_value=121, create=True), \
                patch.object(builds, 'run') as invoke:
            builds.cross_build('locked-image', stage, 'Diagnostic', 30)
        arguments = invoke.call_args_list[0].args[0]
        self.assertEqual(arguments[arguments.index('--user') + 1], '1001:121')

    def test_docker_timeout_removes_own_container_and_preserves_failure(self):
        original = ToolError('build timeout')
        with patch.object(builds, 'run', side_effect=[original, ToolError('cleanup unavailable')]) as process:
            with self.assertRaises(ToolError) as raised:
                builds.cross_build('test-image', Path('test-output'), 'Diagnostic', 5)
            self.assertIs(raised.exception, original)
            launch = process.call_args_list[0].args[0]
            cleanup = process.call_args_list[1].args[0]
            self.assertEqual(cleanup, ['docker', 'rm', '-f', launch[3]])
            self.assertTrue(launch[3].startswith('phantom-tooling-build-'))
    def test_release_publication_cannot_bypass_external_evidence(self):
        for target in ('ev3', 'quest'):
            args = parser().parse_args(['build', '--target', target, '--profile', 'release'])
            result = subprocess.CompletedProcess([], 0, 'test-commit', '')
            with patch.object(builds, 'internal'), patch.object(builds, 'hashes', return_value={}), \
                    patch.object(builds, 'sha', return_value='0' * 64), \
                    patch.object(builds, 'run', return_value=result), \
                    patch.object(builds, 'load', side_effect=AssertionError('Release must not read robot data')):
                with self.assertRaisesRegex(ToolError, 'external qualification evidence'):
                    builds.build(args)
    def test_reproducibility_compares_independent_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / 'package.tar.gz'
            calls = []
            def fake_build(args):
                artifact.write_bytes(bytes([len(calls)]))
                Path(str(artifact) + '.build-manifest.json').write_text('{"build_id":"same"}')
                calls.append(args)
                return artifact
            args = parser().parse_args(['build', '--target', 'ev3', '--verify-reproducibility'])
            with patch.object(builds, 'ROOT', root), patch.object(builds, 'build', side_effect=fake_build):
                (root / 'build/reproducibility').mkdir(parents=True)
                with self.assertRaisesRegex(ToolError, 'Reproducibility failed'):
                    builds.execute(args)
            self.assertEqual(len(calls), 2)
