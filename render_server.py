"""
render_server.py — Minimal FastAPI + WebSocket bridge between JARVIS's
render_3d action and a Three.js frontend.

Run with:  python render_server.py
Then open: http://localhost:8000  in a browser, and it will render
whatever scene data JARVIS POSTs to /scene, live.
"""

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel, Field

STATIC_DIR = Path(__file__).resolve().parent / "static"


class Scene(BaseModel):
    shape: Literal["box", "sphere", "cone"] = "box"
    color: str = Field(default="#00ff88", pattern=r"^#[0-9a-fA-F]{6}$")
    size: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)

app = FastAPI(title="JARVIS 3D Render Server", docs_url=None, redoc_url=None, openapi_url=None)
from local_security import LocalGuard
app.add_middleware(LocalGuard, hosts={'127.0.0.1:8000', 'localhost:8000'})


@app.get("/health")
async def health():
    return {"service": "jarvis-viewer", "status": "ok"}

_connected_clients: list[WebSocket] = []
_last_scene: dict | None = None


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connected_clients.append(websocket)
    try:
        if _last_scene is not None:
            await websocket.send_json(_last_scene)
        while True:
            # Keep the connection open; we only push data server -> client.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _connected_clients:
            _connected_clients.remove(websocket)


@app.post("/scene")
async def post_scene(model_data: Scene):
    """Called by actions.render_3d(); broadcasts the scene to all viewers."""
    global _last_scene
    _last_scene = model_data.model_dump()
    payload = json.dumps(_last_scene)
    stale = []
    for client in list(_connected_clients):
        try:
            await client.send_text(payload)
        except Exception:  # noqa: BLE001
            stale.append(client)
    for client in stale:
        if client in _connected_clients:
            _connected_clients.remove(client)
    return {"status": "broadcast", "clients": len(_connected_clients)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
