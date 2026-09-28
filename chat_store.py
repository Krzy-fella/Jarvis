"""Saved browser conversations, in the same private database as local memory."""
import json
import secrets
import time
from privacy import redact


class ChatStore:
    def __init__(self, memory):
        self.memory = memory
        self.profile = memory.profile
        with memory._lock, memory._connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, profile TEXT NOT NULL, title TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL, messages TEXT NOT NULL, history TEXT NOT NULL, interrupted INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE INDEX IF NOT EXISTS chats_profile ON chats(profile, pinned, updated)')
            db.execute('CREATE TABLE IF NOT EXISTS chat_state (profile TEXT PRIMARY KEY, active_id TEXT)')
            if not db.execute('SELECT 1 FROM chat_state WHERE profile=?', (self.profile,)).fetchone():
                # Older versions stored turns without conversation boundaries. Preserve
                # those retained turns together once, rather than inventing sessions.
                rows = db.execute('SELECT id,user,assistant FROM turns WHERE profile=? AND chat_id IS NULL ORDER BY id', (self.profile,)).fetchall()
                active = None
                if rows:
                    active = secrets.token_urlsafe(16)
                    messages, history = [], []
                    for _, user, assistant in rows:
                        messages.extend([{'role':'user','content':redact(user),'label':None}, {'role':'assistant','content':redact(assistant),'label':None}])
                        history.extend([{'role':'user','content':redact(user)}, {'role':'assistant','content':redact(assistant)}])
                    db.execute('INSERT INTO chats(id,profile,title,updated,messages,history) VALUES(?,?,?,?,?,?)', (active,self.profile,'Earlier conversations',time.time_ns(),json.dumps(messages),json.dumps(history[-40:])))
                    db.executemany('UPDATE turns SET chat_id=? WHERE id=? AND profile=?', [(active,row[0],self.profile) for row in rows])
                db.execute('INSERT INTO chat_state(profile,active_id) VALUES(?,?)', (self.profile,active))

    def list(self):
        with self.memory._lock, self.memory._connection() as db:
            rows = db.execute('SELECT id,title,pinned,updated FROM chats WHERE profile=? ORDER BY pinned DESC,updated DESC,id', (self.profile,)).fetchall()
        return [dict(id=i,title=redact(t),pinned=bool(p),updated=u) for i,t,p,u in rows]

    def active_id(self):
        with self.memory._connection() as db:
            row = db.execute('SELECT active_id FROM chat_state WHERE profile=?', (self.profile,)).fetchone()
        return row[0] if row else None

    def activate(self, chat_id):
        with self.memory._lock, self.memory._connection() as db:
            if chat_id is not None and not db.execute('SELECT 1 FROM chats WHERE id=? AND profile=?', (chat_id,self.profile)).fetchone():
                raise KeyError('Chat not found')
            db.execute('UPDATE chat_state SET active_id=? WHERE profile=?', (chat_id,self.profile))

    def create(self, first_message):
        chat_id = secrets.token_urlsafe(16)
        title = ' '.join(redact(first_message).split())[:70] or 'New conversation'
        with self.memory._lock, self.memory._connection() as db:
            db.execute('INSERT INTO chats(id,profile,title,updated,messages,history) VALUES(?,?,?,?,?,?)', (chat_id,self.profile,title,time.time_ns(),'[]','[]'))
            db.execute('UPDATE chat_state SET active_id=? WHERE profile=?', (chat_id,self.profile))
        return chat_id

    def load(self, chat_id):
        with self.memory._connection() as db:
            row = db.execute('SELECT title,messages,history,interrupted FROM chats WHERE id=? AND profile=?', (chat_id,self.profile)).fetchone()
        if not row:
            raise KeyError('Chat not found')
        return dict(id=chat_id,title=redact(row[0]),messages=json.loads(redact(row[1])),history=json.loads(redact(row[2])),interrupted=bool(row[3]))

    def save(self, chat_id, messages, history, interrupted=False):
        with self.memory._lock, self.memory._connection() as db:
            changed = db.execute('UPDATE chats SET messages=?,history=?,interrupted=?,updated=? WHERE id=? AND profile=?', (redact(json.dumps(messages)),redact(json.dumps(history[-40:])),int(interrupted),time.time_ns(),chat_id,self.profile)).rowcount
            if not changed:
                raise KeyError('Chat not found')

    def bulk(self, ids, action):
        ids = list(dict.fromkeys(ids))
        if not ids or action not in {'pin','unpin','delete'}:
            raise ValueError('Select chats and choose pin, unpin, or delete.')
        placeholders = ','.join('?' for _ in ids)
        with self.memory._lock, self.memory._connection() as db:
            found = db.execute(f'SELECT id FROM chats WHERE profile=? AND id IN ({placeholders})', (self.profile,*ids)).fetchall()
            if len(found) != len(ids):
                raise KeyError('One or more chats no longer exist.')
            if action == 'delete':
                db.execute('PRAGMA secure_delete=ON')
                db.execute(f'DELETE FROM turns WHERE profile=? AND chat_id IN ({placeholders})', (self.profile,*ids))
                db.execute(f'DELETE FROM chats WHERE profile=? AND id IN ({placeholders})', (self.profile,*ids))
                db.execute(f'UPDATE chat_state SET active_id=NULL WHERE profile=? AND active_id IN ({placeholders})', (self.profile,*ids))
            else:
                db.execute(f'UPDATE chats SET pinned=? WHERE profile=? AND id IN ({placeholders})', (int(action=='pin'),self.profile,*ids))
