"""Security and lifecycle regression coverage from the project review."""
import json
import os
from pathlib import Path
import socket
import subprocess
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import actions
import brain
import file_tools
import main
from memory import MemoryStore
import render_server
from session import Session
from tv_mode import TVController, terminal_menu
from web_chat import create_app


class ReviewTests(unittest.TestCase):
    def test_prose_action_examples_never_execute(self):
        payload = json.dumps({'speak': 'Example', 'action': {'tool': 'run_terminal', 'args': {'command': 'echo example'}}})
        self.assertEqual(brain._safe_parse_json(payload)['action']['tool'], 'run_terminal')
        self.assertEqual(brain._safe_parse_json('Here is an example: ' + payload)['action']['tool'], 'none')
        self.assertEqual(brain._safe_parse_json(payload + '\nDo something else')['action']['tool'], 'none')
        self.assertEqual(brain._safe_parse_json('```json\n' + payload + '\n```')['action']['tool'], 'run_terminal')

    def test_response_size_is_bounded(self):
        self.assertEqual(brain._safe_parse_json('x' * 128001)['action']['tool'], 'none')

    @unittest.skipUnless(os.name == 'posix', 'POSIX special files')
    def test_special_file_read_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / 'pipe'
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, 'regular'):
                file_tools.read_file(str(fifo))
        with self.assertRaisesRegex(ValueError, 'regular'):
            file_tools.read_file('/dev/zero')

    def test_terminal_output_and_timeout_are_bounded(self):
        result = json.loads(actions.run_terminal("printf '%13000s' x", timeout=3))
        self.assertLessEqual(len(result['stdout']), 12000)
        result = json.loads(actions.run_terminal('sleep 5', timeout=.15))
        self.assertEqual(result['status'], 'timeout')
        with self.assertRaises(ValueError):
            actions.run_terminal('echo test', background='false')

    def test_render_rejects_foreign_origin_and_host(self):
        with TestClient(render_server.app, base_url='http://127.0.0.1:8000') as client:
            self.assertEqual(client.get('/', headers={'Host': 'evil.example'}).status_code, 403)
            self.assertEqual(client.post('/scene', json={}, headers={'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/scene', content='{}', headers={'Content-Type': 'text/plain'}).status_code, 415)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('ws://127.0.0.1:8000/ws', headers={'Origin': 'https://evil.example'}):
                    pass

    def test_terminal_tv_menu_explains_before_start(self):
        with patch('builtins.input', side_effect=['1', '5']), patch('builtins.print') as out, patch('tv_mode.controller') as controller:
            controller.status.return_value = dict(status='stopped', origin='', code='', error='')
            terminal_menu('ollama')
            self.assertIn('TV mode setup', out.call_args_list[0].args[0])
            controller.start.assert_called_once_with(provider='ollama')
        with patch('builtins.input', return_value='6'):
            self.assertEqual(main.choose_mode(), 'tv')


class TVTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.controller = TVController()
        self.addCleanup(self.controller.stop)
        self.env = patch.dict(os.environ, {'JARVIS_SATELLITE_DIR': self.directory.name + '/satellite'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def wait_status(self, status):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self.controller.status()
            if result['status'] == status:
                return result
            if result['status'] == 'failed' and status != 'failed':
                self.fail(result['error'])
            time.sleep(.05)
        self.fail('TV startup timed out: ' + self.controller.status()['status'])

    def test_real_preview_pair_stop_restart_and_persistence(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.controller.start(port=port)
        state = self.wait_status('running')
        self.assertEqual(state['origin'], f'http://127.0.0.1:{port}')
        self.assertRegex(state['code'], r'^\d{6}$')
        with self.assertRaisesRegex(ValueError, 'already'):
            self.controller.start(port=port)
        response = requests.post(state['origin'] + '/api/pair', json={'code': state['code'], 'device_name': 'Review TV', 'device_type': 'tv'}, headers={'Origin': state['origin']}, timeout=5)
        self.assertEqual(response.status_code, 200, response.text)
        credential = response.json()['credential']
        self.assertEqual(self.controller.stop()['status'], 'stopped')
        self.controller.start(port=port)
        state = self.wait_status('running')
        response = requests.get(state['origin'] + '/api/state', headers={'Authorization': 'Bearer ' + credential}, timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['capabilities']['control_pc'])
        self.assertEqual(self.controller.stop()['code'], '')

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required for HTTPS integration')
    def test_managed_https_with_verified_certificate(self):
        cert = Path(self.directory.name) / 'cert.pem'
        key = Path(self.directory.name) / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.controller.start(mode='https', host='127.0.0.1', port=port, certfile=str(cert), keyfile=str(key))
        state = self.wait_status('running')
        self.assertTrue(state['origin'].startswith('https://'))
        response = requests.post(state['origin'] + '/api/pair', json={'code':state['code'], 'device_name':'HTTPS review', 'device_type':'tv'}, headers={'Origin':state['origin']}, verify=str(cert), timeout=5)
        self.assertEqual(response.status_code, 200)
        self.controller.stop()

    def test_invalid_settings_and_occupied_port_fail_without_lan_fallback(self):
        for kwargs in [dict(mode='https', host='0.0.0.0'), dict(mode='https', host='8.8.8.8'), dict(mode='https', host='192.168.1.25'), dict(mode='insecure')]:
            with self.assertRaises(ValueError):
                self.controller.start(**kwargs)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); sock.listen()
            self.controller.start(port=sock.getsockname()[1])
            state = self.wait_status('failed')
            self.assertEqual(state['code'], '')
            self.assertIn('bind', state['error'])

    def test_local_tv_api_requires_auth_and_rejects_untrusted_requests(self):
        app = create_app(token='review-token', session=Session(MemoryStore(self.directory.name + '/pc')))
        with patch('tv_mode.controller', self.controller), TestClient(app, base_url='http://127.0.0.1:8765') as client:
            self.assertEqual(client.get('/api/tv').status_code, 401)
            client.headers['X-Jarvis-Token'] = 'review-token'
            self.assertIn('setup', client.get('/api/tv').json())
            self.assertEqual(client.post('/api/tv', json={'action': 'start', 'mode': 'insecure'}).status_code, 422)
            self.assertEqual(client.post('/api/tv', json={'action': 'stop'}, headers={'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/tv', json={'action': 'stop', 'command': 'echo unsafe'}).status_code, 422)
            self.assertEqual(client.post('/api/tv', json={'action': 'stop'}).json()['status'], 'stopped')
            self.assertEqual(client.post('/api/message', content=b'x'*131073, headers={'Content-Type': 'application/json'}).status_code, 413)
            self.assertEqual(client.get('/api/tv', headers=[('Host','127.0.0.1:8765'),('Host','evil.example')]).status_code, 400)
