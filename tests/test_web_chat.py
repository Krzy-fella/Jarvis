import json
import threading
import tempfile
from memory import MemoryStore
from session import Session
import time
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
import brain
from presentation import readable_output
from web_chat import create_app


class FormattingTests(unittest.TestCase):
    def test_envelope_with_prose_suffix(self):
        result = brain._safe_parse_json('Here you go: {"speak":"Hello, Nxnx.","action":{"tool":"none","args":{}}} Done.')
        self.assertEqual(result['speak'], 'Hello, Nxnx.')

    def test_malformed_action_only_recovers_speech(self):
        result = brain._safe_parse_json('{"speak":"Hello there.","action":{"tool":"run_terminal","args": BROKEN}}')
        self.assertEqual(result['speak'], 'Hello there.')
        self.assertEqual(result['action']['tool'], 'none')

    def test_invalid_envelope_not_shown_to_user(self):
        for text in ['{"speak":32,"action":{}}', '{"speak":"unterminated', "{'speak': 'broken'}"]:
            result = brain._safe_parse_json(text)
            self.assertNotIn('speak', result['speak'])
            self.assertEqual(result['action']['tool'], 'none')

    def test_plain_text_and_requested_code_preserved(self):
        text = 'Here is Python:\n```python\nprint({"hello": 42})\n```'
        self.assertEqual(brain._safe_parse_json(text)['speak'], text)

    def test_nested_speech_does_not_execute_nested_action(self):
        inner = json.dumps({'speak':'Hello', 'action':{'tool':'run_terminal', 'args':{'command':'echo test'}}})
        result = brain._safe_parse_json(json.dumps({'speak':inner}))
        self.assertEqual(result['speak'], 'Hello')
        self.assertEqual(result['action']['tool'], 'none')

    def test_tool_output_is_readable(self):
        self.assertEqual(readable_output('{"exit_code":0,"stdout":"Ready","stderr":""}'), 'Exit code: 0\n\nStdout: Ready')

    def test_owner_is_scoped_to_request(self):
        captured = []
        def call(messages):
            captured.append(brain._system_prompt())
            return '{"speak":"Hello"}'
        with patch.dict(brain._PROVIDERS, {'test':call}):
            brain.get_response([], 'test', owner=True)
            brain.get_response([], 'test')
        self.assertIn('Nxnx, the owner', captured[0])
        self.assertIn('do not bypass action confirmation', captured[0])
        self.assertNotIn('Nxnx, the owner', captured[1])


class WebTests(unittest.TestCase):
    def setUp(self):
        self.switch = MagicMock()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session = Session(MemoryStore(self.directory.name))
        self.app = create_app(token='test-token', host='127.0.0.1:8765', on_switch=self.switch, session=self.session)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:8765', headers={'X-Jarvis-Token':'test-token'})
        self.result = {'speak':'I can check that.', 'action':{'tool':'run_terminal','args':{'command':'echo test'}}}

    def wait_state(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.get('/api/state').json()
            if predicate(state):
                return state
            time.sleep(.01)
        self.fail('Background request did not finish')

    def test_auth_origin_and_no_file_exposure(self):
        for kwargs in [{'headers':{'X-Jarvis-Token':''}}, {'headers':{'Origin':'https://example.org'}}, {'headers':{'Host':'evil.example'}}]:
            self.assertIn(self.client.get('/api/state', **kwargs).status_code, (401,403))
        self.assertEqual(self.client.get('/.env').status_code, 404)
        self.assertEqual(self.client.get('/docs').status_code, 404)
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn("frame-ancestors 'none'", page.headers['content-security-policy'])
        self.assertNotIn('test-token', page.text)

    def test_confirmation_cancellation_and_replay(self):
        with patch('brain.get_response', return_value=self.result), patch('main.dispatch_action') as dispatch:
            self.assertEqual(self.client.post('/api/message', json={'text':'test'}).status_code, 202)
            state = self.wait_state(lambda s:s['pending'])
            dispatch.assert_not_called()
            self.assertEqual(self.client.post('/api/message', json={'text':'another'}).status_code, 409)
            self.assertEqual(self.client.post('/api/clear').status_code, 409)
            self.assertEqual(self.client.post('/api/interface', json={'mode':'text'}).status_code, 409)
            body = {'action_id':state['pending']['id'],'approve':False}
            self.assertEqual(self.client.post('/api/decision', json=body).status_code, 202)
            self.assertEqual(self.client.post('/api/decision', json=body).status_code, 409)
            dispatch.assert_not_called()
            self.assertIn('Cancelled', self.client.get('/api/state').json()['messages'][-1]['content'])

    def test_long_tool_does_not_block_state_and_runs_once(self):
        release = threading.Event()
        entered = threading.Event()
        def tool(*args, **kwargs):
            entered.set()
            release.wait(3)
            return '{"exit_code":0,"stdout":"Completed"}'
        try:
            with patch('brain.get_response', return_value=self.result), patch('main.dispatch_action', side_effect=tool) as dispatch:
                self.client.post('/api/message', json={'text':'test'})
                state = self.wait_state(lambda s:s['pending'])
                body = {'action_id':state['pending']['id'],'approve':True}
                self.client.post('/api/decision', json=body)
                self.assertTrue(entered.wait(1))
                self.assertTrue(self.client.get('/api/state').json()['busy'])
                self.assertEqual(self.client.post('/api/decision', json=body).status_code, 409)
                release.set()
                final = self.wait_state(lambda s:not s['busy'])
                self.assertIn('Stdout: Completed', final['messages'][-1]['content'])
                dispatch.assert_called_once()
        finally:
            release.set()

    def test_failure_can_retry_and_menu_works(self):
        with patch('brain.get_response', side_effect=brain.BrainError('Provider unavailable')):
            self.client.post('/api/message', json={'text':'hi'})
            state = self.wait_state(lambda s:not s['busy'])
            self.assertEqual(state['messages'][-1]['role'],'error')
        self.assertEqual(self.client.post('/api/interface', json={'mode':'text'}).status_code, 200)
        self.switch.assert_called_once_with('text')


class VoiceTests(unittest.TestCase):
    def test_microphone_session_reused_and_closed(self):
        try:
            import voice
        except ImportError:
            self.skipTest('Optional voice dependencies not installed')
        with patch.object(voice, '_microphone', None), patch.object(voice.sr, 'Microphone') as mic, patch.object(voice._recognizer, 'adjust_for_ambient_noise'):
            first = voice._get_microphone()
            self.assertIs(voice._get_microphone(), first)
            mic.assert_called_once()
            mic.return_value.__enter__.assert_called_once()
            voice.close_microphone()
            mic.return_value.__exit__.assert_called_once()
