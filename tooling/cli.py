import argparse
import os
from pathlib import Path
import sys

from tooling.common.process import ROOT, ToolError
from tooling.common.settings import settings
from tooling.common.environment import quest_package


def parser():
    result = argparse.ArgumentParser(prog='python tooling', allow_abbrev=False)
    commands = result.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='Linters, generated inputs and documentation')
    check.add_argument('--target', choices=('all', 'docs', 'schemas', 'security', 'android'), default='all')
    generate = commands.add_parser('generate')
    generate.add_argument('--target', choices=('all', 'protocol', 'config', 'docs'), default='all')
    docs = commands.add_parser('docs', help='Locate a documentation section')
    docs.add_argument('--document')
    docs.add_argument('--locate', required=True)
    commands.add_parser('self-test', help='Tests of the tooling, without devices')
    commands.add_parser('doctor', help='Report installed build/test dependencies')
    for name in ('test', 'build', 'install', 'start', 'integration-test', 'logs'):
        command = commands.add_parser(name)
        command.add_argument('--target', choices=('ev3', 'quest'), required=True)
        command.add_argument('--timeout', type=int, default=None)
        command.add_argument('--output', type=Path)
        if name in ('test', 'build'):
            command.add_argument('--profile', choices=('diagnostic', 'release'), default='diagnostic')
        if name == 'test':
            command.add_argument('--suite', choices=('all', 'host', 'unity'), default='all')
            command.add_argument('--category', choices=('all', 'unit', 'functional'), default='all')
            command.add_argument('--filter', default=None)
            command.add_argument('--sanitize', action='store_true')
        if name == 'build':
            command.add_argument('--signing-directory', type=Path, default=Path('.secrets/quest-release'))
            command.add_argument('--verify-reproducibility', action='store_true')
        if name in ('install', 'start', 'integration-test', 'logs'):
            command.add_argument('--state-root', type=Path)
            command.add_argument('--package', default=quest_package())
        if name == 'install':
            command.add_argument('--artifact', type=Path, required=True)
            command.add_argument('--host-fingerprint')
            command.add_argument('--quest-serial')
            command.add_argument('--robot-id')
            command.add_argument('--control-key-id')
            command.add_argument('--bootstrap-user', default='robot')
            command.add_argument('--wifi-settings', type=Path)
            command.add_argument('--wifi-service')
            command.add_argument('--repair', action='store_true')
            command.add_argument('--rotate-ssh-key', action='store_true')
            command.add_argument('--rotate-control-secret', action='store_true')
            command.add_argument('--repin-host', action='store_true')
        if name in ('start', 'integration-test'):
            command.add_argument('--build-id')
        if name == 'start':
            command.add_argument('--capture-debug', action='store_true')
        if name == 'integration-test':
            command.add_argument('--apk-a', type=Path)
            command.add_argument('--apk-b', type=Path)
        if name == 'logs':
            command.add_argument('--skip-analysis', action='store_true')
            command.add_argument('--lines', type=int, default=1000)
    analyze = commands.add_parser('analyze')
    analyze.add_argument('--target', choices=('ev3', 'quest'), required=True)
    analyze.add_argument('--input', type=Path, nargs='+', required=True)
    analyze.add_argument('--output', type=Path, required=True)
    clean = commands.add_parser('clean')
    clean.add_argument('--target', choices=('build', 'results'), required=True)
    clean.add_argument('--apply', action='store_true')
    clean.add_argument('--all', action='store_true')
    clean.add_argument('--keep', type=int, default=2)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    maximum = settings()['timeout_max_seconds']
    if getattr(args, 'timeout', None) is not None and not 1 <= args.timeout <= maximum:
        parser().error(f'--timeout must be between 1 and {maximum} seconds')
    if getattr(args, 'build_id', None):
        import re
        if not re.fullmatch('[0-9a-f]{64}', args.build_id):
            parser().error('--build-id must be a lowercase SHA-256')
    if getattr(args, 'target', None) == 'ev3' and (getattr(args, 'apk_a', None) or getattr(args, 'apk_b', None)):
        parser().error('--apk-a and --apk-b apply to Quest')
    os.chdir(ROOT)
    try:
        if args.command in ('check', 'generate', 'docs', 'self-test', 'doctor'):
            from tooling.commands import checks
            checks.execute(args)
        elif args.command == 'test':
            from tooling.commands import product_tests
            product_tests.execute(args)
        elif args.command == 'build':
            from tooling.commands import builds
            builds.execute(args)
        elif args.command in ('logs', 'analyze', 'clean'):
            from tooling.commands import logs
            logs.execute(args)
        else:
            from tooling.commands import devices
            devices.execute(args)
    except (ToolError, ValueError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    return 0
