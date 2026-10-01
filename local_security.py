"""Bounded requests and DNS-rebinding/cross-origin protection for local servers."""
import asyncio
import secrets
from starlette.responses import JSONResponse


class LocalGuard:
    def __init__(self, app, *, hosts, token=None):
        self.app, self.hosts, self.token = app, set(hosts), token

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        async def reject(status, detail):
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 1008})
            await JSONResponse({'detail': detail}, status_code=status,
                               headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})(scope, receive, send)
        pairs = scope.get('headers', [])
        guarded = {b'host', b'origin', b'x-jarvis-token', b'content-length', b'content-type'}
        if any(sum(k.lower() == name for k, _ in pairs) > 1 for name in guarded):
            return await reject(400, 'Duplicate security headers are blocked.')
        headers = {k.lower(): v.decode('latin1') for k, v in pairs}
        host = headers.get(b'host', '')
        if host not in self.hosts:
            return await reject(403, 'Invalid host')
        origin = headers.get(b'origin')
        if origin and origin != 'http://' + host:
            return await reject(403, 'Cross-origin requests are blocked')
        if self.token and scope['path'].startswith('/api/'):
            if not secrets.compare_digest(headers.get(b'x-jarvis-token', '').encode(), self.token.encode()):
                return await reject(401, 'Open the launch link from your terminal to connect.')
        if scope['type'] == 'websocket':
            return await self.app(scope, receive, send)
        if scope['method'] == 'POST' and b'content-type' in headers and headers[b'content-type'].split(';')[0].strip().lower() != 'application/json':
            return await reject(415, 'Use a JSON request.')
        if b'content-encoding' in headers:
            return await reject(415, 'Compressed requests are not supported.')
        limit = 131072
        try:
            size = int(headers.get(b'content-length', '0'))
            if not 0 <= size <= limit:
                return await reject(413, 'Request is too large.')
        except ValueError:
            return await reject(400, 'Invalid request length.')
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    event = await receive()
                    if event['type'] == 'http.disconnect':
                        return
                    body.extend(event.get('body', b''))
                    if len(body) > limit:
                        return await reject(413, 'Request is too large.')
                    if not event.get('more_body'):
                        break
        except TimeoutError:
            return await reject(408, 'Request timed out.')
        if scope['method'] == 'POST' and body and b'content-type' not in headers:
            return await reject(415, 'Use a JSON request.')
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)
