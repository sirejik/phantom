import base64
import hashlib
import os
from pathlib import Path
import re
import secrets
from .files import load, write_json
from .process import ROOT, ToolError, run
from .environment import executable
from .identity import robot_id
from .settings import settings, timeout as command_timeout


def private(path):
    path = Path(path)
    if os.name == 'nt':
        # SID stays ASCII even when the account name uses Cyrillic and native
        # Windows utilities write in the console code page.
        identity = run(['whoami', '/user', '/fo', 'csv', '/nh']).stdout
        match = re.search(r'S-1-\d+(?:-\d+)+', identity)
        if not match:
            raise ToolError('Cannot determine Windows account SID')
        run(['icacls', path, '/inheritance:r', '/grant:r', '*' + match.group(0) + ':(F)',
             '/remove:g', '*S-1-1-0', '*S-1-5-11', '*S-1-5-32-545'])
    else:
        path.chmod(0o700 if path.is_dir() else 0o600)


class Pair:
    def __init__(self, root=None):
        base = root or os.environ.get('PHANTOM_PAIR_STATE_ROOT')
        if not base:
            base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'PHANTOM'
        self.root = Path(base).resolve()
        for disposable in (ROOT / 'build', ROOT / 'results', ROOT / '.git'):
            if self.root == disposable or disposable in self.root.parents:
                raise ToolError('Pair state cannot be stored with disposable outputs')
        self.record = self.root / 'pair.json'
        self.key = self.root / 'ssh/id_ed25519'
        self.config = self.root / 'ssh/config'
        self.known_hosts = self.root / 'ssh/known_hosts'
        self.secret = self.root / 'secrets/control.psk'
        self.state = None

    def read(self, private_files=False):
        if not self.record.is_file():
            raise ToolError('PROVISION_REQUIRED: pair record is missing')
        state = load(self.record)
        patterns = {'quest_adb_serial': r'[A-Za-z0-9._:-]{1,128}',
                    'ev3_host_key_fingerprint': r'SHA256:[A-Za-z0-9+/]{43}',
                    'robot_id': r'[A-Za-z0-9._-]{1,32}', 'control_key_id': r'[A-Za-z0-9._-]{1,64}'}
        if (not isinstance(state, dict) or state.get('provision_schema_version') != 1 or state.get('provision_status') != 'complete' or
                state.get('ev3_hostname') != 'ev3dev.local' or any(
                not isinstance(state.get(k), str) or not re.fullmatch(v, state[k]) for k, v in patterns.items())):
            raise ToolError('PROVISION_CORRUPT: invalid pair record')
        if private_files and any(not p.is_file() for p in (self.key, self.config, self.known_hosts, self.secret)):
            raise ToolError('PROVISION_CORRUPT: private pair file is missing')
        self.state = state
        return self

    def save(self):
        write_json(self.record, self.state)
        private(self.record)

    def initialize(self, args):
        rotations = args.rotate_ssh_key or args.rotate_control_secret or args.repin_host
        if rotations and not args.repair:
            raise ToolError('Rotation or repin requires --repair')
        if self.record.is_file():
            self.read()
            for option, field in (('quest_serial', 'quest_adb_serial'),
                                  ('control_key_id', 'control_key_id')):
                value = getattr(args, option)
                if value and value != self.state[field]:
                    raise ToolError('Pair identity mismatch: ' + field)
            if args.host_fingerprint and args.host_fingerprint != self.state['ev3_host_key_fingerprint'] and not args.repin_host:
                raise ToolError('HOST_KEY_MISMATCH')
            if args.repin_host:
                if not args.host_fingerprint:
                    raise ToolError('Explicit fingerprint required for repin')
                self.state['ev3_host_key_fingerprint'] = args.host_fingerprint
            if not self.key.is_file() and not args.rotate_ssh_key:
                raise ToolError('Missing SSH key requires explicit repair')
            if not self.secret.is_file() and not args.rotate_control_secret:
                raise ToolError('Missing CONTROL key requires explicit repair')
        else:
            if self.root.exists() and any(self.root.iterdir()):
                raise ToolError('Partial pair state requires inspection')
            serial = args.quest_serial
            if not serial:
                devices = authorized_devices()
                if len(devices) != 1:
                    raise ToolError('Specify --quest-serial or connect exactly one authorized Quest')
                serial = devices[0]
                check_quest(serial)
            self.state = dict(provision_schema_version=1, provision_status='complete',
                              ev3_hostname='ev3dev.local', ev3_host_key_fingerprint=args.host_fingerprint,
                              quest_adb_serial=serial, robot_id=robot_id(),
                              control_key_id=args.control_key_id or load(ROOT / 'config/shared/pair.json')['network']['control_key_id'],
                              quest_credential_staged=False)
        # Validate inputs before generating or replacing private material.
        patterns = {'ev3_host_key_fingerprint': r'SHA256:[A-Za-z0-9+/]{43}',
                    'quest_adb_serial': r'[A-Za-z0-9._:-]{1,128}', 'robot_id': r'[A-Za-z0-9._-]{1,32}',
                    'control_key_id': r'[A-Za-z0-9._-]{1,64}'}
        if any(not isinstance(self.state.get(k), str) or not re.fullmatch(v, self.state[k]) for k, v in patterns.items()):
            raise ToolError('Invalid pair identity or missing trusted host fingerprint')
        self.root.mkdir(parents=True, exist_ok=True)
        private(self.root)
        self.key.parent.mkdir(exist_ok=True)
        self.secret.parent.mkdir(exist_ok=True)
        private(self.key.parent)
        private(self.secret.parent)
        if args.rotate_ssh_key:
            self.key.unlink(missing_ok=True)
            Path(str(self.key) + '.pub').unlink(missing_ok=True)
        if not self.key.is_file():
            run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'PHANTOM deployment key', '-f', self.key])
            private(self.key)
        if args.rotate_control_secret:
            self.secret.unlink(missing_ok=True)
            self.state['quest_credential_staged'] = False
        if not self.secret.is_file():
            self.secret.write_bytes(secrets.token_bytes(32))
        private(self.secret)
        self.save()
        return self

    def pin(self, repin=False, repair=False):
        fingerprint = self.state['ev3_host_key_fingerprint']
        lines = self.known_hosts.read_text().splitlines() if self.known_hosts.is_file() and not repin else run(
            ['ssh-keyscan', '-T', str(settings()['ssh']['keyscan_timeout_seconds']), '-t', 'ed25519',
             self.state['ev3_hostname']], timeout=command_timeout('ssh_keyscan')).stdout.splitlines()
        matched = []
        for line in lines:
            fields = line.split()
            if len(fields) != 3 or fields[1] != 'ssh-ed25519':
                continue
            digest = 'SHA256:' + base64.b64encode(hashlib.sha256(base64.b64decode(fields[2])).digest()).decode().rstrip('=')
            if digest == fingerprint:
                matched.append(self.state['ev3_hostname'] + ' ssh-ed25519 ' + fields[2])
            elif self.known_hosts.is_file() and not repin:
                raise ToolError('HOST_KEY_MISMATCH')
        if len(set(matched)) != 1:
            raise ToolError('HOST_KEY_MISMATCH or ambiguous EV3')
        # Quote paths for OpenSSH config; this is configuration, not shell text.
        quote = lambda p: '"' + str(p).replace('\\', '/') + '"'
        config = ('Host ev3dev.local\n User root\n IdentityFile ' + quote(self.key) +
                               f"\n IdentitiesOnly yes\n BatchMode yes\n ConnectTimeout {settings()['ssh']['connect_timeout_seconds']}\n"
                               ' StrictHostKeyChecking yes\n UserKnownHostsFile ' + quote(self.known_hosts) + '\n')
        if self.config.is_file() and self.config.read_text(encoding='utf-8') != config and not repair:
            raise ToolError('SSH configuration differs; explicit --repair is required')
        self.known_hosts.write_text(matched[0] + '\n', encoding='ascii')
        self.config.write_text(config, encoding='utf-8')
        private(self.config)


def adb(serial, *args, timeout=None):
    timeout = command_timeout('adb') if timeout is None else timeout
    return run([executable('adb'), '-s', serial, *args], timeout=timeout).stdout.strip()


def authorized_devices():
    output = run([executable('adb'), 'devices']).stdout
    return [line.split()[0] for line in output.splitlines()[1:] if re.fullmatch(r'\S+\s+device', line)]


def check_quest(serial):
    if serial not in authorized_devices():
        raise ToolError('Designated Quest is not connected or authorized')
    if adb(serial, 'shell', 'getprop', 'ro.product.model') != 'Quest 3' or adb(
            serial, 'shell', 'getprop', 'ro.product.device') != 'eureka':
        raise ToolError('Designated device must be Quest 3/eureka')
