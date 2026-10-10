from tooling.common.settings import timeout as command_timeout
import copy
import json
from pathlib import Path
import re
import shlex
import shutil
import tarfile
import tempfile
import time
import uuid
from tooling.common.files import load, sha, write_json
from tooling.common.process import ROOT, ToolError, run
from tooling.common.pair import Pair, adb, check_quest
from tooling.commands.checks import internal


MAINTENANCE = '/usr/local/libexec/phantom-maintenance'


def ssh(pair, command, timeout=30, check=True):
    return run(['ssh', '-F', pair.config, '-o', 'BatchMode=yes', '--',
                pair.state['ev3_hostname'], command], timeout=timeout, check=check)


def remote_report(pair, command, remote, destination, expected, timeout):
    marker = '__PHANTOM_PHASE_REPORT__'
    script = f'rm -f {shlex.quote(remote)}; {command}; rc=$?; echo {marker}; test ! -f {shlex.quote(remote)} || cat {shlex.quote(remote)}; exit $rc'
    result = ssh(pair, script, timeout, False)
    if marker + '\n' not in result.stdout:
        raise ToolError('Remote operation did not return a report')
    report = json.loads(result.stdout.split(marker + '\n', 1)[1])
    if not isinstance(report, dict):
        raise ToolError('Remote report must be a JSON object')
    if result.returncode or report.get('build_id') != expected:
        report['status'] = 'FAIL'
        report['reason'] = 'REMOTE_OPERATION_OR_IDENTITY_FAILED'
    write_json(destination, report)
    if report.get('status') != 'PASS':
        raise ToolError(f'Remote operation failed; report={destination}')
    return report


