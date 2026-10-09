import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import httpx
import pytest

from swa_agent.chat import request_id
from swa_agent.gateway import Gateway
from swa_agent.protocol import Protocol, MAX_FRAME
from swa_agent.workspace import digest


class Host:
    def __init__(self, tmp_path, binary=None):
        command = [str(binary)] if binary else [sys.executable, str(Path(__file__).resolve().parents[1] / 'swa_cli.py')]
        self.process = subprocess.Popen([*command, 'agent', '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env=dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path)))
        self.events = queue.Queue()
        def reader():
            for line in self.process.stdout:
                self.events.put(json.loads(line))
        threading.Thread(target=reader, daemon=True).start()
        self.counter = 0
        self.received = []
        assert self.get(lambda row: row['type'] == 'hello')['protocol'] == 1

    def send(self, method, params=None):
        self.counter += 1
        mid = str(self.counter)
        self.process.stdin.write((json.dumps({'v': 1, 'id': mid, 'method': method, 'params': params or {}}) + '\n').encode())
        self.process.stdin.flush()
        return mid

    def get(self, match):
        while True:
            row = self.events.get(timeout=8)
            self.received.append(row)
            if match(row):
                return row

    def reply(self, event, result, binding=None):
        return self.send('reply', {'callId': event['callId'], 'binding': binding or event['binding'], 'result': result})

    def close(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.wait(timeout=8)
        stderr = self.process.stderr.read().decode()
        assert stderr == '', stderr


@pytest.fixture
def host(tmp_path):
    instance = Host(tmp_path)
    try:
        yield instance
    finally:
        if instance.process.poll() is None:
            instance.close()


def initialize(host, root, mode='host'):
    mid = host.send('initialize', {'workspace': str(root), 'mode': mode})
    return host.get(lambda row: row.get('id') == mid)['result']


def test_protocol_host_reads_and_exact_edit_approval_without_disk_mutation(host, tmp_path):
    path = tmp_path / 'file.txt'
    path.write_text('saved')
    assert initialize(host, tmp_path)['capabilities']['hostEdits']
    request = host.send('tool', {'name': 'edit', 'arguments': {'path': 'file.txt', 'text': 'updated', 'baseHash': digest('dirty')}})
    first = host.get(lambda row: row.get('kind') == 'read')
    host.reply(first, {'exists': True, 'text': 'dirty', 'version': 4})
    approval = host.get(lambda row: row.get('kind') == 'approval')
    wrong = host.reply(approval, {'approved': True}, binding='wrong')
    assert host.get(lambda row: row.get('id') == wrong)['error'] == 'stale_or_mismatched_host_reply'
    proposal = approval['proposal']
    host.reply(approval, {'approved': True, 'approvalHash': proposal['approvalHash']})
    second = host.get(lambda row: row.get('kind') == 'read')
    host.reply(second, {'exists': True, 'text': 'dirty', 'version': 4})
    apply = host.get(lambda row: row.get('kind') == 'apply')
    assert apply['payload']['version'] == 4 and apply['payload']['baseHash'] == digest('dirty')
    host.reply(apply, {'applied': True, 'hash': digest('updated')})
    done = host.get(lambda row: row.get('id') == request and row['type'] == 'result')
    assert done['result']['applied'] and path.read_text() == 'saved'
    duplicate = host.reply(approval, {'approved': True, 'approvalHash': proposal['approvalHash']})
    assert host.get(lambda row: row.get('id') == duplicate)['error'] == 'stale_or_mismatched_host_reply'


def test_cancel_pending_approval_and_reject_late_reply(host, tmp_path):
    path = tmp_path / 'file.txt'
    path.write_text('saved')
    initialize(host, tmp_path, 'disk')
    mid = host.send('tool', {'name': 'edit', 'arguments': {'path': 'file.txt', 'text': 'new', 'baseHash': digest('saved')}})
    event = host.get(lambda row: row.get('kind') == 'approval')
    host.send('cancel', {'requestId': mid})
    assert host.get(lambda row: row.get('id') == mid and row['type'] == 'error')['error'] == 'cancelled'
    late = host.reply(event, {'approved': True, 'approvalHash': event['proposal']['approvalHash']})
    assert host.get(lambda row: row.get('id') == late)['error'] == 'stale_or_mismatched_host_reply'
    assert path.read_text() == 'saved'


def test_host_eof_denies_pending_approval(host, tmp_path):
    path = tmp_path / 'file.txt'
    path.write_text('saved')
    initialize(host, tmp_path, 'disk')
    host.send('tool', {'name': 'edit', 'arguments': {'path': 'file.txt', 'text': 'new', 'baseHash': digest('saved')}})
    host.get(lambda row: row.get('kind') == 'approval')
    host.close()
    assert path.read_text() == 'saved'


def test_version_mismatch_malformed_params_and_busy_are_errors(host, tmp_path):
    host.process.stdin.write(b'{"v":2,"id":"bad","method":"initialize"}\n')
    host.process.stdin.flush()
    assert host.get(lambda row: row['type'] == 'error')['error'] == 'invalid_protocol_message'
    bad = host.send('initialize', {'workspace': {}, 'mode': 'host'})
    assert host.get(lambda row: row['type'] == 'error')['error'] == 'invalid_protocol_request'
    initialize(host, tmp_path)
    read = host.send('tool', {'name': 'read', 'arguments': {'path': 'file.txt'}})
    host.get(lambda row: row.get('kind') == 'read')
    busy = host.send('tool', {'name': 'list', 'arguments': {}})
    assert host.get(lambda row: row.get('id') == busy)['error'] == 'engine_busy'
    host.send('cancel', {'requestId': read})
    host.get(lambda row: row.get('id') == read and row['type'] == 'error')


def test_oversized_frame_stops_protocol_without_parsing():
    output = io.BytesIO()
    protocol = Protocol(io.BytesIO(b'x'*(MAX_FRAME+1)), output, 'test')
    assert protocol.serve() == 0
    assert json.loads(output.getvalue().splitlines()[-1])['error'] == 'protocol_frame_limit_or_truncated'


def test_host_prompt_streams_and_never_persists_credentials(tmp_path):
    output, calls = io.BytesIO(), []
    def handler(req):
        calls.append(req.url.path)
        assert req.headers['authorization'] == 'Bearer ' + 'a'*43
        if req.url.path.endswith('/me'):
            return httpx.Response(200, json={'uid': 'alice'})
        rid = request_id('alice', req.headers['idempotency-key'])
        events = [{'version': 1, 'type': kind, 'requestId': rid, **extra} for kind, extra in [('request.started', {}), ('text.delta', {'text': 'hello'}), ('request.completed', {'actual': 2})]]
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=''.join('data: ' + json.dumps(e) + '\n\n' for e in events))
    protocol = Protocol(io.BytesIO(), output, 'test', tmp_path / 'state', lambda api: Gateway(api, httpx.MockTransport(handler)))
    protocol.initialize({'workspace': str(tmp_path), 'mode': 'host', 'apiOrigin': 'https://test.invalid', 'uid': 'alice'})
    def credential(kind, payload, cancel):
        assert kind == 'credential' and payload['uid'] == 'alice'
        return {'accessToken': 'a'*43, 'expiresIn': 900}
    protocol.request_host = credential
    protocol.active = 'prompt'
    protocol.work({'id': 'prompt', 'method': 'prompt', 'params': {'messages': [{'role': 'user', 'content': 'hello'}], 'model': 'fake', 'maxOutputTokens': 10}})
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[-1]['result']['completed'] and len(calls) == 2
    assert 'a'*43 not in output.getvalue().decode()
    assert all('a'*43 not in path.read_text() for path in (tmp_path / 'state').rglob('*.json'))
    protocol.gateway.close()


def test_changed_host_account_cannot_start_paid_turn(tmp_path):
    output = io.BytesIO()
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={'uid': 'bob'})
    protocol = Protocol(io.BytesIO(), output, 'test', tmp_path / 'state', lambda api: Gateway(api, httpx.MockTransport(handler)))
    protocol.initialize({'workspace': str(tmp_path), 'mode': 'host', 'apiOrigin': 'https://test.invalid', 'uid': 'alice'})
    protocol.request_host = lambda *args: {'accessToken': 'a'*43, 'expiresIn': 900}
    protocol.active = 'prompt'
    protocol.work({'id': 'prompt', 'method': 'prompt', 'params': {'messages': [{'role': 'user', 'content': 'hello'}], 'model': 'fake', 'maxOutputTokens': 10}})
    assert json.loads(output.getvalue().splitlines()[-1])['error'] == 'host_account_changed'
    assert calls == ['/api/v1/me']
    protocol.gateway.close()
