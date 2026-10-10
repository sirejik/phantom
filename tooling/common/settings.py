"""Host command limits owned by config/tooling/settings.json."""
from pathlib import Path
from .files import load


ROOT = Path(__file__).resolve().parents[2]


def settings():
    value = load(ROOT / 'config/tooling/settings.json')
    minimum = value['python_minimum']
    if not isinstance(minimum, list) or len(minimum) != 2 or any(type(part) is not int or part < 0 for part in minimum):
        raise ValueError('python_minimum must contain major and minor integers')
    maximum = value['timeout_max_seconds']
    if type(maximum) is not int or maximum <= 0:
        raise ValueError('timeout_max_seconds must be a positive integer')
    for name, timeout in value['timeouts'].items():
        if type(timeout) is not int or not 0 < timeout <= maximum:
            raise ValueError(f'Invalid tooling timeout: {name}')
    return value


def timeout(name):
    return settings()['timeouts'][name]
