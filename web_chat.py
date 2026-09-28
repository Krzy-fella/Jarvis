"""Loopback-only browser chat. No credentials or conversation files are served."""
import copy
import json
import secrets
import socket
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import brain
from privacy import redact
from presentation import readable_output
from session import Session
from memory import MemoryStore

WEB_ROOT = Path(__file__).resolve().parent / 'web'


def internet_available():
    import requests
    try:
        return requests.head('https://ollama.com', timeout=2, allow_redirects=True).status_code < 500
    except requests.RequestException:
        return False


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=16000)


class Decision(BaseModel):
    action_id: str
    approve: bool


class Interface(BaseModel):
    mode: str


class Settings(BaseModel):
    approval: str


def create_app(provider='ollama', owner=False, token=None, host='127.0.0.1:8765', on_switch=None, session=None):
    import main
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    token = token or secrets.token_urlsafe(32)
    session = session or Session(MemoryStore())
    session.start_chat()
    lock = threading.RLock()
    history = []
    state = {'messages': [], 'busy': False, 'pending': None, 'status': 'Ready',
             'provider': provider, 'profile': 'Nxnx · Owner' if owner else 'Personal',
             'approval': session.approval, 'revision': 0}
    pending_result = None
    app.state.token = token

    @app.middleware('http')
    async def protect(request: Request, call_next):
        if request.headers.get('host') != host:
            return JSONResponse({'detail': 'Invalid host'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != 'http://' + host:
            return JSONResponse({'detail': 'Cross-origin requests are blocked'}, status_code=403)
        if request.url.path.startswith('/api/'):
            provided = request.headers.get('x-jarvis-token', '')
            if not secrets.compare_digest(provided.encode(), token.encode()):
                return JSONResponse({'detail': 'Open the launch link from your terminal to connect.'}, status_code=401)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.get('/')
    def index():
        return FileResponse(WEB_ROOT / 'index.html')

    @app.get('/app.js')
    def javascript():
        return FileResponse(WEB_ROOT / 'app.js', media_type='text/javascript')

    @app.get('/style.css')
    def stylesheet():
        return FileResponse(WEB_ROOT / 'style.css', media_type='text/css')

    def add_message(role, content, label=None):
        state['messages'].append({'role': role, 'content': redact(content), 'label': label})
        state['messages'] = state['messages'][-80:]
        state['revision'] += 1

    def finish(result, output=''):
        with lock:
            if output:
                add_message('tool', readable_output(output), result['action']['tool'].replace('_', ' ').title())
            user = next((m['content'] for m in reversed(history) if m['role'] == 'user'), '')
            main.record_result(history, result, output)
            warning = session.save_turn(user, result['speak'])
            if warning:
                add_message('error', warning)
            state.update(busy=False, pending=None, status='Ready')
            state['revision'] += 1

    def respond(text):
        nonlocal pending_result
        try:
            local = session.local_command(text)
            if local is not None:
                with lock:
                    if text.strip().lower() == '/forget all':
                        history.clear()
                    add_message('assistant', local)
                    state.update(busy=False, status='Ready')
                return
            history.append({'role': 'user', 'content': text})
            result = brain.get_response(history, provider, owner=owner, memory_context=session.memory_context)
            with lock:
                add_message('assistant', result['speak'])
                if result['action']['tool'] != 'none' and session.approval == 'ask':
                    pending_result = result
                    state['pending'] = {'id': secrets.token_urlsafe(16),
                                        'tool': result['action']['tool'],
                                        'description': readable_output(json.dumps(result['action']['args']))}
                    state['status'] = 'Waiting for your approval'
                    return
                if result['action']['tool'] != 'none':
                    state['status'] = 'Running tool… automatic approval is enabled for this session'
            if result['action']['tool'] != 'none':
                execute(result)
            else:
                finish(result)
        except Exception as exc:
            with lock:
                if history and history[-1]['role'] == 'user':
                    history.pop()
                add_message('error', str(exc))
                state.update(busy=False, pending=None, status='Could not complete the request')

    def execute(result):
        try:
            output = main.dispatch_action(result['action']['tool'], result['action']['args'], confirmer=lambda _: True)
        except Exception as exc:
            output = f'Action failed: {redact(exc)}'
        finish(result, redact(output))

    @app.get('/api/state')
    def get_state():
        with lock:
            return copy.deepcopy(state)

    @app.post('/api/message', status_code=202)
    def message(body: Message):
        if not body.text.strip():
            raise HTTPException(422, 'Write a message first.')
        with lock:
            if state['busy']:
                raise HTTPException(409, 'Finish or cancel the current action first.')
            state.update(busy=True, status='Thinking…')
            add_message('user', body.text.strip())
            threading.Thread(target=respond, args=(body.text.strip(),), daemon=True).start()
        return {'accepted': True}

    @app.post('/api/decision', status_code=202)
    def decision(body: Decision):
        nonlocal pending_result
        with lock:
            pending = state['pending']
            if not pending or not secrets.compare_digest(pending['id'].encode(), body.action_id.encode()):
                raise HTTPException(409, 'This action is no longer awaiting approval.')
            result = pending_result
            pending_result = None
            state['pending'] = None
            state['revision'] += 1
            if body.approve:
                state['status'] = 'Running tool… long commands may take up to 1h 3m 50s'
                threading.Thread(target=execute, args=(result,), daemon=True).start()
            else:
                finish(result, 'Cancelled — you did not approve this action.')
        return {'accepted': True}

    @app.post('/api/clear')
    def clear():
        with lock:
            if state['busy']:
                raise HTTPException(409, 'Finish or cancel the current action first.')
            history.clear()
            session.start_chat()
            state['messages'].clear()
            state['revision'] += 1
        return {'cleared': True}

    @app.post('/api/settings')
    def settings(body: Settings):
        with lock:
            if state['busy']:
                raise HTTPException(409, 'Finish or cancel the current action before changing approval settings.')
            try:
                session.set_approval(body.approval)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            state['approval'] = session.approval
            state['revision'] += 1
        return {'approval': session.approval}

    @app.post('/api/interface')
    def switch(body: Interface):
        if body.mode not in {'text', 'menu', 'exit'}:
            raise HTTPException(422, 'Choose terminal, menu, or quit.')
        with lock:
            if state['busy']:
                raise HTTPException(409, 'Finish or cancel the current action first.')
            state.update(busy=True, status='Returning to your terminal…')
        if on_switch:
            on_switch(body.mode)
        return {'mode': body.mode}

    return app


def run_web_mode(provider, owner=False, session=None):
    import uvicorn
    token = secrets.token_urlsafe(32)
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', 8765))
    except OSError:
        sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    host = f'127.0.0.1:{sock.getsockname()[1]}'
    selected = {'mode': 'menu'}
    def switch(mode):
        selected['mode'] = mode
        server.should_exit = True
    app = create_app(provider, owner, token, host, switch, session)
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
    url = f'http://{host}/#{token}'
    def open_when_ready():
        for _ in range(300):
            if server.started:
                webbrowser.open(url)
                return
            if server.should_exit:
                return
            time.sleep(.1)
    print('\nWeb chat is local to this computer. Keep this terminal running.')
    print(f'Open this private launch link if your browser does not open:\n{url}')
    print('Use the web menu to switch to terminal chat. Ctrl+C returns to the menu.\n')
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return selected['mode']
