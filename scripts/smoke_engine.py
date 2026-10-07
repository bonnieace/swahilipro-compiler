"""Packaged stdio handshake and host-buffer read, with no network or credentials."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading

suffix = '.exe' if os.name == 'nt' else ''
for alias in ('swa', 'swahilipro'):
    binary = str((Path('dist') / (alias + suffix)).resolve())
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'workspace'
        root.mkdir()
        (root / 'file.txt').write_text('saved disk text', encoding='utf-8')
        home = Path(temporary) / 'home'
        home.mkdir()
        child = subprocess.Popen([binary, 'agent', '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=dict(os.environ, HOME=str(home), USERPROFILE=str(home)))
        events = queue.Queue()
        def reader():
            for line in child.stdout:
                events.put(json.loads(line))
        threading.Thread(target=reader, daemon=True).start()
        def send(mid, method, params):
            child.stdin.write((json.dumps({'v': 1, 'id': mid, 'method': method, 'params': params}) + '\n').encode())
            child.stdin.flush()
        try:
            assert events.get(timeout=15)['protocol'] == 1
            send('init', 'initialize', {'workspace': str(root), 'mode': 'host'})
            assert events.get(timeout=10)['result']['capabilities']['hostEdits']
            send('read', 'tool', {'name': 'read', 'arguments': {'path': 'file.txt'}})
            request = events.get(timeout=10)
            assert request['kind'] == 'read'
            send('reply', 'reply', {'callId': request['callId'], 'binding': request['binding'], 'result': {'exists': True, 'text': 'unsaved buffer', 'version': 2}})
            rows = [events.get(timeout=10), events.get(timeout=10)]
            result = next(row['result'] for row in rows if row.get('id') == 'read')
            assert result['text'] == 'unsaved buffer' and result['hash'] == hashlib.sha256(b'unsaved buffer').hexdigest()
            send('stop', 'shutdown', {})
            child.stdin.close()
            assert child.wait(timeout=10) == 0
            assert child.stderr.read() == b''
            assert (root / 'file.txt').read_text() == 'saved disk text'
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        print(alias + ': packaged stdio host-buffer smoke passed')
