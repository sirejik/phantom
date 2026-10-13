"""Public entry point: python tooling <command>."""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
minimum = tuple(int(part) for part in (ROOT / '.python-version').read_text(encoding='ascii').strip().split('.'))
if sys.version_info[:2] < minimum:
    sys.exit('PHANTOM tooling requires Python ' + '.'.join(map(str, minimum)) + ' or newer.')
os.environ['PYTHONIOENCODING'] = 'utf-8'
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tooling/internal'))
from tooling.cli import main

if __name__ == '__main__':
    sys.exit(main())
