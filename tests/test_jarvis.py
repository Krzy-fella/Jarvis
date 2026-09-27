import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import actions
import brain
import config
import main
import render_server


class BrainTests(unittest.TestCase):
    def test_ollama_cloud_only_rejects_local_model(self):
        with patch.object(config, 'OLLAMA_CLOUD_ONLY', True), patch.object(config, 'OLLAMA_MODEL', 'llama3.1'), patch('ollama.Client') as client:
            with self.assertRaises(brain.BrainError):
                brain._call_ollama([])
            client.assert_not_called()

    def test_ollama_cloud_request(self):
        with patch.object(config, 'OLLAMA_CLOUD_ONLY', True), patch.object(config, 'OLLAMA_MODEL', 'gpt-oss:120b-cloud'), patch('ollama.Client') as client:
            client.return_value.chat.return_value = {'message': {'content': '{"speak":"Hello"}'}}
            self.assertEqual(brain._call_ollama([]), '{"speak":"Hello"}')
            self.assertEqual(client.return_value.chat.call_args.kwargs['model'], 'gpt-oss:120b-cloud')
            self.assertEqual(client.return_value.chat.call_args.kwargs['format'], 'json')
            client.return_value.pull.assert_not_called()

    def test_ollama_auth_error_has_signin_instructions(self):
        import ollama
        with patch.object(config, 'OLLAMA_MODEL', 'gpt-oss:120b-cloud'), patch('ollama.Client') as client:
            client.return_value.chat.side_effect = ollama.ResponseError('Unauthorized', status_code=401)
            with self.assertRaisesRegex(brain.BrainError, 'ollama signin'):
                brain._call_ollama([])

    def test_invalid_response_cannot_dispatch(self):
        for raw in ['null', '[]', '42', '{"speak": 2}', '{"action":{"tool":[],"args":{}}}', '{"action":{"tool":"run_terminal","args":null}}']:
            with self.subTest(raw=raw):
                self.assertEqual(brain._safe_parse_json(raw)['action']['tool'], 'none')

    def test_fenced_response(self):
        result = brain._safe_parse_json('```json\n{"speak":"hello"}\n```')
        self.assertEqual(result, {'speak': 'hello', 'action': {'tool': 'none', 'args': {}}})

    def test_missing_key_fails_without_retries(self):
        with patch.object(config, 'GEMINI_API_KEY', ''), patch('brain.time.sleep') as sleep:
            with self.assertRaises(brain.BrainError):
                brain.get_response([], 'gemini')
            sleep.assert_not_called()

    def test_provider_error_redacts_key(self):
        with patch.object(config, 'GEMINI_API_KEY', 'test-secret'), patch.dict(brain._PROVIDERS, {'test': lambda _: (_ for _ in ()).throw(RuntimeError('test-secret'))}):
            with self.assertRaises(brain.BrainError) as caught:
                brain.get_response([], 'test', retries=0)
            self.assertNotIn('test-secret', str(caught.exception))


class ActionTests(unittest.TestCase):
    def test_file_creation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'file.txt'
            actions.create_file(str(path), 'hello')
            with self.assertRaises(FileExistsError):
                actions.create_file(str(path), 'replacement')
            self.assertEqual(path.read_text(), 'hello')

    def test_terminal_reports_stderr_and_status(self):
        result = json.loads(actions.run_terminal("printf problem >&2; exit 7"))
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['stderr'], 'problem')

    def test_blacklisted_command_does_not_execute(self):
        with patch('actions.subprocess.run') as run:
            with self.assertRaises(actions.UnsafeCommandError):
                actions.run_terminal('rm -rf /')
            run.assert_not_called()

    def test_cancel_prevents_file_creation(self):
        with patch('main.confirm', return_value=False), patch('actions.create_file') as create:
            self.assertIn('Cancelled', main.dispatch_action('create_file', {'path': 'test', 'content': ''}))
            create.assert_not_called()

    def test_invalid_dispatch_args(self):
        self.assertIn('arguments', main.dispatch_action('run_terminal', None))
        self.assertIn('invalid', main.dispatch_action([], {}))

    def test_result_retained_in_history(self):
        history = []
        main.record_result(history, {'speak': 'Trying', 'action': {'tool': 'none', 'args': {}}}, 'Cancelled')
        self.assertIn('Cancelled', history[0]['content'])

    def test_missing_adb_has_setup_hint(self):
        with patch('devices.adb_path', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'ADB is missing'):
                actions.connect_device('adb', 'scan')


class RenderTests(unittest.TestCase):
    def setUp(self):
        render_server._last_scene = None
        render_server._connected_clients.clear()

    def test_index_and_invalid_scene(self):
        with TestClient(render_server.app) as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.post('/scene', json={'shape': 'bad', 'size': -1}).status_code, 422)

    def test_websocket_broadcast_and_late_viewer(self):
        scene = {'shape': 'sphere', 'color': '#123abc', 'size': 2}
        with TestClient(render_server.app) as client:
            with client.websocket_connect('/ws') as websocket:
                self.assertEqual(client.post('/scene', json=scene).json()['clients'], 1)
                self.assertEqual(websocket.receive_json(), scene)
            with client.websocket_connect('/ws') as websocket:
                self.assertEqual(websocket.receive_json(), scene)
        self.assertEqual(render_server._connected_clients, [])


if __name__ == '__main__':
    unittest.main()
