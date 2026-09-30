"""Private device credentials and resumable state, separate from PC chat storage."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from privacy import redact
from .permissions import CAPABILITIES


class DeviceStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / 'devices.sqlite3'
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.path.chmod(0o600)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, credential_hash TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS states (device_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (device_id TEXT NOT NULL, request_id TEXT NOT NULL, text_hash TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(device_id,request_id))')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=3)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def register(self, name, kind):
        now = time.time()
        with self.lock, self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM devices WHERE revoked=0 AND expires>?', (now,)).fetchone()[0] >= 8:
                raise ValueError('Eight devices are already paired. Revoke an unused device on the PC first.')
            device_id = secrets.token_urlsafe(16)
            credential = device_id + '.' + secrets.token_urlsafe(32)
            db.execute('INSERT INTO devices VALUES(?,?,?,?,?,?,?,0)', (device_id,redact(name),kind,self.digest(credential),now,now,now+90*86400))
        return self.device(device_id), credential

    def device(self, device_id):
        with self.connection() as db:
            row = db.execute('SELECT id,name,kind,created,seen,expires,revoked FROM devices WHERE id=?', (device_id,)).fetchone()
        if row is None:
            return None
        result = dict(zip(('device_id','device_name','device_type','created_at','last_seen','expires_at','revoked'), row))
        result['permissions'] = dict(CAPABILITIES)
        return result

    def authenticate(self, credential):
        if not isinstance(credential, str) or len(credential) > 160:
            return None
        device_id = credential.partition('.')[0]
        now = time.time()
        with self.lock, self.connection() as db:
            row = db.execute('SELECT credential_hash,expires,revoked,seen FROM devices WHERE id=?', (device_id,)).fetchone()
            expected = row[0] if row else '0' * 64
            valid = secrets.compare_digest(expected, self.digest(credential))
            if not valid or not row or row[1] <= now or row[2]:
                return None
            if now-row[3] > 30:
                db.execute('UPDATE devices SET seen=? WHERE id=?', (now,device_id))
        return self.device(device_id)

    def active(self, device_id):
        device = self.device(device_id)
        return device is not None and not device['revoked'] and device['expires_at'] > time.time()

    def list_devices(self):
        with self.connection() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM devices ORDER BY created DESC')]
        return [self.device(i) for i in ids]

    def revoke(self, device_id):
        with self.lock, self.connection() as db:
            return bool(db.execute('UPDATE devices SET revoked=1 WHERE id=?', (device_id,)).rowcount)

    def load(self, device_id):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM states WHERE device_id=?', (device_id,)).fetchone()
        return json.loads(redact(row[0])) if row else None

    def save(self, device_id, state, request=None):
        with self.lock, self.connection() as db:
            if request:
                request_id, text = request
                db.execute('INSERT INTO requests VALUES(?,?,?,?)', (device_id, request_id,self.digest(text),time.time()))
                db.execute('DELETE FROM requests WHERE device_id=? AND request_id NOT IN (SELECT request_id FROM requests WHERE device_id=? ORDER BY created DESC LIMIT 100)', (device_id,device_id))
            db.execute('INSERT OR REPLACE INTO states VALUES(?,?)', (device_id,redact(json.dumps(state,ensure_ascii=False))))

    def duplicate(self, device_id, request_id, text):
        with self.connection() as db:
            row = db.execute('SELECT text_hash FROM requests WHERE device_id=? AND request_id=?', (device_id,request_id)).fetchone()
        if row and not secrets.compare_digest(row[0],self.digest(text)):
            raise ValueError('A request ID cannot be reused for a different message.')
        return bool(row)
