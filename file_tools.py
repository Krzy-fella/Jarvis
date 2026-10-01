"""Readable file access and exact, atomic edits with a recoverable backup."""
from pathlib import Path
import os
import shutil
import tempfile
import stat

MAX_FILE_BYTES = 1_000_000


def _path(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('A nonempty file path is required.')
    target = Path(path).expanduser().resolve()
    secret_names = {'.env', 'id_rsa', 'id_ed25519', 'credentials', 'credentials.json'}
    if (target.name in secret_names or target.name.startswith('.env.') and target.name != '.env.example'
            or target.suffix in {'.pem', '.key', '.p12', '.pfx'}
            or any(part in {'.ssh', '.gnupg', '.aws', '.git'} for part in target.parts)):
        raise ValueError('Credential and Git-internal files are not available through file actions.')
    return target


def read_file(path):
    target = _path(path)
    # Nonblocking open prevents a FIFO/device from hanging the assistant forever.
    descriptor = os.open(target, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Only regular text files can be read.')
        content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ValueError('File is too large (maximum 1 MB).')
    return content.decode('utf-8')


def create_file(path, content):
    target = _path(path)
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_FILE_BYTES:
        raise ValueError('Content must be UTF-8 text up to 1 MB.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        stream.write(content)
    return f'Created {target}'


def edit_file(path, old_text, new_text):
    target = _path(path)
    if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
        raise ValueError('old_text must be nonempty; new_text must be text.')
    content = read_file(str(target))
    count = content.count(old_text)
    if count != 1:
        raise ValueError(f'old_text must occur exactly once; found {count}. Read the file and use a more specific selection.')
    updated = content.replace(old_text, new_text, 1)
    if len(updated.encode('utf-8')) > MAX_FILE_BYTES:
        raise ValueError('Edited file would exceed 1 MB.')
    backup = target.with_name(target.name + '.jarvis.bak')
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, target.stat().st_mode & 0o777)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(content)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
        shutil.copymode(target, temporary)
        # Refuse to replace a file modified since the read above.
        if target.read_text(encoding='utf-8') != content:
            raise RuntimeError('File changed during edit; retry after reading it again.')
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return f'Updated {target}. Original saved to {backup}. Remove or rename that backup before another edit.'
