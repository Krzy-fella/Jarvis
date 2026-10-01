"""Bounded live command output and observable execution state (no model reasoning)."""
import codecs
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import json
import os
from pathlib import Path
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

from privacy import redact

_observer = ContextVar('execution_observer', default=None)


@contextmanager
def observe(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def report(**event):
    callback = _observer.get()
    if callback:
        callback(event)


def observed():
    return _observer.get() is not None


def prepare_action(action):
    """Add Nmap's periodic stats before approval, never rewrite shell expressions."""
    action = copy.deepcopy(action)
    args = action.get('args', {})
    try:
        if action['tool'] == 'kali_tool' and args.get('tool_name') == 'nmap':
            parts = shlex.split(args.get('argument_string', ''))
            if not any(p.startswith('--stats-every') or p == '--resume' for p in parts):
                args['argument_string'] = shlex.join(['--stats-every', '2s', *parts])
        elif action['tool'] == 'run_terminal' and not args.get('background'):
            command = args.get('command', '')
            if re.search(r'[\n\r$`|&;<>*?~{}()\[\]]', command):
                return action
            parts = shlex.split(command)
            if parts and Path(parts[0]).name == 'nmap' and not any(p.startswith('--stats-every') or p == '--resume' for p in parts):
                args['command'] = shlex.join([parts[0], '--stats-every', '2s', *parts[1:]])
    except (ValueError, TypeError):
        pass  # Dispatch retains responsibility for argument validation.
    return action


def action_command(action):
    args = action.get('args', {})
    if action['tool'] == 'run_terminal':
        return str(args.get('command', ''))
    if action['tool'] == 'kali_tool':
        return str(args.get('tool_name', '')) + ' ' + str(args.get('argument_string', ''))
    return action['tool'] + '(' + json.dumps(args, ensure_ascii=False) + ')'


def nmap_progress(text):
    matches = list(re.finditer(r'([^\r\n]+?)\s+Timing:\s+About\s+(\d+(?:\.\d+)?)%\s+done', text, re.I))
    if matches:
        last = matches[-1]
        return last[1].strip(), min(100.0, max(0.0, float(last[2])))
    return None


def output_outcome(output):
    """Report only outcomes supported by the tool result, not invented success."""
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        if data.get('status') == 'timeout':
            return 'timed_out'
        if data.get('exit_code', 0) != 0 or data.get('status') in {'error', 'exception', 'unavailable', 'warning'}:
            return 'failed'
    if str(output).startswith(('Action failed:', '[SAFETY]', 'Unknown or invalid', 'Application not found:')):
        return 'failed'
    if str(output).startswith('Started background process'):
        return 'detached'
    return 'completed'


def run_command(command, *, shell=False, timeout):
    """Drain both streams while waiting; cap retained output and kill on timeout."""
    # Nmap 7.99 and earlier suppress --stats-every without a controlling TTY.
    # Give only direct Nmap calls a private terminal, never the user's terminal.
    launch_command, launch_shell = command, shell
    try:
        parts = shlex.split(command) if shell else list(command)
        simple = not shell or not re.search(r'[\n\r$`|&;<>*?~{}()\[\]]', command)
        if os.name == 'posix' and simple and parts and Path(parts[0]).name == 'nmap' and '--noninteractive' not in parts:
            launch_command = [sys.executable, str(Path(__file__).resolve()), '--nmap-tty', *parts]
            launch_shell = False
    except (ValueError, TypeError):
        pass
    process = subprocess.Popen(launch_command, shell=launch_shell, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=os.name == 'posix')
    report(kind='started', pid=process.pid)
    events = queue.Queue(maxsize=64)
    stop = threading.Event()

    def enqueue(item):
        while not stop.is_set():
            try:
                events.put(item, timeout=.1)
                return
            except queue.Full:
                pass

    def read_stream(stream, name):
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            while not stop.is_set():
                chunk = os.read(stream.fileno(), 4096)
                if not chunk:
                    break
                enqueue((name, decoder.decode(chunk)))
            enqueue((name, decoder.decode(b'', final=True)))
        finally:
            stream.close()
            enqueue((name, None))

    for name in ('stdout', 'stderr'):
        threading.Thread(target=read_stream, args=(getattr(process, name), name), daemon=True).start()
    start = time.monotonic()
    tails = {'stdout': '', 'stderr': ''}
    partials = {'stdout': '', 'stderr': ''}
    closed = set()
    timed_out = False
    exit_seen = None
    try:
        while len(closed) < 2 or process.poll() is None:
            now = time.monotonic()
            if now - start >= timeout:
                timed_out = True
                break
            # A deliberately detached descendant may keep inherited pipes open.
            if process.poll() is not None:
                exit_seen = exit_seen or now
                if now - exit_seen > 1:
                    break
            try:
                name, chunk = events.get(timeout=.1)
            except queue.Empty:
                continue
            if chunk is None:
                closed.add(name)
                if partials[name]:
                    report(kind='output', stream=name, text=partials[name])
                partials[name] = ''
                continue
            tails[name] = (tails[name] + chunk)[-12000:]
            partials[name] += chunk
            lines = re.split(r'[\r\n]', partials[name])
            partials[name] = lines.pop()[-16000:]
            if lines:
                report(kind='output', stream=name, text='\n'.join(lines) + '\n')
        if timed_out:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
        code = process.wait(timeout=2)
    finally:
        stop.set()
        if process.poll() is None:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
    for pending in partials.values():
        if pending:
            report(kind='output', stream='output', text=pending)
    report(kind='ended', exit_code=code, timed_out=timed_out)
    result = dict(exit_code=code, **tails)
    if timed_out:
        result.update(status='timeout', message=f'Command exceeded its {timeout:g}-second time limit and was stopped.')
    return json.dumps(result)


if __name__ == '__main__' and len(sys.argv) > 2 and sys.argv[1] == '--nmap-tty':
    # This runs in a new interpreter/session, avoiding preexec_fn in a threaded server.
    import fcntl
    import pty
    import termios
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    os.set_inheritable(master, True)
    os.set_inheritable(slave, True)
    os.execvp(sys.argv[2], sys.argv[2:])
