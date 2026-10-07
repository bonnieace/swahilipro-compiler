import os
from pathlib import Path
import sys
import threading
import time

import pytest

from swa_agent.config import read_json
from swa_agent.engine import ToolEngine
from swa_agent.errors import AgentError
from swa_agent.executor import run
from swa_agent.workspace import Workspace, digest

posix = pytest.mark.skipif(os.name != 'posix', reason='Native mutation/execution adapter is POSIX-only')


@pytest.fixture
def engine(tmp_path):
    workspace = tmp_path / 'repo'
    workspace.mkdir()
    return ToolEngine(str(workspace), tmp_path / 'state')


@pytest.mark.parametrize('path', ['../outside', '/etc/passwd', '.git/config', '.env', 'sub/.env.local', '.ssh/id_ed25519', 'credentials.json', 'secrets.toml', 'key.pem', 'C:/Users/file', 'sub\\file', 'file\x00'])
def test_paths_exclude_traversal_and_secrets(engine, path):
    with pytest.raises(AgentError):
        engine.workspace.path(path)


def test_ignores_nested_patterns_secrets_and_binary(engine):
    root = engine.workspace.root
    (root / '.gitignore').write_text('build/\n*.log\n')
    (root / '.swaignore').write_text('private.txt\n')
    (root / 'build').mkdir()
    (root / 'build/out.txt').write_text('excluded')
    (root / 'sub').mkdir()
    (root / 'sub/.gitignore').write_text('hidden.txt\n')
    for path in ('private.txt', 'debug.log', '.env', 'sub/hidden.txt', 'visible.txt'):
        (root / path).write_text('needle')
    assert engine.workspace.search('needle')['matches'] == [{'path': 'visible.txt', 'line': 1, 'text': 'needle'}]
    for path in ('private.txt', 'debug.log', 'sub/hidden.txt', 'build/out.txt'):
        with pytest.raises(AgentError):
            engine.workspace.read(path)
    (root / 'binary').write_bytes(b'\x00binary')
    (root / 'huge').write_text('a'*32769)
    for path in ('binary', 'huge'):
        with pytest.raises(AgentError, match='text_file_limit'):
            engine.workspace.read(path)


def test_links_never_expose_external_contents(engine, tmp_path):
    outside = tmp_path / 'outside'
    outside.write_text('secret')
    try:
        (engine.workspace.root / 'link').symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation unavailable')
    with pytest.raises(AgentError, match='link_refused'):
        engine.workspace.read('link')
    os.link(outside, engine.workspace.root / 'hardlink')
    with pytest.raises(AgentError, match='special_file'):
        engine.workspace.read('hardlink')


@posix
def test_approval_exact_edit_atomic_apply_and_conditional_undo(engine):
    path = engine.workspace.root / 'file.txt'
    path.write_text('before\n')
    proposals = []
    def approve(p):
        proposals.append(p)
        assert p['baseHash'] == digest('before\n')
        assert '-before' in p['diff'] and '+after' in p['diff']
        return True
    result = engine.invoke('edit', {'path': 'file.txt', 'baseHash': digest('before\n'), 'text': 'after\n'}, approve)
    assert path.read_text() == 'after\n'
    journal = read_json(engine.directory / (result['operationId'] + '.json'))
    assert journal['approvalHash'] == proposals[0]['approvalHash'] and journal['state'] == 'applied'
    engine.invoke('undo', {'operationId': result['operationId']}, lambda p: True)
    assert path.read_text() == 'before\n'
    with pytest.raises(AgentError, match='stale_file'):
        engine.invoke('undo', {'operationId': result['operationId']}, lambda p: True)


def test_denial_and_stale_edit_preserve_user_changes(engine):
    path = engine.workspace.root / 'file.txt'
    path.write_text('before')
    args = {'path': 'file.txt', 'baseHash': digest('before'), 'text': 'after'}
    with pytest.raises(AgentError, match='approval_required'):
        engine.invoke('edit', args, lambda p: False)
    assert path.read_text() == 'before'
    def approve(p):
        path.write_text('user change')
        return True
    with pytest.raises(AgentError, match='stale_file'):
        engine.invoke('edit', args, approve)
    assert path.read_text() == 'user change'


@posix
def test_new_file_cannot_replace_existing_file_and_has_no_automatic_delete_undo(engine):
    result = engine.invoke('edit', {'path': 'new.txt', 'text': 'new', 'baseHash': None}, lambda p: True)
    with pytest.raises(AgentError, match='stale_file'):
        engine.invoke('edit', {'path': 'new.txt', 'text': 'replace', 'baseHash': None}, lambda p: True)
    with pytest.raises(AgentError, match='not_undoable'):
        engine.invoke('undo', {'operationId': result['operationId']}, lambda p: True)


