"""Shared standalone build entry point used by PR and release workflows."""
import subprocess
import sys
backend = {'win32': 'Windows', 'darwin': 'macOS'}.get(sys.platform, 'SecretService')
for name in ('swa', 'swahilipro'):
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--onefile', '--name', name, '--collect-data', 'certifi',
                    '--hidden-import', 'keyring.backends.' + backend,
                    'swa_cli.py'], check=True)
