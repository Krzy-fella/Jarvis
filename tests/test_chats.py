import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from memory import MemoryStore
from chat_store import ChatStore
from session import Session
from web_chat import create_app


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.memory = MemoryStore(self.directory.name)
        self.store = ChatStore(self.memory)
        self.client = self.make_client()

    def make_client(self):
        return TestClient(create_app(token='test', host='testserver', session=Session(MemoryStore(self.directory.name))), headers={'X-Jarvis-Token':'test'})

    def wait(self, predicate=lambda s:not s['busy']):
        for _ in range(200):
            state = self.client.get('/api/state').json()
            if predicate(state):
                return state
            time.sleep(.01)
        self.fail('Request did not settle')

    def send(self, text, reply='Reply'):
        with patch('brain.get_response', return_value={'speak':reply,'action':{'tool':'none','args':{}}}):
            self.assertEqual(self.client.post('/api/message',json={'text':text}).status_code,202)
            return self.wait()

    def test_resume_after_switch_and_restart_uses_original_history(self):
        first = self.send('Project Aurora', 'We will use Python.')
        first_id = first['chat_id']
        self.client.post('/api/clear')
        second_id = self.send('Different topic')['chat_id']
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(self.client.post('/api/chats/open',json={'chat_id':first_id}).status_code,200)
        self.client = self.make_client()
        state = self.client.get('/api/state').json()
        self.assertEqual(state['chat_id'],first_id)
        self.assertEqual(state['messages'][1]['content'],'We will use Python.')
        with patch('brain.get_response',return_value={'speak':'Continue','action':{'tool':'none','args':{}}}) as model:
            self.client.post('/api/message',json={'text':'Continue where we left off','chat_id':first_id})
            self.wait()
            messages = model.call_args.args[0]
            self.assertIn('Aurora',messages[0]['content'])
            self.assertIn('Python',messages[1]['content'])
            self.assertNotIn('Different topic',str(messages))

    def test_pin_many_persists_and_unpin_restores_recency(self):
        first = self.send('First')['chat_id']
        self.client.post('/api/clear')
        second = self.send('Second')['chat_id']
        self.assertEqual(self.client.post('/api/chats/bulk',json={'ids':[first,second],'action':'pin'}).status_code,200)
        self.assertTrue(all(c['pinned'] for c in ChatStore(MemoryStore(self.directory.name)).list()))
        self.client.post('/api/chats/bulk',json={'ids':[second],'action':'unpin'})
        self.assertEqual(self.store.list()[0]['id'],first)

    def test_delete_multiple_removes_transcripts_and_linked_memory(self):
        first = self.send('Forget this topic')['chat_id']
        self.client.post('/api/clear')
        second = self.send('Another topic')['chat_id']
        self.memory.remember('Keep this explicit note')
        self.assertEqual(self.client.post('/api/chats/bulk',json={'ids':[first,second],'action':'delete'}).status_code,200)
        state = self.client.get('/api/state').json()
        self.assertEqual(state['chats'],[])
        self.assertEqual(state['messages'],[])
        self.assertIsNone(state['chat_id'])
        self.assertEqual(self.memory.snapshot()['saved_turns'],0)
        self.assertIn('explicit note',self.memory.context())
        self.assertEqual(self.client.post('/api/chats/open',json={'chat_id':first}).status_code,404)

    def test_missing_or_foreign_ids_make_bulk_operation_atomic(self):
        own = self.store.create('Own')
        other = ChatStore(MemoryStore(self.directory.name,profile='other'))
        foreign = other.create('Foreign')
        for bad in ['missing',foreign]:
            with self.assertRaises(KeyError):
                self.store.bulk([own,bad],'delete')
        self.assertEqual(len(self.store.list()),1)
        self.assertEqual(len(other.list()),1)

    def test_pending_actions_cannot_switch_or_delete_and_never_resume(self):
        result={'speak':'Ready for approval','action':{'tool':'run_terminal','args':{'command':'echo test'}}}
        with patch('brain.get_response',return_value=result), patch('main.dispatch_action') as dispatch:
            self.client.post('/api/message',json={'text':'Run a command'})
            state=self.wait(lambda s:s['pending'])
            chat_id=state['chat_id']
            self.assertEqual(self.client.post('/api/chats/open',json={'chat_id':chat_id}).status_code,409)
            self.assertEqual(self.client.post('/api/chats/bulk',json={'ids':[chat_id],'action':'delete'}).status_code,409)
            reopened=self.make_client().get('/api/state').json()
            self.assertFalse(reopened['busy'])
            self.assertIsNone(reopened['pending'])
            self.assertIn('interrupted',reopened['messages'][-1]['content'])
            dispatch.assert_not_called()

    def test_legacy_memory_imported_once(self):
        with tempfile.TemporaryDirectory() as directory:
            memory=MemoryStore(directory)
            memory.save_turn('Old question','Old answer')
            store=ChatStore(memory)
            self.assertEqual(store.list()[0]['title'],'Earlier conversations')
            self.assertEqual(store.load(store.active_id())['messages'][1]['content'],'Old answer')
            self.assertEqual(len(ChatStore(memory).list()),1)
            store.bulk([store.active_id()],'delete')
            self.assertEqual(ChatStore(memory).list(),[])
            self.assertEqual(memory.snapshot()['saved_turns'],0)

    def test_transcript_not_truncated_at_eighty_messages_and_secrets_redacted(self):
        secret='synthetic-chat-secret-value'
        chat_id=self.store.create('Long chat')
        messages=[{'role':'user','content':str(i)} for i in range(100)]
        messages.append({'role':'assistant','content':secret})
        with patch.dict(os.environ,{'TEST_API_KEY':secret}):
            self.store.save(chat_id,messages,[{'role':'user','content':secret}])
        loaded=self.store.load(chat_id)
        self.assertEqual(len(loaded['messages']),101)
        self.assertNotIn(secret,json.dumps(loaded))
        self.assertNotIn(secret.encode(),self.memory.path.read_bytes())

    def test_stale_tab_cannot_send_into_another_chat(self):
        first=self.send('First')['chat_id']
        self.client.post('/api/clear')
        self.send('Second')
        with patch('brain.get_response') as model:
            response=self.client.post('/api/message',json={'text':'Wrong tab','chat_id':first})
            self.assertEqual(response.status_code,409)
            model.assert_not_called()
