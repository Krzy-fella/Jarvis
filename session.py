"""Approval preferences are process-local; only memory survives a restart."""
from dataclasses import dataclass, field
from memory import MemoryStore
from presentation import readable_output
import json
import sqlite3


@dataclass
class Session:
    memory: MemoryStore
    approval: str = 'ask'
    memory_context: str = field(default='', init=False)

    def start_chat(self):
        self.memory_context = self.memory.context()

    def save_turn(self, user, assistant):
        try:
            self.memory.save_turn(user, assistant)
            return ''
        except (OSError, sqlite3.Error) as exc:
            return f'Local memory could not be saved ({type(exc).__name__}). This reply was not saved.'

    def set_approval(self, mode):
        if mode not in {'ask', 'auto'}:
            raise ValueError('Choose ask or auto approval.')
        self.approval = mode

    def local_command(self, text):
        command, _, argument = text.strip().partition(' ')
        if command.lower() == '/remember':
            result = self.memory.remember(argument)
        elif command.lower() == '/memory':
            result = readable_output(json.dumps(self.memory.snapshot()))
        elif text.strip().lower() == '/forget all':
            result = self.memory.forget()
        else:
            return None
        self.start_chat()
        return result
