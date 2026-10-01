#!/usr/bin/env python3
"""Set up a cloned checkout and install a user-level jarvis launcher on Linux/macOS."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--voice', action='store_true', help='Also install optional speech packages')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    environment = root / '.venv'
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade', 'pip>=26.2'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], check=True)
    if options.voice:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements-voice.txt')], check=True)
    env_file = root / '.env'
    if not env_file.exists():
        shutil.copyfile(root / '.env.example', env_file)
        env_file.chmod(0o600)
    if os.name == 'nt':
        print('Setup complete. Run .venv\\Scripts\\python.exe main.py --provider ollama --mode auto')
        return
    launcher = Path.home() / '.local/bin/jarvis'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    body = '#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' + shlex.quote(str(root / 'main.py')) + ' --provider ollama --mode auto "$@"\n'
    if launcher.exists() and launcher.read_text() != body:
        backup = launcher.with_name('jarvis.previous')
        if backup.exists():
            raise RuntimeError('Launcher backup already exists; inspect jarvis.previous before replacing your launcher.')
        shutil.copy2(launcher, backup)
    launcher.write_text(body)
    launcher.chmod(0o755)
    print('Setup complete. Run jarvis; add ~/.local/bin to PATH if your shell cannot find it.')
    print('Configure .env and sign in with ollama signin. No model weights were downloaded.')


if __name__ == '__main__':
    main()
