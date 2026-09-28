"""Bounded, local conversation memory. Never part of the source checkout."""
import json
import os
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from privacy import redact


class MemoryStore:
    def __init__(self, directory=None, profile='personal'):
        self.directory = Path(directory or os.environ.get('JARVIS_MEMORY_DIR', Path.home() / '.local/share/jarvis/memory')).expanduser()
        self.profile = profile
        self._lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'memory.sqlite3'
        # Restrict the database from its first creation, without changing umask.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.path.chmod(0o600)
        with self._connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, profile TEXT, user TEXT, assistant TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, profile TEXT, text TEXT)')

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_turn(self, user, assistant):
        with self._lock, self._connection() as db:
            db.execute('INSERT INTO turns(profile,user,assistant) VALUES(?,?,?)', (self.profile, redact(user)[:8000], redact(assistant)[:8000]))
            db.execute('DELETE FROM turns WHERE profile=? AND id NOT IN (SELECT id FROM turns WHERE profile=? ORDER BY id DESC LIMIT 100)', (self.profile, self.profile))

    def remember(self, text):
        text = redact(text.strip())[:2000]
        if not text:
            return 'Write the information after /remember.'
        with self._lock, self._connection() as db:
            db.execute('INSERT INTO notes(profile,text) VALUES(?,?)', (self.profile, text))
            db.execute('DELETE FROM notes WHERE profile=? AND id NOT IN (SELECT id FROM notes WHERE profile=? ORDER BY id DESC LIMIT 30)', (self.profile, self.profile))
        return 'Saved to your local memory.'

    def snapshot(self):
        with self._lock, self._connection() as db:
            notes = [row[0] for row in db.execute('SELECT text FROM notes WHERE profile=? ORDER BY id', (self.profile,))]
            rows = list(db.execute('SELECT user,assistant FROM turns WHERE profile=? ORDER BY id DESC LIMIT 8', (self.profile,)))
            count = db.execute('SELECT COUNT(*) FROM turns WHERE profile=?', (self.profile,)).fetchone()[0]
        return {'notes':notes, 'recent_conversations':[{'you':u,'jarvis':a} for u,a in reversed(rows)], 'saved_turns':count}

    def context(self):
        data = self.snapshot()
        # Keep the provider context bounded. Explicit notes take precedence.
        return redact(json.dumps(data, ensure_ascii=False))[:24000]

    def forget(self):
        with self._lock, self._connection() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM turns WHERE profile=?', (self.profile,))
            db.execute('DELETE FROM notes WHERE profile=?', (self.profile,))
        return 'Forgot the saved notes and conversations for this profile.'
