"""PC-only lifecycle control for the separate, restricted Satellite process.

The local web UI and terminal share this controller. Nothing starts on import.
Pairing codes live in memory and never enter chat history or the AI prompt.
"""
import atexit
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

SETUP = 'TV mode is experimental and conversation-only. It cannot control your PC. Start with a preview on this computer, or follow these steps for a TV.'
SETUP_STEPS = [
    'Put this PC and the TV on the same private network.',
    'Choose HTTPS. Enter this PC’s private IP and paths to a matching certificate and key trusted by the TV. The certificate SAN must match the IP.',
    'Start TV mode, open the displayed address on the TV and enter the pairing code within five minutes. Each code works once.',
    'Keep JARVIS running. Stop and start for a new code; previously paired devices reconnect with their saved chats.',
]
SETUP_NOTE = ('PC preview cannot connect a TV. Browser voice depends on microphone permission and browser support; text remains available. '
              'Closing this panel keeps TV mode running. Quit JARVIS or choose Stop to disconnect devices. '
              'Never forward the port to the internet. Revoke a lost device with jarvis --satellite-revoke DEVICE_ID.')



class TVController:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.info = {'status': 'stopped', 'origin': '', 'code': '', 'expires_at': 0, 'error': ''}

    def status(self):
        with self.lock:
            if self.process is not None and self.process.poll() is not None:
                if self.info['status'] in {'starting', 'running'}:
                    self.info.update(status='failed', error='TV server stopped. Check configuration and start again.')
                self.info.update(code='', origin='', expires_at=0)
            result = dict(self.info)
            if time.time() >= result['expires_at']:
                result['code'] = ''
            result['setup'] = SETUP
            result['setup_steps'] = SETUP_STEPS
            result['setup_note'] = SETUP_NOTE
            return result

    def start(self, *, provider='ollama', mode='preview', host='', port=8766, certfile='', keyfile=''):
        from satellite.settings import Settings, data_directory
        from satellite import SatelliteError
        if provider not in {'ollama', 'gemini', 'openai', 'anthropic'}:
            raise ValueError('Select a supported AI provider.')
        if mode not in {'preview', 'https'}:
            raise ValueError('Choose PC preview or private-network HTTPS.')
        settings = Settings(host='127.0.0.1' if mode == 'preview' else host.strip(), port=port,
                            data_dir=data_directory(), insecure_http=mode == 'preview',
                            certfile=str(Path(certfile).expanduser()) if certfile and mode == 'https' else None,
                            keyfile=str(Path(keyfile).expanduser()) if keyfile and mode == 'https' else None)
        try:
            settings.validate()
        except SatelliteError as exc:
            raise ValueError(str(exc)) from None
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError('TV mode is already running or starting. Stop it before changing setup.')
            self.info = dict(status='starting', origin='', code='', expires_at=0, error='')
            payload = dict(provider=provider, host=settings.host, port=settings.port,
                           certfile=settings.certfile, keyfile=settings.keyfile,
                           insecure_http=settings.insecure_http, data_dir=str(settings.data_dir))
            try:
                process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker'],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                           text=True, start_new_session=os.name == 'posix')
                self.process = process
                process.stdin.write(json.dumps(payload) + '\n')
                process.stdin.close()
                threading.Thread(target=self._receive, args=(process,), daemon=True).start()
            except (OSError, ValueError):
                self.stop()
                self.info.update(status='failed', error='TV process could not start. Check your Python installation.')
                raise ValueError(self.info['error']) from None
            return self.status()

    def _receive(self, process):
        try:
            for line in process.stdout:
                if len(line) > 8192:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                with self.lock:
                    if process is not self.process or self.info['status'] == 'stopped':
                        return
                    if event.get('status') == 'running':
                        self.info.update(status='running', origin=event['origin'], code=event['code'],
                                         expires_at=time.time() + 295, error='')
                    elif event.get('status') == 'failed':
                        self.info.update(status='failed', error=event['error'], code='', origin='')
        finally:
            process.stdout.close()

    def stop(self):
        with self.lock:
            process = self.process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'posix':
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        process.kill()
                    process.wait(timeout=5)
            self.process = None
            self.info.update(status='stopped', code='', origin='', expires_at=0, error='')
            return self.status()


controller = TVController()
atexit.register(controller.stop)


def terminal_menu(provider):
    print('\nTV mode setup\n' + SETUP)
    for number, step in enumerate(SETUP_STEPS, 1):
        print(f'{number}. {step}')
    print(SETUP_NOTE)
    while True:
        state = controller.status()
        print('\nTV mode: ' + state['status'])
        if state['origin']:
            print('Open: ' + state['origin'])
            print('Pairing code (one use): ' + (state['code'] or 'expired — restart for another code'))
        if state['error']:
            print(state['error'])
        print('1) Start PC preview  2) Start TV via HTTPS  3) Stop TV mode  4) Refresh status  5) Back')
        choice = input('> ').strip()
        try:
            if choice == '1':
                controller.start(provider=provider)
            elif choice == '2':
                host = input('PC private LAN IP: ').strip()
                port = int(input('Port [8766]: ').strip() or '8766')
                cert = input('Trusted certificate path: ').strip()
                key = input('Private key path (contents are never displayed): ').strip()
                controller.start(provider=provider, mode='https', host=host, port=port, certfile=cert, keyfile=key)
            elif choice == '3':
                controller.stop()
            elif choice in {'5', '', 'back'}:
                return
            elif choice != '4':
                print('Choose 1–5.')
            if choice in {'1', '2'}:
                deadline = time.monotonic() + 5
                while controller.status()['status'] == 'starting' and time.monotonic() < deadline:
                    time.sleep(.1)
        except (ValueError, RuntimeError) as exc:
            print('TV mode: ' + str(exc))


def worker():
    # Load the existing provider environment without importing the PC dispatcher.
    import config  # noqa: F401
    from contextlib import redirect_stdout
    from satellite import SatelliteError
    from satellite.settings import Settings
    from satellite.cli import serve
    channel = sys.stdout
    def emit(**event):
        channel.write(json.dumps(event) + '\n')
        channel.flush()
    try:
        data = json.loads(sys.stdin.readline(8192))
        provider = data.pop('provider')
        data['data_dir'] = Path(data['data_dir'])
        settings = Settings(**data)
        settings.validate()
        with redirect_stdout(sys.stderr):
            serve(settings, provider, on_ready=lambda origin, code: emit(status='running', origin=origin, code=code))
    except SatelliteError as exc:
        emit(status='failed', error=str(exc))
    except (Exception, SystemExit):
        emit(status='failed', error='TV server could not start. Check dependencies, certificate/key and private storage.')


if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    worker()
