"""Satellite boundaries, failure isolation and durable device conversation tests."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import brain
import config
import main
from memory import MemoryStore
from satellite import SatelliteError
from satellite.cli import InstanceLock, bound_socket, run_cli
from satellite.pairing import Pairing, PairingRejected
from satellite.permissions import BLOCKED, CAPABILITIES
from satellite.server import create_app, RateLimiter
from satellite.sessions import Conversations, Busy
from satellite.settings import Settings
from satellite.storage import DeviceStore

ROOT = Path(__file__).resolve().parents[1]
REPLY = {'speak':'Hello from Satellite.', 'action':{'tool':'none','args':{}}}


def options(**changes):
    values = dict(satellite_devices=False,satellite_revoke=None,satellite_host=None,
                  satellite_port=None,satellite_cert=None,satellite_key=None,
                  satellite_insecure_http=True,provider='ollama')
    return SimpleNamespace(**(values | changes))


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Satellite worker did not finish in time')


class PairingTests(unittest.TestCase):
    def test_one_use_expiry_and_attempt_limit(self):
        now = [0]
        pairing = Pairing(clock=lambda:now[0],attempts=2)
        code = pairing.issue()
        self.assertNotIn(code, vars(pairing).values())
        pairing.consume(code)
        with self.assertRaises(PairingRejected): pairing.consume(code)
        code = pairing.issue(); now[0] = 300
        with self.assertRaises(PairingRejected): pairing.consume(code)
        code = pairing.issue()
        wrong = '000000' if code != '000000' else '000001'
        for _ in range(2):
            with self.assertRaises(PairingRejected): pairing.consume(wrong)
        with self.assertRaises(PairingRejected): pairing.consume(code)

    def test_simultaneous_pairing_consumes_only_once(self):
        pairing = Pairing(); code = pairing.issue(); accepted = []
        def consume():
            try: pairing.consume(code); accepted.append(True)
            except PairingRejected: pass
        threads = [threading.Thread(target=consume) for _ in range(10)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(accepted,[True])


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)/'satellite'
        self.environment = patch.dict(os.environ,{'JARVIS_SATELLITE_DIR':str(self.directory),'JARVIS_SATELLITE_ENABLED':'false'})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_disabled_default_and_explicit_launch(self):
        with patch('satellite.cli.serve') as serve, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_cli(options()),1); serve.assert_not_called()
            with patch.dict(os.environ,{'JARVIS_SATELLITE_ENABLED':'true'}):
                self.assertEqual(run_cli(options()),0)
            serve.assert_called_once()

    def test_missing_dependency_and_network_errors_are_contained(self):
        for error in (ImportError('optional dependency'), OSError('network down'), SystemExit(1)):
            with self.subTest(error=type(error).__name__), patch.dict(os.environ,{'JARVIS_SATELLITE_ENABLED':'true'}), patch('satellite.cli.serve',side_effect=error), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run_cli(options()),1)
                self.assertIn('Normal JARVIS',output.getvalue())

    def test_bind_failure_and_exclusive_instance_lock(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0)); occupied.listen()
            settings = Settings(port=occupied.getsockname()[1],data_dir=self.directory,insecure_http=True)
            with self.assertRaises(SatelliteError): bound_socket(settings)
        with InstanceLock(self.directory):
            with self.assertRaises(SatelliteError):
                with InstanceLock(self.directory): pass
        with InstanceLock(self.directory): pass

    def test_explicit_numeric_private_address_and_separate_storage_required(self):
        for host in ('0.0.0.0','::','8.8.8.8','example.com','169.254.1.2','ff02::1'):
            with self.subTest(host=host), self.assertRaises(SatelliteError):
                Settings(host=host,data_dir=self.directory,insecure_http=True).validate()
        for host in ('127.0.0.1','192.168.1.4','::1','fd12::1'):
            Settings(host=host,data_dir=self.directory,insecure_http=True).validate()
        with self.assertRaises(SatelliteError): Settings(data_dir=self.directory).validate()
        with self.assertRaises(SatelliteError): Settings(port=8765,data_dir=self.directory,insecure_http=True).validate()
        with self.assertRaises(SatelliteError): Settings(data_dir=ROOT/'private',insecure_http=True).validate()
        for directory in (self.directory, self.directory/'child', self.directory.parent):
            with patch.dict(os.environ,{'JARVIS_MEMORY_DIR':str(self.directory)}), self.assertRaises(SatelliteError):
                Settings(data_dir=directory,insecure_http=True).validate()

    def test_bad_certificate_is_reported_without_starting_server(self):
        with patch.dict(os.environ,{'JARVIS_SATELLITE_ENABLED':'true'}), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(run_cli(options(satellite_cert='/nonexistent/cert',satellite_key='/nonexistent/key',satellite_insecure_http=False)),1)
        self.assertIn('HTTPS certificate/key',out.getvalue())

    def test_normal_import_and_text_start_work_without_satellite_or_web_dependencies(self):
        # Fresh interpreter: optional imports cannot hide in sys.modules.
        script = '''
import builtins, os, sys
from unittest.mock import patch
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'satellite','fastapi','uvicorn'}:
        raise ImportError('optional feature missing')
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
import main, brain, actions, execution, session, memory, chat_store
with patch.object(sys,'argv',['jarvis','--mode','text']), patch('main.run_text_mode', side_effect=EOFError) as text:
    try: main.main()
    except EOFError: pass
    text.assert_called_once()
assert not any(name.startswith('satellite') for name in sys.modules)
'''
        result = subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=os.environ | {'JARVIS_MEMORY_DIR':str(self.directory/'pc'),'JARVIS_SATELLITE_ENABLED':'true'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_main_cli_routes_beta_before_creating_pc_memory(self):
        with patch.object(sys,'argv',['jarvis','--mode','satellite']), patch('satellite.cli.run_cli',return_value=1) as launch, patch('main.MemoryStore') as memory:
            self.assertEqual(main.main(),1)
        launch.assert_called_once(); memory.assert_not_called()


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = DeviceStore(Path(self.temp.name)/'satellite')

    def test_hashes_permissions_reconnect_expiry_and_revocation(self):
        device,credential = self.store.register('TV','tv')
        self.assertNotIn(credential.encode(),self.store.path.read_bytes())
        self.assertNotIn('credential_hash',device)
        if os.name != 'nt': self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)
        reopened = DeviceStore(self.store.directory)
        self.assertEqual(reopened.authenticate(credential)['device_id'],device['device_id'])
        self.assertIsNone(reopened.authenticate(credential+'x'))
        self.assertFalse(device['permissions']['control_pc'])
        with self.store.connection() as db: db.execute('UPDATE devices SET expires=0 WHERE id=?',(device['device_id'],))
        self.assertIsNone(reopened.authenticate(credential))
        second,token = reopened.register('Other','browser')
        self.store.revoke(second['device_id'])
        self.assertIsNone(reopened.authenticate(token))

    def test_device_limit_and_revoke_makes_room(self):
        devices = [self.store.register('TV','tv')[0] for _ in range(8)]
        with self.assertRaises(ValueError): self.store.register('Ninth','tv')
        self.store.revoke(devices[0]['device_id'])
        self.store.register('Replacement','tv')


class ConversationTests(DeviceTests):
    # Device tests intentionally reused against the same storage fixture.
    def setUp(self):
        super().setUp()
        self.device,self.token = self.store.register('TV','tv')
        self.device_id = self.device['device_id']
        self.manager = Conversations(self.store,'ollama')
        self.addCleanup(self.manager.close)

    def wait(self):
        wait_for(lambda:not self.manager.worker_busy)
        return self.manager.snapshot(self.device_id)

    def test_device_limit_and_revoke_makes_room(self):
        self.store.revoke(self.device_id)
        super().test_device_limit_and_revoke_makes_room()

    def test_all_actions_including_unknown_future_actions_are_blocked(self):
        tools = set(config.AVAILABLE_TOOLS) | set(CAPABILITIES) | {'future_pc_control'}
        tools.discard('none')
        with patch('main.dispatch_action') as dispatch, patch('actions.run_terminal') as terminal:
            for index,tool in enumerate(sorted(tools)):
                with self.subTest(tool=tool), patch('brain.get_response',return_value={'speak':'Executed!', 'action':{'tool':tool,'args':{'command':'echo should-not-run'}}}):
                    self.manager.submit(self.device_id,f'blocked-request-{index:04}',f'Try {tool}')
                    state = self.wait()
                    self.assertEqual(state['messages'][-1]['content'],BLOCKED)
                    self.assertFalse(state['busy'])
            dispatch.assert_not_called(); terminal.assert_not_called()

    def test_two_requests_do_not_mix_and_retries_are_idempotent(self):
        entered,release = threading.Event(),threading.Event()
        self.addCleanup(release.set)
        def respond(*args,**kwargs): entered.set(); release.wait(3); return REPLY
        with patch('brain.get_response',side_effect=respond) as provider:
            self.manager.submit(self.device_id,'first-request-0001','Hello')
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.manager.submit(self.device_id,'first-request-0001','Hello'))
            with self.assertRaises(ValueError): self.manager.submit(self.device_id,'first-request-0001','Different')
            other,_ = self.store.register('Other','tv')
            with self.assertRaises(Busy): self.manager.submit(other['device_id'],'second-request-01','Other message')
            self.assertEqual(self.manager.snapshot(other['device_id'])['messages'],[])
            release.set(); state = self.wait()
            self.assertEqual(len(state['messages']),2)
            provider.assert_called_once()
            self.assertTrue(provider.call_args.kwargs['conversation_only'])
            self.assertFalse(provider.call_args.kwargs['owner'])
        reopened = Conversations(DeviceStore(self.store.directory),'ollama'); self.addCleanup(reopened.close)
        self.assertEqual(reopened.snapshot(self.device_id)['messages'],state['messages'])
        self.assertFalse(reopened.submit(self.device_id,'first-request-0001','Hello'))

    def test_separate_device_memory_does_not_touch_pc_memory(self):
        pc = MemoryStore(Path(self.temp.name)/'pc'); pc.remember('Private PC note')
        original = pc.path.read_bytes()
        with patch.dict(os.environ,{'JARVIS_MEMORY_DIR':str(pc.directory)}):
            self.manager.submit(self.device_id,'remember-request-1','/remember Satellite-only note')
            self.wait()
            other,_ = self.store.register('Other','tv')
            self.manager.snapshot(other['device_id'])
            self.assertIn('Satellite-only note',self.manager.sessions[self.device_id].memory_context)
            self.assertNotIn('Private PC note',self.manager.sessions[self.device_id].memory_context)
            self.assertNotIn('Satellite-only note',self.manager.sessions[other['device_id']].memory_context)
            self.manager.submit(self.device_id,'forget-request-01','/forget all'); self.wait()
            self.assertNotIn('Satellite-only note',self.manager.sessions[self.device_id].memory_context)
        self.assertEqual(original,pc.path.read_bytes())

    def test_provider_failure_is_sanitized_and_next_request_works(self):
        with patch('brain.get_response',side_effect=RuntimeError('private-detail-123')), contextlib.redirect_stdout(io.StringIO()) as log:
            self.manager.submit(self.device_id,'failed-request-01','hello'); state = self.wait()
        self.assertEqual(state['status'],'Error')
        self.assertNotIn('private-detail-123',json.dumps(state)+log.getvalue())
        with patch('brain.get_response',return_value=REPLY):
            self.manager.submit(self.device_id,'recovery-request-1','hello again'); state = self.wait()
        self.assertEqual(state['status'],'Idle')
        self.assertEqual([item['content'] for item in self.manager.states[self.device_id]['history']],['hello again',REPLY['speak']])

    def test_storage_failure_rolls_back_acceptance(self):
        with patch.object(self.store,'save',side_effect=OSError('disk full')), patch('brain.get_response') as provider:
            with self.assertRaises(OSError): self.manager.submit(self.device_id,'failed-storage-01','hello')
            provider.assert_not_called()
        self.assertFalse(self.manager.worker_busy)
        self.assertEqual(self.manager.snapshot(self.device_id)['messages'],[])
        self.assertFalse(self.store.duplicate(self.device_id,'failed-storage-01','hello'))

    def test_restart_interrupts_inflight_without_replaying(self):
        state = {'messages':[{'role':'user','content':'hello','id':'interrupted-00001'}], 'history':[{'role':'user','content':'hello'}], 'busy':True,'status':'Thinking','error':'','revision':1}
        self.store.save(self.device_id,state,request=('interrupted-00001','hello'))
        with patch('brain.get_response') as provider:
            restarted = Conversations(self.store,'ollama'); self.addCleanup(restarted.close)
            result = restarted.snapshot(self.device_id)
            self.assertFalse(result['busy']); self.assertEqual(result['status'],'Error')
            self.assertFalse(restarted.submit(self.device_id,'interrupted-00001','hello'))
            provider.assert_not_called()

    def test_revoked_device_does_not_receive_running_reply(self):
        entered,release = threading.Event(),threading.Event(); self.addCleanup(release.set)
        def respond(*args,**kwargs): entered.set(); release.wait(3); return REPLY
        with patch('brain.get_response',side_effect=respond):
            self.manager.submit(self.device_id,'revoked-request-1','hello'); self.assertTrue(entered.wait(2))
            self.store.revoke(self.device_id); release.set(); state = self.wait()
        self.assertEqual(len(state['messages']),1)
        self.assertEqual(state['status'],'Error')


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name)/'satellite',insecure_http=True)
        self.store = DeviceStore(self.settings.data_dir); self.pairing = Pairing()
        self.app = create_app(self.settings,self.store,self.pairing)
        self.client = TestClient(self.app,base_url=self.settings.origin,client=('127.0.0.1',12345),raise_server_exceptions=False)
        self.client.__enter__(); self.addCleanup(self.client.__exit__,None,None,None)
        self.origin = {'Origin':self.settings.origin}

    def pair(self):
        response = self.client.post('/api/pair',headers=self.origin,json={'code':self.pairing.issue(),'device_name':'Test TV','device_type':'tv'})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def auth(self):
        result = self.pair()
        return self.origin | {'Authorization':'Bearer '+result['credential']}

    def test_pair_replay_and_no_credentials_in_state_or_static_content(self):
        code = self.pairing.issue(); body = {'code':code,'device_name':'TV'}
        first = self.client.post('/api/pair',headers=self.origin,json=body)
        self.assertEqual(first.status_code,200)
        self.assertEqual(self.client.post('/api/pair',headers=self.origin,json=body).status_code,403)
        state = self.client.get('/api/state',headers={'Authorization':'Bearer '+first.json()['credential']})
        self.assertEqual(state.status_code,200)
        self.assertNotIn(first.json()['credential'],state.text)
        self.assertNotIn('history',state.json()['conversation'])
        for path in ('/','/app.js','/style.css','/voice.js','/input-history.js'):
            response = self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn(first.json()['credential'],response.text)

    def test_authentication_origin_host_and_api_isolation(self):
        self.assertEqual(self.client.get('/api/state').status_code,401)
        self.assertEqual(self.client.get('/api/state',headers={'Authorization':'Bearer wrong'}).status_code,401)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/pair',json={}).status_code,403)
        headers = self.auth()
        for path in ('/api/execute','/api/config','/api/approval','/api/chats','/api/audio','/api/revoke','/openapi.json','/docs','/.env','/main.py'):
            self.assertEqual(self.client.get(path,headers=headers).status_code,404,path)
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws'): pass

    def test_input_limits_malformed_json_extra_fields_and_audio(self):
        headers = self.auth()
        valid = {'text':'hello','request_id':'test-request-0001'}
        for body in (valid | {'text':' '}, valid | {'text':'x'*4001}, valid | {'request_id':'short'}, valid | {'action':{'tool':'run_terminal'}}, valid | {'device_id':'other'}, valid | {'text':3}):
            self.assertEqual(self.client.post('/api/message',headers=headers,json=body).status_code,422)
        self.assertEqual(self.client.post('/api/message',headers=headers | {'Content-Type':'application/json'},content=b'{broken').status_code,422)
        self.assertEqual(self.client.post('/api/message',headers=headers | {'Content-Type':'application/json'},content=b'x'*8193).status_code,413)
        self.assertEqual(self.client.post('/api/message',headers=headers | {'Content-Type':'application/json'},content=iter([b'x'*4096,b'x'*4097])).status_code,413)
        self.assertEqual(self.client.post('/api/message',headers=headers | {'Content-Type':'audio/wav'},content=b'RIFFfake').status_code,415)
        self.assertEqual(self.client.get('/api/state',headers=headers).status_code,200)

    def test_duplicate_headers_and_public_peer_rejected(self):
        self.assertEqual(self.client.get('/',headers=[('Host',self.settings.authority),('Host','evil')]).status_code,400)
        with TestClient(self.app,base_url=self.settings.origin,client=('8.8.8.8',123)) as public:
            self.assertEqual(public.get('/').status_code,403)

    def test_message_retry_reconnect_and_rate_limit(self):
        headers = self.auth()
        body = {'text':'hello','request_id':'test-request-0001'}
        with patch('brain.get_response',return_value=REPLY) as provider:
            self.assertEqual(self.client.post('/api/message',headers=headers,json=body).status_code,202)
            wait_for(lambda:not self.client.get('/api/state',headers=headers).json()['conversation']['busy'])
            self.assertTrue(self.client.post('/api/message',headers=headers,json=body).json()['duplicate'])
            self.assertEqual(self.client.post('/api/message',headers=headers,json=body | {'text':'different'}).status_code,409)
            provider.assert_called_once()
        state = self.client.get('/api/state',headers=headers).json()['conversation']
        self.assertEqual(len(state['messages']),2)
        self.assertEqual(state['messages'][-1]['content'],REPLY['speak'])

    def test_storage_error_returns_sanitized_response_and_security_headers(self):
        headers = self.auth()
        with patch.object(self.store,'load',side_effect=OSError('private exception data')):
            result = self.client.get('/api/state',headers=headers)
        self.assertEqual(result.status_code,503)
        self.assertNotIn('private exception data',result.text)
        self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertEqual(self.client.get('/api/state',headers=headers).status_code,200)

    def test_auth_attempt_rate_limit(self):
        for _ in range(20): self.assertEqual(self.client.get('/api/state').status_code,401)
        self.assertEqual(self.client.get('/api/state').status_code,429)


class BrainScopeTests(unittest.TestCase):
    def test_prompt_isolation_during_concurrent_pc_and_satellite_requests(self):
        barrier = threading.Barrier(2); results = {}; errors = []
        def provider(messages):
            barrier.wait(timeout=3)
            results[messages[0]['content']] = brain._system_prompt()
            return json.dumps(REPLY)
        def run(satellite):
            try: brain.get_response([{'role':'user','content':'satellite' if satellite else 'pc'}],'test',owner=True,conversation_only=satellite,memory_context='Device note' if satellite else 'PC note')
            except Exception as exc: errors.append(exc)
        with patch.dict(brain._PROVIDERS,{'test':provider}), patch('actions.installed_tool_names',return_value=['sampletool']):
            threads = [threading.Thread(target=run,args=(flag,)) for flag in (True,False)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(5)
        self.assertEqual(errors,[])
        self.assertNotIn('sampletool',results['satellite']); self.assertNotIn('Nxnx, the owner',results['satellite'])
        self.assertNotIn('PC note',results['satellite']); self.assertIn('Device note',results['satellite'])
        self.assertIn('sampletool',results['pc']); self.assertIn('Nxnx, the owner',results['pc'])
        self.assertFalse(brain._conversation_only.get()); self.assertFalse(brain._owner.get())

    def test_raw_future_and_malformed_model_actions_reach_the_server_denial(self):
        from satellite.permissions import conversation_reply
        for action in ({'tool':'future_control','args':{}}, {'tool':'run_terminal','args':{}}, [], {'tool':'none','args':None}):
            with self.subTest(action=action), patch.dict(brain._PROVIDERS,{'test':lambda _:json.dumps({'speak':'Claimed success','action':action})}):
                result = brain.get_response([],'test',conversation_only=True)
                self.assertEqual(conversation_reply(result),BLOCKED)

    def test_context_restores_after_provider_failure(self):
        with patch.dict(brain._PROVIDERS,{'test':lambda _: (_ for _ in ()).throw(RuntimeError('failure'))}):
            with self.assertRaises(brain.BrainError): brain.get_response([],'test',retries=0,conversation_only=True)
        self.assertFalse(brain._conversation_only.get())

    def test_rate_limiter_recovers_and_bounds_keys(self):
        now = [0]; limiter = RateLimiter(2,max_keys=1,clock=lambda:now[0])
        self.assertTrue(limiter.allow('one')); self.assertTrue(limiter.allow('one'))
        self.assertFalse(limiter.allow('one')); self.assertFalse(limiter.allow('two'))
        now[0] = 60; self.assertTrue(limiter.allow('two'))

    @unittest.skipUnless(shutil.which('node'),'Node is only needed for browser speech fallback tests')
    def test_browser_voice_fallbacks(self):
        result = subprocess.run(['node',str(ROOT/'tests/satellite_voice_test.js')],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
