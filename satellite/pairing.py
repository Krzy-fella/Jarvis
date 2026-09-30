"""Short-lived one-use pairing; no plaintext code retained or logged."""
import hashlib
import secrets
import threading
import time


class PairingRejected(Exception):
    pass


class Pairing:
    def __init__(self, *, lifetime=300, attempts=10, clock=time.monotonic):
        self._clock = clock
        self._lifetime = lifetime
        self._limit = attempts
        self._lock = threading.Lock()
        self._digest = None
        self._salt = secrets.token_bytes(32)
        self._expires = 0
        self._attempts = 0

    def issue(self):
        with self._lock:
            code = f'{secrets.randbelow(1000000):06d}'
            self._salt = secrets.token_bytes(32)
            self._digest = self._hash(code)
            self._expires = self._clock() + self._lifetime
            self._attempts = 0
            return code  # Caller displays once on PC, never through the LAN API.

    def _hash(self, code):
        return hashlib.sha256(self._salt + code.encode()).digest()

    def consume(self, code):
        with self._lock:
            if self._digest is None or self._clock() >= self._expires or self._attempts >= self._limit:
                raise PairingRejected('Pairing is unavailable. Restart Satellite on the PC for a new code.')
            self._attempts += 1
            if not secrets.compare_digest(self._digest, self._hash(code)):
                raise PairingRejected('Pairing code is invalid or expired.')
            self._digest = None
