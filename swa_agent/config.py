"""User-owned settings only. Repository files and environment cannot set API origin."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from .errors import AgentError

DEFAULT_API_ORIGIN = "https://swahilipro.com"


def origin(value):
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path not in ('', '/') or url.query or url.fragment
                or any(ord(c) <= 32 for c in value)):
            raise ValueError()
        port = url.port
        host = url.hostname.encode('idna').decode('ascii').lower()
        if ':' in host:
            host = '[' + host + ']'
        return 'https://' + host + (f':{port}' if port and port != 443 else '')
    except (ValueError, UnicodeError):
        raise AgentError('api_origin_must_be_an_https_origin', 2) from None


def data_root():
    home = Path.home()
    if sys.platform == 'win32':
        return home / 'AppData' / 'Local' / 'SwahiliPro'
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'SwahiliPro'
    return home / '.local' / 'share' / 'swahilipro'


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise AgentError('unsafe_state_directory', 3)
    if os.name != 'nt':
        path.chmod(0o700)
    return path


def write_json(path, value):
    private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    try:
        if path.is_symlink() or path.stat().st_size > 131072:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except FileNotFoundError:
        return None
    except (ValueError, OSError):
        raise AgentError('invalid_local_state', 3) from None


class Settings:
    def __init__(self, root=None):
        self.root = private_dir(root or data_root())

    def configure(self, value):
        value = origin(value)
        write_json(self.root / 'config.json', {'version': 1, 'origin': value})
        return value

    def load_origin(self):
        row = read_json(self.root / 'config.json')
        if row is None:
            return DEFAULT_API_ORIGIN
        if row.get('version') != 1:
            raise AgentError('run_swa_configure_with_your_api_origin', 2)
        return origin(row.get('origin', ''))

    def account_dir(self, api_origin):
        return private_dir(self.root / hashlib.sha256(api_origin.encode()).hexdigest())
