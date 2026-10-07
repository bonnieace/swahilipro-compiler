"""OS keychain only; refresh serialization spans all CLI processes for this origin."""
from contextlib import contextmanager
import json
import sys
from filelock import FileLock, Timeout
from .errors import AgentError


class Credentials:
    def __init__(self, api_origin, directory, backend=None):
        self.service = 'SwahiliPro:' + api_origin
        self.directory = directory
        if backend is None:
            try:
                # Explicit allowlist avoids plugin-configured plaintext fallbacks.
                if sys.platform == 'win32':
                    from keyring.backends.Windows import WinVaultKeyring
                    backend = WinVaultKeyring()
                elif sys.platform == 'darwin':
                    from keyring.backends.macOS import Keyring
                    backend = Keyring()
                else:
                    from keyring.backends.SecretService import Keyring
                    backend = Keyring()
                if backend.priority <= 0:
                    raise RuntimeError()
            except Exception:
                raise AgentError('os_keychain_unavailable', 3) from None
        self.backend = backend

    @contextmanager
    def locked(self):
        try:
            with FileLock(str(self.directory / 'credentials.lock'), timeout=1, mode=0o600):
                yield
        except Timeout:
            raise AgentError('another_account_command_is_running', 3) from None

    def read(self):
        try:
            raw = self.backend.get_password(self.service, 'active-account')
            if not raw:
                return None
            row = json.loads(raw)
            if not isinstance(row, dict) or row.get('version') != 1:
                raise ValueError()
            return row
        except Exception:
            raise AgentError('os_keychain_read_failed', 3) from None

    def write(self, row):
        try:
            self.backend.set_password(self.service, 'active-account', json.dumps(row))
        except Exception:
            raise AgentError('os_keychain_write_failed', 3) from None

    def clear(self):
        # Tombstone is idempotent across backends; contains no tokens.
        self.write({'version': 1, 'loggedOut': True})
