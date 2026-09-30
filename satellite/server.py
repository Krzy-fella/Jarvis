"""Restricted Satellite API; entirely separate from the loopback PC web app."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
import ipaddress
from pathlib import Path
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from .models import PairRequest, MessageRequest
from .pairing import PairingRejected
from .permissions import CAPABILITIES
from .sessions import Conversations, Busy

WEB_ROOT = Path(__file__).resolve().parents[1] / 'web/satellite'
MAX_BODY = 8192


class RateLimiter:
    def __init__(self, limit, window=60, max_keys=1024, clock=time.monotonic):
        self.limit, self.window, self.max_keys, self.clock = limit, window, max_keys, clock
        self.entries = {}
        self.lock = threading.Lock()

    def allow(self, key):
        with self.lock:
            now = self.clock()
            expired = [k for k,v in self.entries.items() if not v or now-v[-1] >= self.window]
            for k in expired:
                del self.entries[k]
            if key not in self.entries and len(self.entries) >= self.max_keys:
                return False
            values = self.entries.setdefault(key,deque())
            while values and now-values[0] >= self.window:
                values.popleft()
            if len(values) >= self.limit:
                return False
            values.append(now)
            return True


class Guard:
    """Bound the body before FastAPI parses it, including chunked/no-length input."""
    def __init__(self, app, settings, store):
        self.app, self.settings, self.store = app, settings, store
        self.traffic = RateLimiter(180)
        self.total = RateLimiter(1200,max_keys=1)
        self.bad_auth = RateLimiter(20)
        self.headers = {
            'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer',
            'X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            'Permissions-Policy':'camera=(), geolocation=(), microphone=(self)',
        }

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type':'websocket.close','code':1008})
            return
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)

        async def reject(code, message):
            await JSONResponse({'detail':message},status_code=code,headers=self.headers)(scope,receive,send)

        pairs = scope.get('headers',[])
        # Avoid ambiguous duplicate authority/auth/content-length headers.
        for name in (b'host',b'origin',b'authorization',b'content-length'):
            if sum(key.lower()==name for key,value in pairs)>1:
                return await reject(400,'Ambiguous request headers.')
        headers = {k.decode('latin1').lower():v.decode('latin1') for k,v in pairs}
        if headers.get('host') != self.settings.authority:
            return await reject(403,'Invalid Satellite host.')
        origin = headers.get('origin')
        if (origin is not None and origin != self.settings.origin) or headers.get('sec-fetch-site') == 'cross-site':
            return await reject(403,'Cross-origin requests are blocked.')
        if scope['method'] == 'POST' and origin != self.settings.origin:
            return await reject(403,'A same-origin request is required.')
        peer = scope.get('client')
        try:
            address = ipaddress.ip_address(peer[0])
            if not address.is_private or address.is_unspecified:
                return await reject(403,'Only local network clients are allowed.')
        except (ValueError,TypeError):
            return await reject(403,'A local network client address is required.')
        if not self.total.allow('all') or not self.traffic.allow(str(address)):
            return await reject(429,'Too many requests. Wait a minute and reconnect.')
        if scope['path'].startswith('/api/') and scope['path'] != '/api/pair':
            credential = headers.get('authorization','')
            try:
                device = self.store.authenticate(credential[7:]) if credential.startswith('Bearer ') else None
            except Exception:
                return await reject(503,'Satellite device storage is unavailable.')
            if device is None:
                code = 401 if self.bad_auth.allow(str(address)) else 429
                return await reject(code,'Pair this device again on the PC.' if code==401 else 'Too many authentication attempts.')
            scope.setdefault('state',{})['device'] = device
        if scope['method'] == 'POST' and headers.get('content-type','').split(';')[0].strip().lower() != 'application/json':
            return await reject(415,'Satellite accepts JSON text requests only; audio uploads are unavailable.')
        if 'content-encoding' in headers:
            return await reject(415,'Compressed requests are not supported.')
        try:
            length = int(headers.get('content-length','0'))
            if length < 0 or length > MAX_BODY:
                return await reject(413,'Request is too large.')
        except ValueError:
            return await reject(400,'Invalid request length.')
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body',b''))
                    if len(body) > MAX_BODY:
                        return await reject(413,'Request is too large.')
                    if not message.get('more_body',False):
                        break
        except TimeoutError:
            return await reject(408,'Request timed out.')
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        response_started = False
        async def safe_send(message):
            nonlocal response_started
            if message['type'] == 'http.response.start':
                response_started = True
                message['headers'] = list(message.get('headers',[])) + [(k.lower().encode(),v.encode()) for k,v in self.headers.items()]
            await send(message)
        try:
            await self.app(scope,replay,safe_send)
        except Exception:
            # No exception details or request body in logs/responses.
            print('[satellite beta] A request failed; normal JARVIS remains available.')
            if not response_started:
                await reject(503,'Satellite is temporarily unavailable. Try again or check the PC.')


def create_app(settings, store, pairing, provider='ollama'):
    settings.validate()
    conversations = Conversations(store,provider)
    messages = RateLimiter(6,max_keys=8)
    @asynccontextmanager
    async def lifespan(app):
        yield
        conversations.close()
    app = FastAPI(docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.add_middleware(Guard,settings=settings,store=store)

    @app.exception_handler(RequestValidationError)
    async def invalid(request,exc):
        return JSONResponse({'detail':'Invalid Satellite request. Check the fields and message length.'},status_code=422)

    @app.exception_handler(Exception)
    async def failed(request,exc):
        print('[satellite beta] A request failed; normal JARVIS remains available.')
        return JSONResponse({'detail':'Satellite is temporarily unavailable. Try again or check the PC.'},status_code=503)

    @app.get('/')
    def page():
        return FileResponse(WEB_ROOT/'index.html')

    @app.get('/app.js')
    def javascript():
        return FileResponse(WEB_ROOT/'app.js',media_type='text/javascript')

    @app.get('/voice.js')
    def voice_javascript():
        return FileResponse(WEB_ROOT/'voice.js',media_type='text/javascript')

    @app.get('/input-history.js')
    def input_history():
        return FileResponse(WEB_ROOT.parent/'input-history.js',media_type='text/javascript')

    @app.get('/style.css')
    def stylesheet():
        return FileResponse(WEB_ROOT/'style.css',media_type='text/css')

    @app.post('/api/pair')
    def pair(body: PairRequest):
        if not body.device_name.strip():
            raise HTTPException(422,'Give this device a name.')
        try:
            pairing.consume(body.code)
            device, credential = store.register(body.device_name.strip(),body.device_type)
        except PairingRejected as exc:
            raise HTTPException(403,str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None
        return {'device':device,'credential':credential}

    @app.get('/api/state')
    def state(request: Request):
        device = request.state.device
        return {'device':device,'capabilities':dict(CAPABILITIES),'conversation':conversations.snapshot(device['device_id'])}

    @app.post('/api/message',status_code=202)
    def message(body: MessageRequest,request: Request):
        if not body.text.strip():
            raise HTTPException(422,'Write a message first.')
        device_id = request.state.device['device_id']
        try:
            if store.duplicate(device_id,body.request_id,body.text.strip()):
                return {'accepted':True,'duplicate':True}
            if not messages.allow(device_id):
                raise HTTPException(429,'Please wait a minute before sending more messages.')
            created = conversations.submit(device_id,body.request_id,body.text.strip())
        except Busy as exc:
            raise HTTPException(409,str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from None
        return {'accepted':True,'duplicate':not created}

    return app
