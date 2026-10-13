from tooling.common.settings import timeout as command_timeout
import copy
import gzip
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import uuid
from tooling.common import environment
from tooling.common.files import load, sha, write_json
from tooling.common.process import ROOT, ToolError, contained, run
from tooling.commands.checks import internal
from build_identity import identity
from configgen import generated_path
from source_hash import source_hash, EV3_SOURCE_INPUTS, QUEST_SOURCE_INPUTS


def hashes():
    return {name: (ROOT / f'protocol/generated/{name}.sha256').read_text().split()[0]
            for name in ('schema', 'semantics', 'contract')}


def cross_command(profile):
    return ('cmake -H/workspace/ev3 -B/tmp/phantom-cross '
            f'-DCMAKE_BUILD_TYPE={"Release" if profile == "Release" else "RelWithDebInfo"} '
            f'-DPHANTOM_DIAGNOSTIC={"OFF" if profile == "Release" else "ON"} '
            '-DPHANTOM_BUILD_TESTS=OFF -DCMAKE_TOOLCHAIN_FILE=/workspace/ev3/toolchains/armel.cmake && '
            'cmake --build /tmp/phantom-cross -- -j2 && '
            'cmake -DCMAKE_INSTALL_PREFIX=/out -P /tmp/phantom-cross/cmake_install.cmake && '
            'cp /tmp/phantom-cross/toolchain-facts.txt /out/toolchain-facts.txt')