def test_host_edit_uses_dirty_buffer_and_does_not_touch_disk(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    path = root / 'file.txt'
    path.write_text('disk')
    calls = []
    def host(kind, payload, cancel):
        calls.append((kind, payload))
        if kind == 'read':
            return {'exists': True, 'text': 'dirty buffer', 'version': 7}
        assert payload['baseHash'] == digest('dirty buffer') and payload['version'] == 7
        return {'applied': True, 'hash': digest('new buffer')}
    engine = ToolEngine(str(root), tmp_path / 'state', host)
    result = engine.invoke('edit', {'path': 'file.txt', 'text': 'new buffer', 'baseHash': digest('dirty buffer')}, lambda p: True)
    assert result['hostManaged'] and path.read_text() == 'disk'
    assert [kind for kind, _ in calls] == ['read', 'read', 'apply']


def test_host_dirty_version_change_refuses_apply(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    calls = []
    def host(kind, payload, cancel):
        calls.append(kind)
        assert kind == 'read'
        return {'exists': True, 'text': 'same content', 'version': len(calls)}
    engine = ToolEngine(str(root), tmp_path / 'state', host)
    with pytest.raises(AgentError, match='stale_file'):
        engine.invoke('edit', {'path': 'file.txt', 'text': 'new', 'baseHash': digest('same content')}, lambda p: True)
    assert calls == ['read', 'read']


@posix
def test_swahili_syntax_check_does_not_execute(engine):
    result = engine.syntax('example.swa', 'andika("SHOULD_NOT_PRINT")', threading.Event())
    assert result['valid'] and result['diagnostic'] == '' and result['syntaxOnly']
    assert not engine.syntax('example.swa', '@', threading.Event())['valid']


@posix
def test_command_requires_approval_and_does_not_inherit_credentials(engine, monkeypatch):
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'do-not-pass')
    argv = [sys.executable, '-c', 'import os; print(os.environ.get("AWS_SECRET_ACCESS_KEY", "absent"))']
    args = {'argv': argv, 'cwd': '.', 'timeout': 5}
    with pytest.raises(AgentError, match='approval_required'):
        engine.invoke('execute', args, lambda p: False)
    result = engine.invoke('execute', args, lambda p: True)
    assert result['output'].strip() == 'absent' and result['exitCode'] == 0
    assert 'do-not-pass' not in ''.join(p.read_text() for p in engine.directory.glob('*.json'))


@posix
def test_command_timeout_output_limit_and_cancellation(engine):
    root = str(engine.workspace.root)
    result = run([sys.executable, '-c', 'while True: pass'], root, threading.Event(), timeout=1)
    assert result['outcome'] == 'timeout'
    result = run([sys.executable, '-c', 'print("x"*1000000)'], root, threading.Event(), limit=1000)
    assert result['outcome'] == 'output_limit' and len(result['output']) <= 1000
    cancel = threading.Event()
    timer = threading.Timer(.1, cancel.set)
    timer.start()
    result = run([sys.executable, '-c', 'import time; time.sleep(20)'], root, cancel)
    timer.join()
    assert result['outcome'] == 'cancelled'


@posix
def test_command_timeout_kills_children_in_process_group(engine):
    target = engine.workspace.root / 'should-not-exist'
    child = f'import time; from pathlib import Path; time.sleep(2); Path({str(target)!r}).write_text("escaped")'
    parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(10)'
    result = run([sys.executable, '-c', parent], str(engine.workspace.root), threading.Event(), timeout=1)
    assert result['outcome'] == 'timeout'
    time.sleep(1.2)
    assert not target.exists()


def test_host_mode_disables_native_execution_and_disk_search(tmp_path):
    engine = ToolEngine(str(tmp_path), tmp_path / 'state', lambda *args: None)
    with pytest.raises(AgentError, match='host_execution_not_available'):
        engine.invoke('execute', {'argv': [sys.executable], 'cwd': '.', 'timeout': 1}, lambda p: True)
    with pytest.raises(AgentError, match='host_search_not_available'):
        engine.invoke('search', {'query': 'x'}, lambda p: True)


@posix
def test_parent_swapped_for_symlink_during_approval_refuses_write(engine, tmp_path):
    root = engine.workspace.root
    (root / 'sub').mkdir()
    (root / 'sub/file.txt').write_text('before')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'file.txt').write_text('before')
    def approve(proposal):
        (root / 'sub').rename(root / 'old-sub')
        (root / 'sub').symlink_to(outside, target_is_directory=True)
        return True
    with pytest.raises(AgentError, match='link_refused'):
        engine.invoke('edit', {'path': 'sub/file.txt', 'text': 'after', 'baseHash': digest('before')}, approve)
    assert (outside / 'file.txt').read_text() == 'before'


@posix
def test_mutated_approval_payload_is_rejected(engine):
    (engine.workspace.root / 'file.txt').write_text('before')
    def approve(proposal):
        proposal['text'] = 'different'
        return True
    with pytest.raises(AgentError, match='approval_payload_changed'):
        engine.invoke('edit', {'path': 'file.txt', 'text': 'after', 'baseHash': digest('before')}, approve)


@posix
def test_interrupted_edit_journal_reports_uncertainty_without_replaying(engine, monkeypatch):
    (engine.workspace.root / 'file.txt').write_text('before')
    def failed_write(*args):
        raise OSError('interrupted')
    monkeypatch.setattr(engine.workspace, 'write', failed_write)
    with pytest.raises(OSError):
        engine.invoke('edit', {'path': 'file.txt', 'text': 'after', 'baseHash': digest('before')}, lambda p: True)
    operation = next(engine.directory.glob('*.json')).stem
    result = engine.invoke('operation', {'operationId': operation}, lambda p: False)
    assert result['state'] == 'unknown' and result['requiresReview']
    assert 'before' not in result
    with pytest.raises(AgentError, match='not_undoable'):
        engine.invoke('undo', {'operationId': operation}, lambda p: True)


@posix
def test_replaced_workspace_root_is_refused(engine, tmp_path):
    root = engine.workspace.root
    root.rename(tmp_path / 'previous-root')
    root.mkdir()
    with pytest.raises(AgentError, match='workspace_changed'):
        engine.workspace.path('.', directory=True)
