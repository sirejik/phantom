"""Host settings reach their real command consumers without attached devices."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tooling.common import environment, pair, settings
from tooling.commands import devices


class HostSettingsTests(unittest.TestCase):
    def test_startup_polling_uses_configured_interval_and_probe_timeout(self):
        configured = copy.deepcopy(settings.settings())
        configured['timeouts']['quest_start_probe'] = 4
        configured['polling']['quest_start_interval_ms'] = 400
        reports = iter(('', '{"ready":true}'))
        def adb(serial, *arguments, **options):
            if arguments[0] == 'shell' and len(arguments) == 2:
                self.assertEqual(options['timeout'], 4)
                return '123' if arguments[1].startswith('pidof') else next(reports)
            return ''
        with patch.object(settings, 'load', return_value=configured), \
                patch.object(devices, 'activity', return_value='package/.Main'), \
                patch.object(devices, 'adb', side_effect=adb), \
                patch.object(devices.time, 'monotonic', side_effect=(0, 0, 1)), \
                patch.object(devices.time, 'sleep') as sleep:
            self.assertEqual(devices.launch_wait('serial', 'package', '/report', 5),
                             ('123', {'ready': True}))
            sleep.assert_called_once_with(0.4)

    def test_adb_and_ssh_use_configured_defaults_and_explicit_overrides(self):
        configured = copy.deepcopy(settings.settings())
        configured['timeouts'].update(adb=17, ssh=29)
        result = subprocess.CompletedProcess([], 0, 'ok\n', '')
        with patch.object(settings, 'load', return_value=configured), \
                patch.object(pair, 'executable', return_value='fake-adb'), \
                patch.object(pair, 'run', return_value=result) as adb_run, \
                patch.object(devices, 'run', return_value=result) as ssh_run:
            self.assertEqual(pair.adb('serial', 'devices'), 'ok')
            self.assertEqual(adb_run.call_args.kwargs['timeout'], 17)
            pair.adb('serial', 'devices', timeout=5)
            self.assertEqual(adb_run.call_args.kwargs['timeout'], 5)
            target = SimpleNamespace(config=Path('ssh.config'), state={'ev3_hostname': 'test.local'})
            devices.ssh(target, 'true')
            self.assertEqual(ssh_run.call_args.kwargs['timeout'], 29)
            devices.ssh(target, 'true', timeout=7)
            self.assertEqual(ssh_run.call_args.kwargs['timeout'], 7)

    def test_invalid_polling_and_scan_limits_are_rejected(self):
        configured = settings.settings()
        mutations = (
            ('polling', 'quest_start_interval_ms', 0),
            ('polling', 'quest_start_interval_ms', configured['timeouts']['quest_start'] * 1000),
            ('ssh', 'keyscan_timeout_seconds', configured['timeouts']['ssh_keyscan']),
            ('timeouts', 'adb', True),
        )
        for section, key, value in mutations:
            broken = copy.deepcopy(configured)
            broken[section][key] = value
            with patch.object(settings, 'load', return_value=broken), self.assertRaises(ValueError):
                settings.settings()

    def test_apksigner_override_variable_comes_from_android_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            signer = Path(directory) / 'signer.exe'
            signer.write_bytes(b'test executable')
            declared = environment.manifest()
            declared['android']['apksigner_override_environment_variable'] = 'PHANTOM_TEST_SIGNER'
            with patch.object(environment, 'manifest', return_value=declared), \
                    patch.dict(os.environ, {'PHANTOM_TEST_SIGNER': str(signer)}):
                self.assertEqual(environment.executable('apksigner'), str(signer))