def archive(directory, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('wb') as output:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as tar:
                for path in sorted(directory.rglob('*')):
                    relative = path.relative_to(directory).as_posix()
                    entry = tar.gettarinfo(str(path), arcname=relative)
                    entry.uid = entry.gid = 0
                    entry.uname = entry.gname = ''
                    entry.mtime = 0
                    entry.mode = 0o755 if path.is_dir() or relative.startswith('bin/') else 0o644
                    if path.is_file():
                        with path.open('rb') as stream:
                            tar.addfile(entry, stream)
                    else:
                        tar.addfile(entry)


def cross_build(image, stage, profile, timeout):
    container = 'phantom-tooling-build-' + uuid.uuid4().hex
    # Linux bind mounts retain host UID/GID and the staging directory is private.
    # Run as its owner; Docker Desktop supplies different mount semantics.
    user = ['--user', f'{os.getuid()}:{os.getgid()}'] if os.name != 'nt' else []
    try:
        run(['docker', 'run', '--name', container, '--rm', *user, '--entrypoint', 'sh', '--mount',
             f'type=bind,src={ROOT},dst=/workspace,readonly', '--mount',
             f'type=bind,src={stage},dst=/out', image, '-lc', cross_command(profile)],
            timeout=timeout, echo=True)
    finally:
        # A killed Docker client does not necessarily stop its daemon-side
        # container. Remove only the uniquely named container we created.
        try:
            run(['docker', 'rm', '-f', container], timeout=15, check=False)
        except (ToolError, OSError):
            pass


def execute(args):
    if args.verify_reproducibility:
        root = ROOT / 'build/reproducibility'
        artifacts = []
        for name in ('a', 'b'):
            selection = copy.copy(args)
            selection.verify_reproducibility = False
            selection.output = root / (name + ('-quest.apk' if args.target == 'quest' else '-ev3'))
            artifact = build(selection)
            # EV3 packages are content addressed; preserve each independent build before
            # the second build can replace the same package path.
            snapshot = root / (name + artifact.suffix)
            shutil.copy2(artifact, snapshot)
            shutil.copy2(str(artifact) + '.build-manifest.json', str(snapshot) + '.build-manifest.json')
            artifacts.append(snapshot)
        a, b = artifacts
        ma, mb = load(str(a) + '.build-manifest.json'), load(str(b) + '.build-manifest.json')
        equal = sha(a) == sha(b)
        if ma['build_id'] != mb['build_id'] or (args.target == 'ev3' and not equal):
            raise ToolError('Reproducibility failed')
        write_json(root / f'{args.target}-report.json', {
            'build_id': ma['build_id'], 'build_identity_stable': True,
            'artifact_byte_reproducible': equal,
            'difference_class': 'NONE' if equal else 'UNCLASSIFIED_PACKAGE_DIFFERENCE',
            'difference_requires_review': not equal, 'status': 'PASS' if equal else 'REVIEW_REQUIRED'})
        if not equal:
            raise ToolError('APK bytes differ; inspect the saved packages and reproducibility report')
        return
    build(args)


def build(args):
    internal('protocolgen', '--check')
    internal('configgen')
    profile = args.profile.title()
    protocol = hashes()
    config = generated_path(args.target + ('-network-only' if profile == 'Diagnostic' else ''))
    config_hash = sha(config)
    bundle_hash = (load(ROOT / 'build/config/manifest.json')['bootstrap_descriptor_hash']
                   if profile == 'Diagnostic' else '0' * 64)
    commit = run(['git', 'rev-parse', 'HEAD']).stdout.strip()
    dirty = bool(run(['git', 'status', '--porcelain']).stdout.strip())
    if profile == 'Release':
        # Software compilation is independent of robot measurements. Publication
        # still requires real external evidence; that workflow is not implemented.
        raise ToolError('Release publication requires external qualification evidence; '
                        'use test --profile release for software compilation and tests')
    if args.target == 'ev3':
        image = environment.cross_image(timeout=args.timeout or command_timeout('build'))
        folder = contained(args.output or ROOT / 'build/ev3-armel', ROOT / 'build') / args.profile
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='phantom-arm-', dir=ROOT / 'build') as name:
            stage = Path(name)
            cross_build(image, stage, profile, args.timeout or command_timeout('build'))
            facts = (stage / 'toolchain-facts.txt').read_text().splitlines()
            (stage / 'toolchain-facts.txt').unlink()
            shutil.copy2(config, stage / 'config.generated.json')
            for resource in ('systemd', 'tmpfiles'):
                shutil.copytree(ROOT / f'tooling/resources/ev3/{resource}', stage / resource)
            source = source_hash(ROOT, EV3_SOURCE_INPUTS)
            lock_hash = environment.toolchain_hash(image)
            build_id = identity('EV3', profile, source, protocol['contract'], config_hash, lock_hash)[0]
            _, base_image, recipe_hash = environment.cross_recipe()
            manifest = dict(schema_version=5, build_identity_schema='PHANTOM-BUILD-V4',
                            component='EV3', build_id=build_id, build_profile=profile, git_commit=commit,
                            source_tree_hash=source, worktree_dirty=dirty,
                            compiler_target=environment.compiler_target(facts),
                            protocol_version=1, protocol_schema_hash=protocol['schema'],
                            protocol_semantics_hash=protocol['semantics'], protocol_contract_hash=protocol['contract'],
                            config_hash=config_hash, commissioning_bundle_hash=bundle_hash,
                            qualification_eligible=True, cross_image=image, cross_image_base=base_image,
                            cross_image_recipe_sha256=recipe_hash, toolchain_facts=' | '.join(facts),
                            toolchain_or_package_lock_hash=lock_hash, source_date_epoch_or_reproducible_epoch=0,
                            controller_sha256=sha(stage / 'bin/phantom-controller'),
                            safety_sha256=sha(stage / 'bin/phantom-safety'))
            write_json(stage / 'build-manifest.json', manifest)
            sums = [sha(path) + '  ' + path.relative_to(stage).as_posix()
                    for path in sorted(stage.rglob('*')) if path.is_file()]
            (stage / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', encoding='ascii', newline='\n')
            for child in folder.iterdir():
                contained(child, ROOT / 'build')
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            shutil.copytree(stage, folder, dirs_exist_ok=True)
        artifact = ROOT / f'build/ev3-packages/phantom-{build_id}.tar.gz'
        archive(folder, artifact)
        write_json(str(artifact) + '.build-manifest.json', {
            'schema_version': 2, 'component': 'EV3', 'build_id': build_id, 'build_profile': profile,
            'source_tree_hash': source, 'artifact_sha256': sha(artifact),
            'embedded_identity_sha256': sha(folder / 'build-manifest.json')})
        internal('artifact_check', '--component', 'EV3', '--profile', profile,
                 '--artifact', str(artifact), '--ev3-directory', str(folder))
    else:
        artifact = Path(args.output or ROOT / f'build/quest/PhantomQuest-{args.profile}.apk').resolve()
        artifact.parent.mkdir(parents=True, exist_ok=True)
        signing = args.signing_directory.resolve()
        key, password = signing / 'phantom-quest-release.keystore', signing / 'keystore.pass'
        if not key.is_file() or not password.is_file():
            raise ToolError('Quest signing keystore or password file is missing')
        source = source_hash(ROOT, QUEST_SOURCE_INPUTS)
        lock_hash = sha(ROOT / 'PhantomQuest/Packages/packages-lock.json')
        build_id = identity('QUEST', profile, source, protocol['contract'], config_hash, lock_hash)[0]
        settings = environment.quest_build_settings()
        env = dict(os.environ, PHANTOM_APK_PATH=str(artifact), PHANTOM_KEYSTORE_PATH=str(key),
                   PHANTOM_KEYSTORE_PASSWORD_FILE=str(password), PHANTOM_KEY_ALIAS=settings['signing_key_alias'],
                   PHANTOM_META_APP_ID=settings['meta_app_id'], PHANTOM_BUILD_PROFILE=profile,
                   PHANTOM_GIT_COMMIT=commit, PHANTOM_WORKTREE_DIRTY=str(dirty).lower(),
                   PHANTOM_PROTOCOL_SCHEMA_HASH=protocol['schema'],
                   PHANTOM_PROTOCOL_SEMANTICS_HASH=protocol['semantics'],
                   PHANTOM_PROTOCOL_CONTRACT_HASH=protocol['contract'],
                   PHANTOM_QUEST_CONFIG_PATH=str(config), PHANTOM_CONFIG_HASH=config_hash,
                   PHANTOM_BUNDLE_HASH=bundle_hash, PHANTOM_PACKAGE_LOCK_SHA256=lock_hash,
                   PHANTOM_SOURCE_TREE_HASH=source, PHANTOM_BUILD_ID=build_id,
                   GRADLE_USER_HOME=str(ROOT / '.gradle-quest'))
        (ROOT / 'results/quest').mkdir(parents=True, exist_ok=True)
        artifact.unlink(missing_ok=True)
        Path(str(artifact) + '.build-manifest.json').unlink(missing_ok=True)
        try:
            run([environment.executable('unity'), '-batchmode', '-nographics', '-buildTarget', 'Android',
                 '-projectPath', ROOT / 'PhantomQuest', '-executeMethod',
                 'Phantom.Editor.PhantomBuild.BuildAndroid', '-logFile',
                 ROOT / 'results/quest/android-build.log', '-quit'], env=env,
                timeout=args.timeout or command_timeout('build'), echo=True)
        finally:
            wrapper = ROOT / 'PhantomQuest/Library/Bee/Android/Prj/IL2CPP/Gradle/gradlew.bat'
            if wrapper.is_file():
                run([wrapper, '--stop'], cwd=wrapper.parent, timeout=30, check=False)
        manifest = load(str(artifact) + '.build-manifest.json')
        if manifest['build_id'] != build_id or manifest['apk_sha256'] != sha(artifact):
            raise ToolError('Quest build manifest mismatch')
        signature = run([environment.executable('apksigner'), 'verify', '--verbose', '--print-certs', artifact])
        match = re.search(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F:]{64,95})', signature.stdout)
        if not match:
            raise ToolError('Signing certificate SHA-256 is missing')
        manifest['apk_signing_certificate_sha256'] = match.group(1).replace(':', '').lower()
        write_json(str(artifact) + '.build-manifest.json', manifest)
        internal('artifact_check', '--component', 'QUEST', '--profile', profile, '--artifact', str(artifact))
    write_json(str(artifact) + '.build-result.json', {'schema_version': 1, 'phase': 'BUILD',
               'status': 'PASS', 'component': args.target.upper(), 'profile': profile,
               'build_id': build_id, 'artifact_sha256': sha(artifact), 'artifact_path': str(artifact)})
    print(f'{args.target.upper()} BUILD: PASS {artifact}')
    return artifact
