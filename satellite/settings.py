"""Read beta settings only on explicit Satellite entry; never during normal startup."""
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path

from . import SatelliteError


@dataclass(frozen=True)
class Settings:
    host: str = '127.0.0.1'
    port: int = 8766
    data_dir: Path = Path.home() / '.local/share/jarvis/satellite'
    certfile: str | None = None
    keyfile: str | None = None
    insecure_http: bool = False

    @property
    def authority(self):
        host = f'[{self.host}]' if ':' in self.host else self.host
        return f'{host}:{self.port}'

    @property
    def origin(self):
        return ('http' if self.insecure_http else 'https') + '://' + self.authority

    def validate(self):
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as exc:
            raise SatelliteError('Choose a numeric private LAN IP or loopback address; hostnames are not supported.') from exc
        private_ranges = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
        private = any(address in ipaddress.ip_network(net) for net in private_ranges)
        if '%' in self.host or address.is_unspecified or address.is_multicast or not (private or address.is_loopback):
            raise SatelliteError('Use one private LAN IP or loopback address. Wildcard, public and link-local binds are disabled.')
        if not 1024 <= self.port <= 65535 or self.port in {8000, 8765}:
            raise SatelliteError('Choose a port from 1024 to 65535 other than the existing JARVIS ports 8000 and 8765.')
        validate_data_directory(self.data_dir)
        if self.insecure_http and (self.certfile or self.keyfile):
            raise SatelliteError('Choose HTTPS certificates or explicit insecure HTTP, not both.')
        if not self.insecure_http and not (self.certfile and self.keyfile):
            raise SatelliteError('HTTPS requires --satellite-cert and --satellite-key. For a trusted-LAN text trial only, explicitly add --satellite-insecure-http.')

    @classmethod
    def from_options(cls, options):
        if os.environ.get('JARVIS_SATELLITE_ENABLED', 'false').lower() != 'true':
            raise SatelliteError('Disabled by default. Set JARVIS_SATELLITE_ENABLED=true and explicitly select --mode satellite.')
        try:
            result = cls(
                host=options.satellite_host or os.environ.get('JARVIS_SATELLITE_HOST', '127.0.0.1'),
                port=options.satellite_port if options.satellite_port is not None else int(os.environ.get('JARVIS_SATELLITE_PORT', '8766')),
                data_dir=data_directory(),
                certfile=options.satellite_cert or os.environ.get('JARVIS_SATELLITE_CERT') or None,
                keyfile=options.satellite_key or os.environ.get('JARVIS_SATELLITE_KEY') or None,
                insecure_http=options.satellite_insecure_http,
            )
        except ValueError as exc:
            raise SatelliteError('Satellite port must be a number.') from exc
        result.validate()
        return result


def data_directory():
    return Path(os.environ.get('JARVIS_SATELLITE_DIR', Path.home() / '.local/share/jarvis/satellite')).expanduser()


def validate_data_directory(path):
    root = Path(__file__).resolve().parents[1]
    directory = Path(path).expanduser().resolve()
    normal_memory = Path(os.environ.get('JARVIS_MEMORY_DIR', Path.home() / '.local/share/jarvis/memory')).expanduser().resolve()
    if (directory.is_relative_to(root) or root.is_relative_to(directory)
            or directory.is_relative_to(normal_memory) or normal_memory.is_relative_to(directory)):
        raise SatelliteError('Satellite data must have its own private directory outside the repository and PC memory directory.')
