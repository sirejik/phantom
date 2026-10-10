from tooling.common.settings import timeout as command_timeout
import os
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET
from tooling.common import environment
from tooling.common.process import ROOT, ToolError, run


def unity_report(path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ToolError('Malformed Unity test report') from error
    if (root.tag != 'test-run' or root.get('result') != 'Passed' or
            int(root.get('total', '0')) <= 0 or int(root.get('passed', '0')) <= 0 or
            int(root.get('failed', '-1')) != 0):
        raise ToolError('Unity test report is empty, failed or malformed')


def execute(args):
    timeout = args.timeout or command_timeout('test')
    if args.target == 'ev3':
        if args.suite == 'unity':
            raise ToolError('--suite unity applies to Quest tests')
        if args.category != 'all':
            raise ToolError('EV3 uses CTest suites selected by --filter; --category applies to Quest host tests')
        source = shlex.quote(environment.linux_path(ROOT / 'ev3'))
        folder = shlex.quote('/tmp/phantom-tooling/ev3-' + args.profile + ('-sanitize' if args.sanitize else ''))
        selected = shlex.quote(args.filter or '.*')
        flags = '-DCMAKE_CXX_FLAGS=-fsanitize=address,undefined' if args.sanitize else ''
        diagnostic = 'ON' if args.profile == 'diagnostic' else 'OFF'
        command = (f'cmake -S {source} -B {folder} -G Ninja -DCMAKE_BUILD_TYPE=Debug '
                   f'-DPHANTOM_DIAGNOSTIC={diagnostic} -DPHANTOM_BUILD_TESTS=ON {flags} && '
                   f'cmake --build {folder} -- -j2 && ctest --test-dir {folder} '
                   f'--output-on-failure --no-tests=error --timeout 30 -R {selected}')
        environment.wsl(command, timeout)
        return
    if args.sanitize:
        raise ToolError('--sanitize applies to EV3 tests')
    if args.suite != 'unity':
        project = ROOT / 'PhantomQuest/Tests/Host/Phantom.HostTests.csproj'
        categories = ('Unit', 'Functional') if args.category == 'all' else (args.category.title(),)
        env = dict(os.environ, PHANTOM_REPO_ROOT=str(ROOT))
        for category in categories:
            run([environment.executable('dotnet'), 'test', project, '--configuration', 'Debug',
                 '-p:RestoreLockedMode=true', '--filter', 'TestCategory=' + category,
                 '--logger', f'trx;LogFileName=host-{category}.trx', '--results-directory',
                 ROOT / 'results/quest'], timeout=timeout, cwd=project.parent, env=env, echo=True)
    if args.suite == 'host':
        return
    output = args.output or ROOT / 'results/quest/unity-test-results.xml'
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    run([environment.executable('unity'), '-batchmode', '-nographics', '-buildTarget', 'Android',
         '-projectPath', ROOT / 'PhantomQuest', '-runTests', '-testPlatform', 'EditMode',
         '-testFilter', args.filter or 'Phantom.Tests', '-testResults', output,
         '-logFile', ROOT / 'results/quest/unity-tests.log'], timeout=timeout, echo=True)
    unity_report(output)
    print('Quest Unity tests: PASS')
