import os
from pathlib import Path
import re
import shutil
from .files import load
from .process import ROOT, ToolError, run
from .settings import timeout as command_timeout


def manifest():
    shared = load(ROOT / 'config/tooling/environment.json')
    quest = load(ROOT / 'config/quest/toolchain.json')
    if set(shared) != {'wsl'} or set(quest) != {'unity', 'android', 'dotnet'}:
        raise ValueError('Environment settings must belong to their declared component')
    return {**shared, **quest}


def toolchain_path():
    return ROOT / 'config/ev3/toolchain.json'


def quest_package():
    # Unity owns this mandatory native setting; consumers read its single source.
    text = (ROOT / 'PhantomQuest/ProjectSettings/ProjectSettings.asset').read_text(encoding='utf-8')
    identifiers = re.findall(r'^\s+Android:\s+([A-Za-z][A-Za-z0-9_.]+)\s*$', text, re.M)
    if len(identifiers) != 1:
        raise ValueError('Expected one Android application identifier in Unity ProjectSettings')
    return identifiers[0]


def quest_build_settings():
    value = load(ROOT / 'config/quest/build.json')
    if set(value) != {'meta_app_id', 'signing_key_alias'} or not re.fullmatch(r'[0-9]+', value['meta_app_id']):
        raise ValueError('Invalid Quest build settings')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', value['signing_key_alias']):
        raise ValueError('Invalid Quest signing key alias')
    return value


def unity_root():
    text = (ROOT / 'PhantomQuest/ProjectSettings/ProjectVersion.txt').read_text()
    version = re.search(r'^m_EditorVersion:\s*(\S+)', text, re.M).group(1)
    settings = manifest()['unity']
    candidates = [os.environ.get(settings['override_environment_variable'], '')]
    candidates += [p.format(version=version) for p in settings['search_paths']]
    for candidate in candidates:
        if candidate and (Path(candidate) / 'Editor/Data').is_dir():
            return Path(candidate)
    raise ToolError(f'Unity {version} not found; set PHANTOM_UNITY_ROOT')


def executable(name):
    declared = manifest()
    overrides = {'adb': declared['android']['override_environment_variable'],
                 'dotnet': declared['dotnet']['override_environment_variable'],
                 'apksigner': 'PHANTOM_APKSIGNER'}
    explicit = os.environ.get(overrides.get(name, ''))
    if explicit:
        if not Path(explicit).is_file():
            raise ToolError(f'{name} override does not exist')
        return explicit
    if name == 'unity':
        return str(unity_root() / 'Editor/Unity.exe')
    if name in ('adb', 'apksigner'):
        try:
            data = unity_root() / 'Editor/Data'
            sdk = data / 'PlaybackEngines/AndroidPlayer/SDK'
            candidates = [data / path for path in declared['android']['adb_relative_paths']] if name == 'adb' else sorted(
                sdk.glob('build-tools/*/apksigner.bat'), reverse=True)
            for path in candidates:
                if path.is_file():
                    return str(path)
        except ToolError:
            pass
        if name == 'adb':
            for candidate in manifest()['android']['adb_search_paths']:
                if Path(candidate).is_file():
                    return candidate
    path = shutil.which(name)
    if path:
        return path
    if name == 'dotnet':
        path = Path.home() / manifest()['dotnet']['user_install_relative_path']
        if path.is_file():
            return str(path)
    raise ToolError(f'{name} is not available')


def wsl(command, timeout=None, echo=True):
    timeout = command_timeout('wsl') if timeout is None else timeout
    if os.name != 'nt':
        return run(['bash', '-lc', command], timeout=timeout, echo=echo)
    settings = manifest()['wsl']
    distro = os.environ.get(settings['override_environment_variable'], settings['distribution'])
    return run(['wsl.exe', '-d', distro, '--', 'bash', '-lc', command], timeout=timeout, echo=echo)


def linux_path(path):
    path = Path(path).resolve()
    if os.name != 'nt':
        return str(path)
    settings = manifest()['wsl']
    distro = os.environ.get(settings['override_environment_variable'], settings['distribution'])
    return run(['wsl.exe', '-d', distro, '--', 'wslpath', '-a', str(path).replace('\\', '/')]).stdout.strip()


def cross_image():
    lock = load(toolchain_path())
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', lock['cross_image_digest']):
        raise ToolError('EV3 image must be pinned by SHA-256')
    image = lock['cross_image'] + '@' + lock['cross_image_digest']
    if run(['docker', 'info', '--format', '{{.OSType}}']).stdout.strip() != 'linux':
        raise ToolError('Docker Linux engine required')
    run(['docker', 'image', 'inspect', image])
    return lock, image
