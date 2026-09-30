"""Explicit, standalone beta launch. No network or beta imports from normal modes."""
import os
import socket
import ssl
from pathlib import Path

from . import SatelliteError
from .settings import Settings, data_directory, validate_data_directory


class InstanceLock:
    """One server per Satellite data directory, including across processes."""
    def __init__(self, directory):
        self.directory = directory
        self.file = None

    def __enter__(self):
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        descriptor = os.open(self.directory/'server.lock',os.O_CREAT | os.O_RDWR,0o600)
        self.file = os.fdopen(descriptor,'r+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if not self.file.read(1):
                    self.file.write(b'0'); self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise SatelliteError('Another Satellite server is using this data directory. Stop it first.') from exc
        return self

    def __exit__(self,*unused):
        self.file.close()


def bound_socket(settings):
    family = socket.AF_INET6 if ':' in settings.host else socket.AF_INET
    sock = socket.socket(family,socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
        sock.bind((settings.host,settings.port))
        sock.listen(32)
        return sock
    except OSError as exc:
        sock.close()
        raise SatelliteError('Could not bind the selected address/port. Check that the IP belongs to this PC and the port is free.') from exc


def serve(settings, provider):
    # Imports stay here so missing web dependencies cannot affect ordinary text mode.
    import uvicorn
    from .server import create_app, WEB_ROOT
    from .storage import DeviceStore
    from .pairing import Pairing
    if not (WEB_ROOT.parent/'input-history.js').is_file() or not all((WEB_ROOT/name).is_file() for name in ('index.html','app.js','voice.js','style.css')):
        raise SatelliteError('Satellite client files are missing. Reinstall the complete feature branch.')
    if not settings.insecure_http:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(settings.certfile,settings.keyfile)
        except (OSError,ssl.SSLError) as exc:
            raise SatelliteError('Could not load the HTTPS certificate/key. Check their format, permissions and matching key.') from exc
    with InstanceLock(settings.data_dir), bound_socket(settings) as sock:
        store = DeviceStore(settings.data_dir)
        pairing = Pairing()
        app = create_app(settings,store,pairing,provider)
        server = uvicorn.Server(uvicorn.Config(
            app,host=settings.host,port=settings.port,access_log=False,log_config=None,
            log_level='critical',proxy_headers=False,server_header=False,
            limit_concurrency=32,timeout_keep_alive=5,timeout_graceful_shutdown=3,
            ssl_certfile=settings.certfile,ssl_keyfile=settings.keyfile,
        ))
        print('\n=== JARVIS Satellite Beta ===\nExperimental conversation-only service. PC control is disabled.')
        print('Normal JARVIS interfaces remain separate. Use a second terminal for them.')
        print(f'\nSatellite server:\n{settings.origin}')
        if settings.host in {'127.0.0.1','::1'}:
            print('[satellite beta] Loopback preview only. Select the PC\'s private LAN IP to connect a TV.')
        if settings.insecure_http:
            print('[satellite beta] INSECURE HTTP: local network observers can read chats and device credentials. Use only a trusted LAN; prefer HTTPS.')
        # Deliberate one-time terminal display, not a log or an HTTP response.
        print(f'\nPairing code (one use, expires in 5 minutes):\n{pairing.issue()}')
        print('\nOpen the address on your TV on the same network and enter the code.\nRestart this server for another pairing code. Press Ctrl+C to stop Satellite Beta.\n',flush=True)
        try:
            server.run(sockets=[sock])
        except KeyboardInterrupt:
            pass


def run_cli(options):
    try:
        if options.satellite_devices or options.satellite_revoke:
            from .storage import DeviceStore
            directory = data_directory()
            validate_data_directory(directory)
            store = DeviceStore(directory)
            if options.satellite_revoke:
                print('[satellite beta] Device revoked.' if store.revoke(options.satellite_revoke) else '[satellite beta] Device not found.')
            else:
                for device in store.list_devices():
                    status = 'revoked' if device['revoked'] else 'paired'
                    print(f"[satellite beta] {device['device_id']}  {device['device_name']}  ({device['device_type']}, {status})")
                if not store.list_devices():
                    print('[satellite beta] No paired devices.')
            return 0
        settings = Settings.from_options(options)
        serve(settings,options.provider or 'ollama')
        return 0
    except ImportError:
        print('[satellite beta] Missing dependency. Install the existing requirements.txt with this Python interpreter.')
    except SatelliteError as exc:
        print(f'[satellite beta] Could not start Satellite: {exc}')
    except (Exception,SystemExit):
        # Uvicorn can use SystemExit on startup failure; never exit normal interfaces.
        print('[satellite beta] Could not start or continue the TV server. Check configuration, network and private data storage.')
    print('[satellite beta] Normal JARVIS has not been affected. Start it with jarvis --mode text or jarvis --mode web.')
    return 1
