"""Manage the local viewer lazily when a scene is first requested."""
import atexit
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

import requests

BASE_URL = 'http://127.0.0.1:8000'
_process = None
_opened = False


def _health():
    try:
        response = requests.get(BASE_URL + '/health', timeout=1)
        return response.ok and response.json().get('service') == 'jarvis-viewer'
    except (requests.RequestException, ValueError):
        return False


def _stop_owned_server():
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait()


atexit.register(_stop_owned_server)


def ensure_server():
    global _process
    if _health():
        return
    _process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('render_server.py'))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if _process.poll() is not None:
            raise RuntimeError('Viewer failed to start. Port 8000 may be occupied; run python render_server.py to see the error.')
        if _health():
            return
        time.sleep(0.1)
    _stop_owned_server()
    raise RuntimeError('Viewer did not become ready on port 8000.')


def render_scene(model_data):
    global _opened
    from render_server import Scene
    scene = Scene.model_validate(model_data).model_dump()
    ensure_server()
    response = requests.post(BASE_URL + '/scene', json=scene, timeout=10)
    response.raise_for_status()
    if not _opened:
        _opened = webbrowser.open(BASE_URL)
    return f'Scene delivered. Viewer: {BASE_URL}. {response.text}'
