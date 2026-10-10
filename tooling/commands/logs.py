from tooling.common.settings import timeout as command_timeout
import json
from pathlib import Path
import shutil
import quest_analyze
from tooling.common.files import write_json
from tooling.common.process import ROOT, ToolError, contained
from tooling.common.pair import Pair, adb, check_quest


def ev3_summary(paths):
    counts, warnings, total = {}, 0, 0
    for path in paths:
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get('_SYSTEMD_UNIT', 'unknown'), str):
                raise ValueError('Invalid journal object')
            unit = event.get('_SYSTEMD_UNIT', 'unknown')
            counts[unit] = counts.get(unit, 0) + 1
            total += 1
            priority = event.get('PRIORITY')
            if priority is not None and int(priority) <= 4:
                warnings += 1
    return dict(component='EV3', records=total, by_service=counts,
                warning_or_error_records=warnings, hardware_verdict='NOT_MEASURED')


def analyze(target, inputs, output):
    output = Path(output).resolve()
    paths = []
    for item in inputs:
        item = Path(item).resolve()
        if not item.exists():
            raise ToolError('Analysis input is missing')
        paths.extend(sorted(item.rglob('*.jsonl')) if item.is_dir() else [item])
    paths = [p for p in paths if output not in p.parents]
    output.mkdir(parents=True, exist_ok=True)
    if target == 'quest':
        quest_analyze.write_reports(quest_analyze.load(paths), output)
    else:
        write_json(output / 'ev3-summary.json', ev3_summary(paths))
    print(f'{target}: analyzed {len(paths)} files')


def execute(args):
    if args.command == 'clean':
        clean(args)
        return
    if args.command == 'analyze':
        analyze(args.target, args.input, args.output)
        return
    if not 1 <= args.lines <= 10000:
        raise ToolError('--lines must be between 1 and 10000')
    import re
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{1,127}', args.package):
        raise ToolError('Invalid Android package name')
    pair = Pair(args.state_root).read(private_files=args.target == 'ev3')
    output = args.output or ROOT / f'results/{args.target}/logs'
    output.mkdir(parents=True, exist_ok=True)
    if args.target == 'quest':
        serial = pair.state['quest_adb_serial']
        check_quest(serial)
        adb(serial, 'pull', f'/sdcard/Android/data/{args.package}/files/phantom-runs/.',
            str(output.resolve()), timeout=args.timeout or command_timeout('quest_logs'))
    else:
        from tooling.commands.devices import ssh
        command = ('journalctl --no-pager -o json -n ' + str(args.lines) +
                   ' -u phantom-controller.service -u phantom-safety.service -u phantom-network.service -u phantom-mdns.service')
        data = ssh(pair, command, args.timeout or command_timeout('ev3_logs')).stdout
        (output / 'journal.jsonl').write_text(data, encoding='utf-8')
    if not args.skip_analysis:
        analyze(args.target, [output], output / 'analysis')


def clean(args):
    if args.keep < 0:
        raise ToolError('--keep must be nonnegative')
    parent = ROOT / args.target
    if not parent.exists():
        print('Nothing to clean')
        return
    if parent.resolve() != parent:
        raise ToolError('Cleanup root must not be a symlink')
    if args.target == 'results' or args.all:
        selected = list(parent.iterdir())
    else:
        selected = [p for p in parent.rglob('*') if p.is_dir() and (
            p.name in ('Temp', 'tmp', 'intermediates', '.gradle', 'diffs') or
            p.name.startswith('ev3-host-') or p.name.endswith('_BackUpThisFolder_ButDontShipItWithYourGame'))]
        packages = sorted((parent / 'ev3-packages').glob('*.tar.gz'), key=lambda p: p.stat().st_mtime, reverse=True)
        for artifact in packages[args.keep:]:
            selected.extend(p for p in artifact.parent.glob(artifact.name + '*') if p.is_file())
    # Validate every target before deleting any target.
    selected = sorted(set(selected), key=lambda p: len(p.parts), reverse=True)
    for path in selected:
        contained(path, parent)
        print(path)
    if args.apply:
        for path in selected:
            contained(path, parent)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
    else:
        print('Preview only; --apply removes these paths')
