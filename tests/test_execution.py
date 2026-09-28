import json
import os
import shlex
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import actions
import execution
from memory import MemoryStore
from session import Session
from web_chat import create_app


class RunnerTests(unittest.TestCase):
    def test_both_streams_arrive_before_exit_and_nonzero_is_preserved(self):
        events = []
        early = threading.Event()
        def observe(event):
            events.append(event)
            if event['kind'] == 'output':
                early.set()
        result = []
        def run():
            with execution.observe(observe):
                result.append(execution.run_command([sys.executable, '-u', '-c', "import time,sys; print('early'); print('problem',file=sys.stderr); time.sleep(.6); sys.exit(7)"], timeout=3))
        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(early.wait(2))
        self.assertTrue(thread.is_alive(), 'Output must be emitted while command is still running')
        thread.join(3)
        data = json.loads(result[0])
        self.assertEqual(data['exit_code'], 7)
        self.assertIn('early', data['stdout'])
        self.assertIn('problem', data['stderr'])
        self.assertEqual(events[-1]['kind'], 'ended')

    def test_timeout_keeps_partial_output_and_stops_process(self):
        events = []
        with execution.observe(events.append):
            result = json.loads(execution.run_command([sys.executable, '-u', '-c', "import time; print('started'); time.sleep(20)"], timeout=.3))
        self.assertEqual(result['status'], 'timeout')
        self.assertIn('started', result['stdout'])
        self.assertTrue(events[-1]['timed_out'])
        if os.name == 'posix':
            with self.assertRaises(ProcessLookupError):
                os.kill(events[0]['pid'], 0)

    def test_output_is_bounded_and_carriage_return_progress_parsed(self):
        events = []
        with execution.observe(events.append):
            result = json.loads(execution.run_command([sys.executable, '-c', "print('x'*100000); print('SYN Stealth Scan Timing: About 35.50% done; ETC: soon')"], timeout=3))
        self.assertLessEqual(len(result['stdout']), 12000)
        self.assertEqual(execution.nmap_progress('DNS Timing: About 99% done\rConnect Scan Timing: About 3.50% done'), ('Connect Scan',3.5))
        self.assertIsNone(execution.nmap_progress('A price is 30% lower'))

    @unittest.skipUnless(os.name == 'posix', 'POSIX terminal compatibility')
    def test_nmap_gets_private_controlling_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            fake = Path(directory) / 'nmap'
            fake.write_text('#!' + sys.executable + '\nimport os\nfd=os.open("/dev/tty",os.O_RDONLY | os.O_NONBLOCK)\nprint("private terminal ready")\nos.close(fd)\n')
            fake.chmod(0o700)
            result = json.loads(execution.run_command([str(fake)], timeout=3))
            self.assertEqual(result['exit_code'], 0, result['stderr'])
            self.assertIn('private terminal ready', result['stdout'])

    def test_nmap_preparation_preserves_shell_semantics_and_existing_stats(self):
        original = {'tool':'run_terminal','args':{'command':'nmap -sT 127.0.0.1'}}
        prepared = execution.prepare_action(original)
        self.assertIn('--stats-every 2s',prepared['args']['command'])
        self.assertNotIn('--stats-every',original['args']['command'])
        for command in ['nmap --stats-every 5s localhost', 'nmap localhost | cat', 'echo $(nmap localhost)', 'nmap --resume output.nmap']:
            action={'tool':'run_terminal','args':{'command':command}}
            self.assertEqual(execution.prepare_action(action),action)
        self.assertIn('--stats-every 2s',execution.prepare_action({'tool':'kali_tool','args':{'tool_name':'nmap','argument_string':'localhost'}})['args']['argument_string'])


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session = Session(MemoryStore(self.directory.name))
        self.client = self.new_client()

    def new_client(self):
        return TestClient(create_app(token='test',host='testserver',session=self.session),headers={'X-Jarvis-Token':'test'})

    def wait(self, predicate):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            state = self.client.get('/api/state').json()
            if predicate(state):
                return state
            time.sleep(.02)
        self.fail('No expected monitor state')

    @staticmethod
    def task(state):
        return next(m['execution'] for m in reversed(state['messages']) if m.get('execution'))

    def test_live_monitor_redacts_split_secret_and_persists_final_record(self):
        secret='synthetic-progress-secret-value'
        command=shlex.join([sys.executable,'-u','-c',"import time,sys; sys.stdout.write('synthetic-progress-'); sys.stdout.flush(); time.sleep(.1); print('secret-value'); print('Connect Scan Timing: About 42.50% done'); time.sleep(.6)"])
        result={'speak':'Running test','action':{'tool':'run_terminal','args':{'command':command}}}
        with patch.dict(os.environ,{'TEST_API_KEY':secret}), patch('brain.get_response',return_value=result):
            self.client.post('/api/message',json={'text':'Test monitor'})
            pending=self.wait(lambda s: s['pending'])
            self.assertEqual(self.task(pending)['stage'],'approval')
            self.client.post('/api/decision',json={'action_id':pending['pending']['id'],'approve':True})
            live=self.wait(lambda s: self.task(s)['percent']==42.5)
            self.assertTrue(live['busy'])
            self.assertNotIn(secret,json.dumps(live))
            self.assertIn('[REDACTED]',self.task(live)['log'])
            final=self.wait(lambda s: not s['busy'])
            task=self.task(final)
            self.assertEqual(task['stage'],'completed')
            self.assertEqual(task['exit_code'],0)
            self.assertEqual([s['stage'] for s in task['steps']],['preparing','approval','running','completed'])
            reopened=self.new_client().get('/api/state').json()
            self.assertEqual(self.task(reopened)['id'],task['id'])
            self.assertNotIn(secret,self.session.memory.path.read_text(errors='replace'))

    def test_cancelled_and_interrupted_never_execute(self):
        result={'speak':'Run?','action':{'tool':'run_terminal','args':{'command':'echo test'}}}
        with patch('brain.get_response',return_value=result),patch('main.dispatch_action') as dispatch:
            self.client.post('/api/message',json={'text':'test'})
            pending=self.wait(lambda s:s['pending'])
            restored=self.new_client().get('/api/state').json()
            self.assertEqual(self.task(restored)['stage'],'interrupted')
            self.client.post('/api/decision',json={'action_id':pending['pending']['id'],'approve':False})
            self.assertEqual(self.task(self.client.get('/api/state').json())['stage'],'cancelled')
            dispatch.assert_not_called()

    def test_nonzero_exit_is_failed_and_no_fake_percentage(self):
        result={'speak':'Run','action':{'tool':'run_terminal','args':{'command':'exit 7'}}}
        self.session.set_approval('auto')
        with patch('brain.get_response',return_value=result):
            self.client.post('/api/message',json={'text':'test'})
            final=self.wait(lambda s:not s['busy'])
        self.assertEqual(self.task(final)['stage'],'failed')
        self.assertEqual(self.task(final)['exit_code'],7)
        self.assertIsNone(self.task(final)['percent'])
