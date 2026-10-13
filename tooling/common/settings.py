"""Host command limits owned by config/tooling/settings.json."""
from pathlib import Path
from .files import load


ROOT = Path(__file__).resolve().parents[2]


def settings():
    value = load(ROOT / 'config/tooling/settings.json')
    if set(value) != {'timeout_max_seconds', 'timeouts', 'ssh', 'polling'}:
        raise ValueError('Unknown or missing tooling settings')
    if not isinstance(value['timeouts'], dict) or set(value['timeouts']) != {
            'process', 'wsl', 'test', 'build', 'ev3_start', 'ev3_integration',
            'quest_install', 'ev3_logs', 'quest_logs', 'adb', 'ssh', 'ssh_keyscan',
            'device_transfer', 'bootstrap_transfer', 'bootstrap', 'deployment_key_install',
            'remote_cleanup', 'ev3_install', 'quest_start', 'quest_start_probe',
            'quest_integration_launch'}:
        raise ValueError('Unknown or missing command timeout')
    maximum = value['timeout_max_seconds']
    if type(maximum) is not int or maximum <= 0:
        raise ValueError('timeout_max_seconds must be a positive integer')
    for name, timeout in value['timeouts'].items():
        if type(timeout) is not int or not 0 < timeout <= maximum:
            raise ValueError(f'Invalid tooling timeout: {name}')
    for section, keys, ceiling in (
            ('ssh', {'connect_timeout_seconds', 'keyscan_timeout_seconds'}, maximum),
            ('polling', {'quest_start_interval_ms', 'quest_integration_stability_ms'}, maximum * 1000)):
        if not isinstance(value[section], dict) or set(value[section]) != keys:
            raise ValueError('Unknown or missing tooling ' + section + ' setting')
        if any(type(item) is not int or not 0 < item <= ceiling for item in value[section].values()):
            raise ValueError('Invalid tooling ' + section + ' setting')
    if value['ssh']['keyscan_timeout_seconds'] >= value['timeouts']['ssh_keyscan']:
        raise ValueError('SSH keyscan subprocess timeout must exceed keyscan timeout')
    if value['polling']['quest_start_interval_ms'] >= value['timeouts']['quest_start'] * 1000:
        raise ValueError('Quest startup polling must fit inside startup timeout')
    return value


def timeout(name):
    return settings()['timeouts'][name]
