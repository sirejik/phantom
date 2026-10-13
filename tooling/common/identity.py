"""Fixed single-robot protocol identity, owned by the EV3 runtime schema."""
import re
from .files import load
from .process import ROOT


def robot_id(root=ROOT):
    value = load(root / 'schemas/ev3/runtime.schema.json')['properties']['robot_id']['const']
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', value):
        raise ValueError('Invalid fixed robot identity in runtime schema')
    return value
