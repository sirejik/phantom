"""Bounded subprocesses, without interpolation of local shell commands."""
import os
from pathlib import Path
import subprocess
from .settings import timeout as command_timeout

ROOT = Path(__file__).resolve().parents[2]


class ToolError(RuntimeError):
    pass


def run(args, *, timeout=None, cwd=ROOT, env=None, check=True, echo=False):
    timeout = command_timeout('process') if timeout is None else timeout
    args = [str(arg) for arg in args]
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8',
                               errors='replace', creationflags=creationflags,
                               start_new_session=os.name != 'nt')
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, creationflags=creationflags, timeout=10)
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.kill()
        process.communicate()
        raise ToolError(f'TIMEOUT: {Path(args[0]).name} exceeded {timeout}s') from None
    if echo:
        print(stdout, end='')
        print(stderr, end='')
    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    if check and result.returncode:
        # Arguments may include private paths. Never print them or an environment dump.
        raise ToolError(f'{Path(args[0]).name} failed (exit {result.returncode})\n{stderr[-2000:]}')
    return result


def contained(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    if path == parent or parent not in path.parents:
        raise ToolError(f'Path must be inside {parent}')
    return path
