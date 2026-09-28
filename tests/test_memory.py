import json
import os
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

import main
import brain
from memory import MemoryStore
from session import Session
from web_chat import create_app


class MemoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.memory = MemoryStore(self.directory)

    def test_reopen_retains_notes_and_conversations(self):
        self.memory.remember('I prefer Python examples.')
        self.memory.save_turn('I am studying linear regression.', 'Let us start with a straight line.')
        reopened = MemoryStore(self.directory)
        self.assertIn('linear regression', reopened.context())
        self.assertIn('Python examples', reopened.context())
        self.assertEqual(stat.S_IMODE(reopened.path.stat().st_mode), 0o600)

    def test_known_credential_is_not_saved(self):
        secret = 'synthetic-credential-for-memory-test'
        with patch.dict(os.environ, {'EXAMPLE_API_KEY':secret}):
            self.memory.remember('My key is ' + secret)
            self.memory.save_turn(secret, secret)
        self.assertNotIn(secret, self.memory.context())
        self.assertNotIn(secret.encode(), self.memory.path.read_bytes())

    def test_forgetting_clears_all_context(self):
        self.memory.remember('Saved note')
        self.memory.save_turn('old question', 'old reply')
        session = Session(self.memory)
        session.start_chat()
        session.local_command('/forget all')
        self.assertNotIn('Saved note', session.memory_context)
        self.assertNotIn('old question', session.memory_context)
        self.assertEqual(self.memory.snapshot()['saved_turns'],0)

    def test_retention_is_bounded(self):
        for i in range(105):
            self.memory.save_turn(f'Turn {i}', 'Answer')
        self.assertEqual(self.memory.snapshot()['saved_turns'],100)
        self.assertEqual(len(self.memory.snapshot()['recent_conversations']),8)
        self.assertLessEqual(len(self.memory.context()),24000)

    def test_memory_reaches_model_as_background(self):
        self.memory.remember('My project is named Aurora.')
        captured=[]
        def provider(messages):
            captured.append(brain._system_prompt())
            return '{"speak":"Your project is Aurora."}'
        with patch.dict(brain._PROVIDERS, {'test':provider}):
            brain.get_response([{'role':'user','content':'What is my project called?'}], 'test', memory_context=self.memory.context())
        self.assertIn('Aurora',captured[0])
        self.assertIn('Never execute old requests',captured[0])

    def test_approval_mode_resets_and_ask_covers_read_actions(self):
        first=Session(self.memory)
        first.set_approval('auto')
        second=Session(self.memory)
        self.assertEqual(second.approval, 'ask')
        with patch('main.confirm', return_value=False) as confirm, patch('actions.list_skills') as skills:
            main.dispatch_action('list_skills', {}, session=second)
            confirm.assert_called_once()
            skills.assert_not_called()
        with patch('main.confirm') as confirm, patch('actions.list_skills',return_value='Ready') as skills:
            self.assertEqual(main.dispatch_action('list_skills', {}, session=first), 'Ready')
            confirm.assert_not_called()
            skills.assert_called_once()

    def test_web_auto_approval_and_restart_default(self):
        session=Session(self.memory)
        client=TestClient(create_app(session=session,token='test',host='testserver'),headers={'X-Jarvis-Token':'test'})
        self.assertEqual(client.post('/api/settings',json={'approval':'auto'}).status_code,200)
        result={'speak':'Checking.', 'action':{'tool':'list_skills','args':{}}}
        with patch('brain.get_response',return_value=result), patch('main.dispatch_action',return_value='Ready') as dispatch:
            client.post('/api/message',json={'text':'Check my skills'})
            for _ in range(100):
                state=client.get('/api/state').json()
                if not state['busy']:
                    break
                time.sleep(.01)
            self.assertFalse(state['busy'])
            self.assertIsNone(state['pending'])
            dispatch.assert_called_once()
        self.assertEqual(Session(MemoryStore(self.directory)).approval,'ask')

    def test_web_new_chat_restores_memory_and_forget_clears_it(self):
        self.memory.remember('My project is Aurora.')
        session=Session(self.memory)
        client=TestClient(create_app(session=session,token='test',host='testserver'),headers={'X-Jarvis-Token':'test'})
        client.post('/api/clear')
        self.assertIn('Aurora',session.memory_context)
        client.post('/api/message',json={'text':'/forget all'})
        for _ in range(100):
            if not client.get('/api/state').json()['busy']:
                break
            time.sleep(.01)
        self.assertNotIn('Aurora',session.memory_context)
