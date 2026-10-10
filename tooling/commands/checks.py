import ast
from pathlib import Path
import sys
import unittest
from tooling.common.process import ROOT, ToolError, run
from tooling.common import environment
from tooling.common.settings import settings as tooling_settings
from tooling.common.files import load


def internal(name, *arguments):
    folder = ROOT / 'tooling/internal'
    script = folder / (name + '.py')
    bootstrap = 'import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); sys.argv.pop(0); runpy.run_path(sys.argv[0],run_name="__main__")'
    return run([sys.executable, '-c', bootstrap, folder, script, *arguments], echo=True)


def execute(args):
    if args.command == 'self-test':
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tooling/tests'))
        result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
        if not result.wasSuccessful():
            raise ToolError('Tooling self-tests failed')
        return
    if args.command == 'docs':
        flags = ['--locate', args.locate]
        if args.document:
            flags += ['--document', args.document]
        internal('docindex', *flags)
        return
    if args.command == 'doctor':
        failures = []
        for name in ('unity', 'dotnet', 'adb', 'docker', 'ssh'):
            try:
                print(name + ': ' + environment.executable(name))
            except ToolError as error:
                failures.append(str(error))
                print(name + ': unavailable')
        try:
            _, image = environment.cross_image()
            print('EV3 image: ' + image)
        except (ToolError, OSError) as error:
            failures.append(str(error))
        try:
            environment.wsl('cmake --version && ninja --version && g++ --version', 20, echo=False)
            print('Host C++ tools: available')
        except (ToolError, OSError) as error:
            failures.append(str(error))
        if failures:
            raise ToolError('; '.join(failures))
        return
    if args.command == 'generate':
        for target, module in (('protocol', 'protocolgen'), ('config', 'configgen'), ('docs', 'docindex')):
            if args.target in ('all', target):
                internal(module)
        return
    # Parse every owned Python module before generators or builds run.
    for path in (ROOT / 'tooling').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    if args.target in ('all', 'schemas'):
        tooling_settings()
        environment.manifest()
        environment.quest_package()
        environment.quest_build_settings()
        lock = load(environment.toolchain_path())
        import re
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', lock['cross_image_digest']):
            raise ToolError('EV3 cross image must be pinned by SHA-256')
        internal('protocolgen', '--check')
        internal('configgen', '--check')
    if args.target in ('all', 'docs'):
        internal('protocolgen', '--check', '--include-docs')
        internal('docindex', '--check')
        internal('doclint')
        internal('spec_contract_check')
        internal('implementation_map_check')
    if args.target in ('all', 'security'):
        internal('security_scan')
    if args.target == 'all':
        import shlex
        for path in sorted((ROOT / 'tooling/resources/ev3').rglob('*')):
            if path.is_file() and path.read_bytes().startswith(b'#!/bin/sh'):
                environment.wsl('sh -n ' + shlex.quote(environment.linux_path(path)), 15)
    if args.target in ('all', 'android'):
        import re
        android = environment.unity_root() / 'Editor/Data/PlaybackEngines/AndroidPlayer'
        settings = (ROOT / 'PhantomQuest/ProjectSettings/ProjectSettings.asset').read_text()
        sdk = re.search(r'AndroidTargetSdkVersion: (\d+)', settings).group(1)
        jar = android / f'SDK/platforms/android-{sdk}/android.jar'
        if not jar.is_file():
            raise ToolError('Pinned Android platform jar is missing')
        sources = sorted((ROOT / 'PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib/src').rglob('*.java'))
        if not sources:
            raise ToolError('Android bridge sources are missing')
        output = ROOT / 'build/quest/androidlib-classes'
        output.mkdir(parents=True, exist_ok=True)
        run([android / 'OpenJDK/bin/javac.exe', '-Xlint:all', '-bootclasspath', jar,
             '-source', '8', '-target', '8', '-d', output, *sources], echo=True)
    print('CHECK: PASS')
