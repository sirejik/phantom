import os
from pathlib import Path
import re
import shutil
from .files import load
from .process import ROOT, ToolError, run
from .settings import timeout as command_timeout


def manifest():
    shared = load(ROOT / 'config/tooling/environment.json')
    quest = load(ROOT / 'config/quest/project.json')['build']['environment']
    if set(shared) != {'wsl'} or set(quest) != {'unity', 'android', 'dotnet'}:
        raise ValueError('Environment settings must belong to their declared component')
    wsl_settings = shared['wsl']
    if (set(wsl_settings) != {'override_environment_variable', 'distribution'} or
            any(not isinstance(value, str) or not value for value in wsl_settings.values())):
        raise ValueError('WSL settings must contain an override variable and distribution')
    return {**shared, **quest}


def compiler_target(facts):
    """Read the observed compiler triple exported by CMake, never a config label."""
    lines = facts.split(' | ') if isinstance(facts, str) else facts
    targets = [line.removeprefix('compiler_target=') for line in lines
               if line.startswith('compiler_target=')]
    if len(targets) != 1 or not re.fullmatch(r'[A-Za-z0-9_+.]+(?:-[A-Za-z0-9_+.]+)+', targets[0]):
        raise ToolError('Missing or malformed observed compiler target')
    return targets[0]


def cross_recipe():
    """The single Dockerfile owns the pinned base and package versions."""
    import hashlib
    path = ROOT / 'ev3/docker/Dockerfile'
    raw = path.read_bytes()
    bases = re.findall(r'^FROM\s+(\S+)\s*$', raw.decode('utf-8'), re.MULTILINE)
    if len(bases) != 1 or not re.fullmatch(r'[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}', bases[0]):
        raise ToolError('EV3 Dockerfile must have one digest-pinned FROM')
    return path, bases[0], hashlib.sha256(raw).hexdigest()


def toolchain_hash(image_id):
    from configgen import canonical
    import hashlib
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ToolError('EV3 prepared image identity must be immutable')
    _, _, recipe_hash = cross_recipe()
    return hashlib.sha256(canonical({'dockerfile_sha256': recipe_hash,
                                     'prepared_image_id': image_id})).hexdigest()


def quest_package():
    # Unity owns this mandatory native setting; consumers read its single source.
    text = (ROOT / 'PhantomQuest/ProjectSettings/ProjectSettings.asset').read_text(encoding='utf-8')
    identifiers = re.findall(r'^\s+Android:\s+([A-Za-z][A-Za-z0-9_.]+)\s*$', text, re.M)
    if len(identifiers) != 1:
        raise ValueError('Expected one Android application identifier in Unity ProjectSettings')
    return identifiers[0]


def quest_build_settings():
    value = load(ROOT / 'config/quest/project.json')['build']['packaging']
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
    raise ToolError(f"Unity {version} not found; set {settings['override_environment_variable']}")


def executable(name):
    declared = manifest()
    overrides = {'adb': declared['android']['override_environment_variable'],
                 'dotnet': declared['dotnet']['override_environment_variable'],
                 'apksigner': declared['android']['apksigner_override_environment_variable']}
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


def cross_image(prepare=True, timeout=None):
    import tempfile
    path, _, recipe_hash = cross_recipe()
    tag = 'phantom-ev3-cross:' + recipe_hash
    if run(['docker', 'info', '--format', '{{.OSType}}']).stdout.strip() != 'linux':
        raise ToolError('Docker Linux engine required')
    if prepare:
        # A tiny context prevents sending project sources, keys or local data.
        with tempfile.TemporaryDirectory(prefix='phantom-cross-image-') as directory:
            identity_file = Path(directory) / 'image.id'
            run(['docker', 'build', '--iidfile', identity_file, '--tag', tag,
                 '--file', path, path.parent], timeout=timeout or command_timeout('build'), echo=True)
            image = identity_file.read_text(encoding='ascii').strip()
    else:
        image = run(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}']).stdout.strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ToolError('Docker returned no immutable prepared image ID')
    run(['docker', 'image', 'inspect', image])
    return image