def execute(args):
    try:
        _execute(args)
    except (ToolError, ValueError, OSError) as error:
        output = args.output or ROOT / f'results/{args.target}/{args.command}'
        path = output / (getattr(args, 'build_id', None) or 'failed-operation') / 'report.json'
        if not path.exists():
            write_json(path, dict(schema_version=1, status='FAIL', component=args.target.upper(),
                       phase=args.command.upper(), reason=str(error), terminal_state='UNVERIFIED',
                       hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'))
        raise


def _execute(args):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{1,127}', args.package):
        raise ToolError('Invalid Android package name')
    if args.command == 'install':
        try:
            install(args)
        except (ToolError, ValueError, OSError) as error:
            output = args.output or ROOT / f'results/{args.target}/install'
            write_json(output / 'failure.json', dict(status='FAIL', component=args.target.upper(),
                       phase='INSTALL', reason=str(error), hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'))
            raise
        return
    if args.command == 'integration-test' and (args.apk_a or args.apk_b):
        persistence(args)
        return
    if args.target == 'ev3' and not args.build_id:
        raise ToolError('--build-id is required for EV3 start and integration tests')
    output = args.output or ROOT / f'results/{args.target}/{args.command}'
    if args.build_id:
        (output / args.build_id / 'report.json').unlink(missing_ok=True)
    pair = Pair(args.state_root).read(private_files=args.target == 'ev3')
    if args.target == 'ev3':
        operation = 'start-release' if args.command == 'start' else 'run-device-integration-test'
        timeout = args.timeout or command_timeout('ev3_start' if args.command == 'start' else 'ev3_integration')
        prefix = 'env PHANTOM_START_VERBOSITY=debug ' if args.command == 'start' and args.capture_debug else ''
        command = f'timeout -k 8 {timeout} {prefix}{MAINTENANCE}/{operation} {args.build_id}'
        remote = '/var/lib/phantom/' + ('start-result.json' if args.command == 'start' else 'device-integration-test.json')
        report = remote_report(pair, command, remote, output / args.build_id / 'report.json', args.build_id, timeout + 16)
    else:
        serial = pair.state['quest_adb_serial']
        check_quest(serial)
        if args.command == 'start':
            report = start_quest(args, serial, output)
        else:
            report = integration_quest(args, serial, output)
    print(f'{args.target.upper()} {args.command}: {report["status"]}')


def install(args):
    artifact = args.artifact.resolve()
    manifest = load(str(artifact) + '.build-manifest.json')
    if not isinstance(manifest, dict):
        raise ToolError('Build manifest must be a JSON object')
    digest = sha(artifact)
    if (manifest.get('schema_version') != (8 if args.target == 'quest' else 2) or
            manifest.get('build_profile') not in ('Diagnostic', 'Release') or
            manifest.get('component') != args.target.upper() or
            not re.fullmatch('[0-9a-f]{64}', manifest.get('build_id', '')) or
            manifest.get('apk_sha256' if args.target == 'quest' else 'artifact_sha256') != digest):
        raise ToolError('ARTIFACT_MISMATCH: package identity/hash is invalid')
    output = args.output or ROOT / f'results/{args.target}/install'
    if args.target == 'quest' and (args.rotate_ssh_key or args.rotate_control_secret or args.repin_host):
        raise ToolError('Pair rotation is performed by EV3 installation')
    pair = Pair(args.state_root).initialize(args)
    if args.target == 'quest':
        serial = pair.state['quest_adb_serial']
        check_quest(serial)
        stage = args.repair or pair.state.get('quest_credential_staged') is False
        if stage and manifest.get('build_profile') != 'Diagnostic':
            raise ToolError('First credential setup requires a Diagnostic APK')
        adb(serial, 'install', '-r', '-g', str(artifact), timeout=args.timeout or command_timeout('quest_install'))
        installed = adb(serial, 'shell', 'pm', 'path', args.package).splitlines()
        path = next((p[8:] for p in installed if p.startswith('package:')), None)
        if not path or adb(serial, 'shell', 'toybox', 'sha256sum', path).split()[0] != digest:
            raise ToolError('Installed APK hash mismatch')
        if stage:
            remote = f'/sdcard/Android/data/{args.package}/files/phantom-provisioning'
            raw = pair.secret.read_bytes()
            if len(raw) < 32:
                raise ToolError('Invalid CONTROL credential')
            adb(serial, 'shell', 'mkdir', '-p', remote)
            target = remote + '/' + pair.state['control_key_id'] + '.psk'
            adb(serial, 'push', '--sync', str(pair.secret), target, timeout=30)
            if adb(serial, 'shell', 'test', '-f', target) != '':
                raise ToolError('Credential staging failed')
            pair.state['quest_credential_staged'] = True
            pair.save()
        report = dict(schema_version=1, phase='INSTALL', component='QUEST', status='PASS',
                      build_id=manifest['build_id'], profile=manifest['build_profile'],
                      artifact_sha256=digest, terminal_state='APP_NOT_STARTED')
        write_json(output / manifest['build_id'] / 'report.json', report)
    else:
        # Validate before touching the remote machine. No executable is extracted from an unchecked archive.
        from artifact_check import verify_ev3_archive, verify_ev3_elf
        verify_ev3_archive(artifact)
        pair.pin(args.repin_host, args.repair)
        probe = ssh(pair, 'true', check=False)
        if probe.returncode:
            if not re.fullmatch('[A-Za-z0-9._-]+', args.bootstrap_user):
                raise ToolError('Invalid bootstrap user')
            target = args.bootstrap_user + '@' + pair.state['ev3_hostname']
            options = ['-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(pair.known_hosts), '-o', 'ConnectTimeout=8']
            helper = ROOT / 'tooling/resources/ev3/install-deployment-key'
            run(['scp', '-O', *options, Path(str(pair.key) + '.pub'), helper, target + ':/tmp/'], timeout=30)
            run(['ssh', '-t', *options, target, 'sudo sh /tmp/install-deployment-key /tmp/id_ed25519.pub'], timeout=60)
            ssh(pair, 'true')
        stopped = ssh(pair, 'if systemctl is-active --quiet phantom-controller.service || systemctl is-active --quiet phantom-safety.service || systemctl is-active --quiet phantom-network.service; then echo ACTIVE; else echo STOPPED; fi').stdout.strip()
        if stopped != 'STOPPED':
            raise ToolError('Safely stop EV3 runtime before installation setup')
        remote = '/tmp/phantom-tooling-' + uuid.uuid4().hex
        try:
            ssh(pair, 'mkdir -m 0700 ' + remote)
            with tempfile.TemporaryDirectory(prefix='phantom-install-') as directory:
                stage = Path(directory)
                from tooling.common.pair import private
                private(stage)
                resource = ROOT / 'tooling/resources/ev3'
                for path in (resource / 'maintenance').iterdir():
                    shutil.copy2(path, stage / path.name)
                shutil.copy2(resource / 'bootstrap', stage / 'bootstrap')
                shutil.copy2(resource / 'systemd/phantom-wifi-autoconnect.service', stage / 'phantom-wifi-autoconnect.service')
                with tarfile.open(artifact, 'r:gz') as package:
                    native = package.extractfile('bin/phantom-maintenance')
                    (stage / 'phantom-maintenance').write_bytes(native.read())
                verify_ev3_elf(stage / 'phantom-maintenance')
                shutil.copy2(pair.secret, stage / 'control.psk')
                wifi = ''
                if args.wifi_settings:
                    if not args.repair and (pair.root / 'ev3-installed').exists():
                        raise ToolError('Changing Wi-Fi requires --repair')
                    if not args.wifi_service or not re.fullmatch('wifi_[A-Za-z0-9_]+', args.wifi_service):
                        raise ToolError('Invalid ConnMan Wi-Fi service id')
                    shutil.copy2(args.wifi_settings, stage / 'wifi.settings')
                    wifi = ' ' + shlex.quote(args.wifi_service) + ' wifi.settings'
                elif args.wifi_service:
                    raise ToolError('--wifi-service requires --wifi-settings')
                run(['scp', '-O', '-F', pair.config, *stage.iterdir(), 'ev3dev.local:' + remote + '/'], timeout=45)
                ssh(pair, f'sh {remote}/bootstrap {remote} control.psk{wifi}', timeout=60)
        finally:
            ssh(pair, 'rm -rf -- ' + remote, timeout=15, check=False)
        remote_artifact = '/var/lib/phantom/staging/phantom-' + manifest['build_id'] + '.tar.gz'
        run(['scp', '-O', '-F', pair.config, artifact, 'ev3dev.local:' + remote_artifact], timeout=args.timeout or 120)
        if ssh(pair, 'sha256sum ' + remote_artifact).stdout.split()[0] != digest:
            raise ToolError('Transferred package hash mismatch')
        timeout = args.timeout or 60
        command = f'timeout {timeout} {MAINTENANCE}/install-release {remote_artifact} {manifest["build_id"]} {digest}'
        remote_report(pair, command, '/var/lib/phantom/install-result.json',
                      output / manifest['build_id'] / 'report.json', manifest['build_id'], timeout + 8)
        (pair.root / 'ev3-installed').touch()
    print(f'{args.target.upper()} INSTALL: PASS; runtime not started')


def activity(serial, package):
    result = adb(serial, 'shell', 'cmd', 'package', 'resolve-activity', '--brief', package).splitlines()
    if not result or 'No activity' in result[-1]:
        raise ToolError('Installed launch activity not found')
    return result[-1]


def launch_wait(serial, package, remote, timeout):
    adb(serial, 'shell', 'am', 'force-stop', package)
    adb(serial, 'shell', 'rm', '-f', remote)
    adb(serial, 'shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
    launch = adb(serial, 'shell', 'am', 'start', '-n', activity(serial, package))
    if 'Error:' in launch:
        raise ToolError('Quest launch failed')
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        pid = adb(serial, 'shell', f'pidof {shlex.quote(package)} 2>/dev/null || true', timeout=3)
        report = adb(serial, 'shell', f'test ! -f {shlex.quote(remote)} || cat {shlex.quote(remote)}', timeout=3)
        if pid and report:
            return pid, json.loads(report)
        time.sleep(0.25)
    raise ToolError('Quest startup report timeout')


def start_quest(args, serial, output):
    try:
        remote = f'/sdcard/Android/data/{args.package}/files/phantom-status/startup.json'
        pid, status = launch_wait(serial, args.package, remote, args.timeout or 30)
        if (not isinstance(status, dict) or status.get('schema_version') != 1 or not re.fullmatch('[0-9a-f]{64}', status.get('build_id', '')) or
                (args.build_id and status['build_id'] != args.build_id) or
                status.get('runtime_status') != 'ready' or status.get('control_credential') != 'ready'):
            raise ToolError('Quest runtime identity/credential is not ready')
        report = dict(schema_version=1, phase='START', component='QUEST', status='PASS',
                      build_id=status['build_id'], profile=status['build_profile'],
                      terminal_state='APP_PROCESS_RUNNING', pid=pid, control_credential='ready')
        if args.capture_debug:
            folder = output / status['build_id']
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'logcat.txt').write_text(adb(serial, 'logcat', '-d'), encoding='utf-8')
        write_json(output / status['build_id'] / 'report.json', report)
        return report
    except Exception:
        adb(serial, 'shell', 'am', 'force-stop', args.package)
        raise


def integration_quest(args, serial, output):
    if not args.build_id:
        raise ToolError('--build-id is required for installed Quest integration tests')
    checks = []
    remote = f'/sdcard/Android/data/{args.package}/files/quest-device-integration-test.json'
    result = dict(schema_version=2, phase='DEVICE INTEGRATION TEST', component='QUEST', status='FAIL',
                  build_id=args.build_id, terminal_state='APP_FORCE_STOPPED', hardware_evidence_state='DEVICE')
    try:
        for label in ('first', 'relaunch'):
            adb(serial, 'logcat', '-c')
            pid, report = launch_wait(serial, args.package, remote, args.timeout or 35)
            time.sleep(2)
            current = adb(serial, 'shell', f'pidof {shlex.quote(args.package)} 2>/dev/null || true')
            crashes = adb(serial, 'logcat', '-d')
            if (not isinstance(report, dict) or report.get('schema_version') != 2 or report.get('status') != 'PASS' or
                    report.get('build_id') != args.build_id or report.get('build_profile') not in ('Diagnostic', 'Release') or
                    pid != current or re.search(r'FATAL EXCEPTION|Fatal signal|CRASH:|ANR in ' + re.escape(args.package), crashes)):
                raise ToolError('Quest ' + label + ' integration check failed')
            checks.append(report)
        result = dict(schema_version=2, phase='DEVICE INTEGRATION TEST', component='QUEST', status='PASS',
                      build_id=args.build_id, terminal_state='APP_FORCE_STOPPED', hardware_evidence_state='DEVICE',
                      app_report=checks[0], relaunch_report=checks[1])
        return result
    except (ToolError, ValueError, OSError) as error:
        result['reason'] = str(error)
        raise
    finally:
        try:
            adb(serial, 'shell', 'am', 'force-stop', args.package)
        except (ToolError, OSError):
            result['status'] = 'FAIL'
            result['terminal_state'] = 'APP_STOP_UNVERIFIED'
            raise
        finally:
            write_json(output / args.build_id / 'report.json', result)


def persistence(args):
    if args.target != 'quest' or not args.apk_a or not args.apk_b or args.build_id:
        raise ToolError('Persistence requires Quest --apk-a and --apk-b, without --build-id')
    a, b = load(str(args.apk_a) + '.build-manifest.json'), load(str(args.apk_b) + '.build-manifest.json')
    if a['build_id'] == b['build_id'] or a.get('build_profile') != 'Diagnostic':
        raise ToolError('Persistence needs distinct builds; A must be Diagnostic')
    output = args.output or ROOT / 'results/quest/credential-persistence'
    pair = Pair(args.state_root).read()
    try:
        for artifact, manifest, repair in ((args.apk_a, a, True), (args.apk_b, b, False)):
            selection = copy.copy(args)
            for name in ('host_fingerprint', 'quest_serial', 'robot_id', 'control_key_id', 'wifi_settings', 'wifi_service'):
                setattr(selection, name, None)
            selection.rotate_ssh_key = selection.rotate_control_secret = selection.repin_host = False
            selection.repair = repair
            selection.artifact = artifact
            selection.output = output / ('a' if repair else 'b')
            install(selection)
            selection.build_id = manifest['build_id']
            selection.capture_debug = False
            start_quest(selection, pair.state['quest_adb_serial'], selection.output)
    finally:
        adb(pair.state['quest_adb_serial'], 'shell', 'am', 'force-stop', args.package)
    write_json(output / 'report.json', dict(status='PASS', test_id='quest-control-credential-persistence',
                                          build_a=a['build_id'], build_b=b['build_id']))
