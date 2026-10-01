"""Read-only capability checks; no secrets, device IDs or account data."""
import importlib.util
import shutil

from devices import adb_path
from tool_inventory import KALI_TOOLSET


def skill_report():
    inventory = sorted({name for names in KALI_TOOLSET.values() for name in names})
    available = [name for name in inventory if shutil.which(name)]
    return {
        'actions': {
            'open_app': 'ready; requested app must be on PATH',
            'run_terminal': 'ready; follows the current session approval setting',
            'create_file': 'ready; refuses overwrite',
            'read_file': 'ready; excludes credential files',
            'edit_file': 'ready; exact replacement with backup and confirmation',
            'research': 'ready; no-key metasearch with Wikipedia fallback; requires internet',
            'render_3d': 'ready; viewer starts on demand',
            'android': 'ADB found; connect and authorize your phone' if adb_path() else 'install Android platform-tools or set JARVIS_ADB_PATH',
            'bluetooth': 'bluetoothctl found; adapter/pairing still required' if shutil.which('bluetoothctl') else 'install BlueZ on Linux',
            'ios': 'basic USB listing/info only; requires libimobiledevice tools',
        },
        'voice_packages': {name: importlib.util.find_spec(name) is not None for name in ['speech_recognition', 'pyaudio', 'pyttsx3', 'edge_tts']},
        'audio_player': bool(shutil.which('ffplay')),
        'optional_tools': {'installed_count': len(available), 'listed_count': len(inventory), 'installed': available, 'missing': [name for name in inventory if name not in available]},
        'note': 'Executable detection is not a functional test. Install only the optional tools you actually use.',
    }
