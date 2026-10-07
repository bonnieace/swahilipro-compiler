"""Offline packaged smoke checks. No login, real keychain, or paid calls."""
import os
import json
from pathlib import Path
import subprocess
import tempfile

suffix = '.exe' if os.name == 'nt' else ''
for name in ('swa', 'swahilipro'):
    binary = str((Path('dist') / (name + suffix)).resolve())
    for args in (['-v'], ['-help'], ['login', '--help'], ['chat', '--help']):
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    result = subprocess.run([binary, 'check', '-'], input='andika("Habari")', capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout == '', result.stderr
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'chat'
        source.write_text('andika("offline")', encoding='utf-8')
        result = subprocess.run([binary, 'run', str(source)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and 'offline' in result.stdout, result.stderr
    with tempfile.TemporaryDirectory() as temporary:
        env = dict(os.environ, HOME=temporary, USERPROFILE=temporary)
        result = subprocess.run([binary, 'configure', '--api-origin', 'https://test.invalid', '--json'], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout
        # Exercise bundled HTTP/TLS imports and the OS keychain adapter without
        # attempting network access or writing a credential.
        result = subprocess.run([binary, 'whoami', '--json'], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 3, result.stdout
        assert json.loads(result.stdout)['error'] in ('login_required', 'os_keychain_unavailable', 'os_keychain_read_failed'), result.stdout
    print(name + ': packaged smoke checks passed')
