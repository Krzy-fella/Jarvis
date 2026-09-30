"""One in-flight provider request, isolated histories, durable retry identifiers."""
import copy
import threading
import time

import brain
from memory import MemoryStore
from session import Session
from privacy import redact
from .permissions import conversation_reply


class Busy(Exception):
    pass


class Conversations:
    def __init__(self, store, provider):
        self.store = store
        self.provider = provider
        self.lock = threading.RLock()
        self.worker_busy = False
        self.states = {}
        self.sessions = {}
        self.closed = False
        # A server restart must never replay an unfinished provider request.
        for device in store.list_devices():
            state = store.load(device['device_id'])
            if state and state.get('busy'):
                state.update(busy=False, status='Error', error='The previous request was interrupted. Send a new message to continue.')
                if state['history'] and state['history'][-1]['role'] == 'user':
                    state['history'].pop()
                store.save(device['device_id'],state)

    def _load(self, device_id):
        if device_id not in self.states:
            self.states[device_id] = self.store.load(device_id) or dict(messages=[],history=[],busy=False,status='Idle',error='',revision=0)
            self.sessions[device_id] = Session(MemoryStore(self.store.directory / 'memory', profile='satellite:' + device_id))
            self.sessions[device_id].start_chat()
        return self.states[device_id]

    def snapshot(self, device_id):
        with self.lock:
            state = copy.deepcopy(self._load(device_id))
            state.pop('history')
            return state

    def submit(self, device_id, request_id, text):
        with self.lock:
            if self.store.duplicate(device_id,request_id,text):
                return False
            if self.closed or self.worker_busy:
                raise Busy('Satellite is handling another message. Please try again when it finishes.')
            state = self._load(device_id)
            previous = copy.deepcopy(state)
            state.update(busy=True,status='Thinking',error='',revision=state['revision']+1)
            state['messages'].append(dict(role='user',content=redact(text),id=request_id))
            state['messages'] = state['messages'][-80:]
            state['history'].append(dict(role='user',content=redact(text)))
            try:
                self.store.save(device_id,state,request=(request_id,text))
            except Exception:
                self.states[device_id] = previous
                raise
            self.worker_busy = True
            try:
                threading.Thread(target=self._respond,args=(device_id,request_id,text),daemon=True).start()
            except Exception:
                self.worker_busy = False
                state.update(busy=False,status='Error',error='Satellite could not start this request. Send a new message to retry.')
                state['history'].pop()
                self.store.save(device_id,state)
                raise
            return True

    def _respond(self, device_id, request_id, text):
        try:
            with self.lock:
                state = self.states[device_id]
                history = copy.deepcopy(state['history'][-40:])
                session = self.sessions[device_id]
            if not self.store.active(device_id):
                raise ValueError('Device revoked')
            # The local commands below affect only this device's isolated memory.
            local = session.local_command(text)
            if local is None:
                result = brain.get_response(history,self.provider,owner=False,memory_context=session.memory_context,conversation_only=True)
                reply = conversation_reply(result)
            else:
                reply = local
            reply = redact(reply)[:16000]
            with self.lock:
                if self.closed or not self.store.active(device_id):
                    raise ValueError('Device no longer active')
                state['messages'].append(dict(role='assistant',content=reply,id=request_id+'-reply'))
                state['messages'] = state['messages'][-80:]
                if text.strip().lower() == '/forget all':
                    state['history'].clear()
                else:
                    state['history'].append(dict(role='assistant',content=reply))
                    state['history'] = state['history'][-40:]
                if local is None:
                    warning = session.save_turn(text,reply)
                    if warning:
                        state['error'] = 'Satellite memory could not be saved. This reply is still visible.'
                state.update(busy=False,status='Idle',revision=state['revision']+1)
                self.store.save(device_id,state)
        except Exception:
            with self.lock:
                state = self.states[device_id]
                if state['history'] and state['history'][-1]['role'] == 'user':
                    state['history'].pop()
                state.update(busy=False,status='Error',error='Satellite could not complete or save this reply. Check the PC provider and storage, then send a new message.',revision=state['revision']+1)
                try:
                    self.store.save(device_id,state)
                except Exception:
                    pass
                # No exception text, prompts, credentials or provider URLs in logs.
                print('[satellite beta] A conversation request failed; normal JARVIS remains available.')
        finally:
            with self.lock:
                self.worker_busy = False

    def close(self):
        with self.lock:
            self.closed = True
