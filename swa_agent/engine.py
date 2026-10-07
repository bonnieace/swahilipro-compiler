"""Shared local tool engine. Only trusted frontends provide approval callbacks."""
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from filelock import FileLock, Timeout
from .config import private_dir, write_json, read_json
from .errors import AgentError
from .executor import run
from .workspace import Workspace, digest, text_valid


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


class ToolEngine:
    def __init__(self, root, state_dir, host=None):
        self.workspace = Workspace(root)
        self.host = host
        self.directory = private_dir(state_dir / 'operations' / digest(str(self.workspace.root)))

    def snapshot(self, path, cancel, missing=False):
        self.workspace.path(path)
        if self.host is None:
            return self.workspace.read(path, missing=missing)
        row = self.host('read', {'path': path, 'allowMissing': missing}, cancel)
        if not isinstance(row, dict) or type(row.get('exists')) is not bool:
            raise AgentError('invalid_host_snapshot', 5)
        if not row['exists']:
            if not missing:
                raise AgentError('file_not_found', 2)
            return {'path': path, 'text': '', 'hash': None, 'version': None}
        text = text_valid(row.get('text'))
        if type(row.get('version')) is not int or row['version'] < 0:
            raise AgentError('invalid_host_version', 5)
        return {'path': path, 'text': text, 'hash': digest(text), 'version': row['version']}

    def syntax(self, path, text, cancel):
        if not path.endswith('.swa') or os.name != 'posix':
            return None
        argv = [sys.executable, 'check', '-'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve().parents[1] / 'swa_cli.py'), 'check', '-']
        result = run(argv, str(self.workspace.root), cancel, timeout=3, limit=8192, input_bytes=text.encode())
        return {'valid': result['exitCode'] == 0 and result['outcome'] == 'completed', 'diagnostic': result['output'], 'syntaxOnly': True}

    def invoke(self, tool, args, approve, cancel=None):
        cancel = cancel or threading.Event()
        if cancel.is_set():
            raise AgentError('cancelled', 130)
        if not isinstance(args, dict):
            raise AgentError('invalid_tool_arguments', 2)
        allowed = {'list': set(), 'read': {'path'}, 'search': {'query'},
                   'edit': {'path', 'text', 'baseHash'}, 'undo': {'operationId'}, 'operation': {'operationId'},
                   'execute': {'argv', 'cwd', 'timeout'}}
        if tool not in allowed or set(args) != allowed[tool]:
            raise AgentError('invalid_tool_arguments', 2)
        if tool == 'operation':
            operation = args['operationId']
            if not isinstance(operation, str) or not re.fullmatch('[a-f0-9]{32}', operation):
                raise AgentError('invalid_operation_id', 2)
            row = read_json(self.directory / (operation + '.json'))
            if not row or row.get('root') != str(self.workspace.root):
                raise AgentError('operation_not_found', 2)
            keys = ('operationId', 'tool', 'state', 'path', 'beforeHash', 'afterHash', 'hostManaged', 'createdAt', 'exitCode')
            return {**{key: row[key] for key in keys if key in row}, 'requiresReview': row['state'] in ('pending', 'unknown')}
        if tool == 'list':
            return self.workspace.files()
        if tool == 'read':
            return self.snapshot(args['path'], cancel)
        if tool == 'search':
            if self.host:
                raise AgentError('host_search_not_available_use_explicit_reads', 5)
            return self.workspace.search(args['query'])
        try:
            with FileLock(str(self.directory / 'tools.lock'), timeout=1, mode=0o600):
                if tool == 'execute':
                    return self.execute(args, approve, cancel)
                if tool == 'undo':
                    if self.host:
                        raise AgentError('use_editor_undo', 5)
                    operation = args['operationId']
                    if not isinstance(operation, str) or not re.fullmatch('[a-f0-9]{32}', operation):
                        raise AgentError('invalid_operation_id', 2)
                    row = read_json(self.directory / (operation + '.json'))
                    if not row or row.get('root') != str(self.workspace.root) or row.get('state') != 'applied' or row.get('beforeHash') is None:
                        raise AgentError('operation_not_undoable', 5)
                    args = {'path': row['path'], 'baseHash': row['afterHash'], 'text': base64.b64decode(row['before']).decode('utf-8')}
                return self.edit(args, approve, cancel)
        except Timeout:
            raise AgentError('another_workspace_tool_is_running', 5) from None

    def approval(self, proposal, approve, cancel):
        approval_hash = fingerprint(proposal)
        payload = {**json.loads(json.dumps(proposal)), 'approvalHash': approval_hash}
        if not approve(payload):
            raise AgentError('approval_required_or_denied', 5)
        if (payload.get('approvalHash') != approval_hash or
                fingerprint({k: v for k, v in payload.items() if k != 'approvalHash'}) != approval_hash):
            raise AgentError('approval_payload_changed', 5)
        if cancel.is_set():
            raise AgentError('cancelled', 130)
        return approval_hash

    def edit(self, args, approve, cancel):
        text = text_valid(args['text'])
        snapshot = self.snapshot(args['path'], cancel, missing=True)
        if snapshot['hash'] != args['baseHash']:
            raise AgentError('stale_file', 5)
        operation = secrets.token_hex(16)
        proposal = {'operationId': operation, 'tool': 'edit', 'root': str(self.workspace.root),
                    'path': args['path'], 'baseHash': snapshot['hash'], 'version': snapshot['version'],
                    'text': text, 'afterHash': digest(text),
                    'diff': ''.join(difflib.unified_diff(snapshot['text'].splitlines(True), text.splitlines(True), fromfile=args['path'], tofile=args['path'])),
                    'syntax': self.syntax(args['path'], text, cancel)}
        approved = self.approval(proposal, approve, cancel)
        # Approval must not hide an intervening editor or disk change.
        current = self.snapshot(args['path'], cancel, missing=True)
        if current['hash'] != snapshot['hash'] or current['version'] != snapshot['version']:
            raise AgentError('stale_file', 5)
        journal = {'version': 1, 'operationId': operation, 'tool': 'edit', 'root': str(self.workspace.root),
                   'path': args['path'], 'beforeHash': snapshot['hash'], 'afterHash': digest(text),
                   'before': base64.b64encode(snapshot['text'].encode()).decode() if not self.host else None,
                   'approvalHash': approved, 'state': 'pending', 'createdAt': time.time(), 'hostManaged': bool(self.host)}
        location = self.directory / (operation + '.json')
        write_json(location, journal)
        try:
            if self.host:
                response = self.host('apply', {**proposal, 'approvalHash': approved}, cancel)
                if not isinstance(response, dict) or response.get('applied') is not True or response.get('hash') != digest(text):
                    raise AgentError('host_edit_not_confirmed', 5)
            else:
                self.workspace.write(args['path'], text, snapshot['hash'])
            journal['state'] = 'applied'
            write_json(location, journal)
            return {'operationId': operation, 'hash': digest(text), 'applied': True, 'hostManaged': bool(self.host)}
        except BaseException:
            journal['state'] = 'unknown'
            write_json(location, journal)
            raise

    def execute(self, args, approve, cancel):
        if self.host:
            raise AgentError('host_execution_not_available', 5)
        if os.name != 'posix':
            raise AgentError('native_execution_unavailable_on_this_platform', 5)
        cwd = self.workspace.path(args['cwd'], directory=True)
        if not cwd.is_dir():
            raise AgentError('invalid_command_directory', 2)
        argv, timeout = args['argv'], args['timeout']
        if (not isinstance(argv, list) or not 1 <= len(argv) <= 64 or
                any(not isinstance(a, str) or '\x00' in a or len(a) > 4096 for a in argv) or
                not Path(argv[0]).is_absolute() or type(timeout) is not int or not 1 <= timeout <= 60):
            raise AgentError('invalid_command_use_absolute_executable', 2)
        operation = secrets.token_hex(16)
        proposal = {'operationId': operation, 'tool': 'execute', 'root': str(self.workspace.root),
                    'argv': argv, 'cwd': str(cwd), 'timeout': timeout,
                    'warning': 'This command can modify files and access the network outside the workspace. It is not sandboxed.'}
        approved = self.approval(proposal, approve, cancel)
        self.workspace.path(args['cwd'], directory=True)
        location = self.directory / (operation + '.json')
        journal = {'version': 1, 'operationId': operation, 'tool': 'execute', 'root': str(self.workspace.root),
                   'approvalHash': approved, 'state': 'pending', 'createdAt': time.time()}
        write_json(location, journal)
        try:
            result = run(argv, str(cwd), cancel, timeout=timeout)
            journal.update(state=result['outcome'], exitCode=result['exitCode'])
            write_json(location, journal)
            return {**result, 'operationId': operation}
        except BaseException:
            journal['state'] = 'unknown'
            write_json(location, journal)
            raise
