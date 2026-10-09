import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest

from swa_agent.auth import Auth
from swa_agent.chat import Chat, request_id
from swa_agent.config import Settings, origin, read_json
from swa_agent.credentials import Credentials
from swa_agent.errors import AgentError
from swa_agent.gateway import Gateway, sse
from swa_agent.commands import safe_text

ORIGIN = 'https://test.invalid'
TOKENS = {'tokenType': 'Bearer', 'accessToken': 'a' * 43, 'refreshToken': 'r' * 43, 'grantId': 'g' * 43, 'expiresIn': 900}


class Keychain:
    def __init__(self):
        self.rows = {}
    def get_password(self, service, account):
        return self.rows.get((service, account))
    def set_password(self, service, account, value):
        self.rows[service, account] = value


def account(tmp_path, handler):
    settings = Settings(tmp_path)
    credentials = Credentials(ORIGIN, settings.account_dir(ORIGIN), Keychain())
    gateway = Gateway(ORIGIN, httpx.MockTransport(handler))
    return Auth(gateway, credentials)


def ready(auth, expires=None):
    auth.credentials.write({'version': 1, **TOKENS, 'expiresAt': expires or time.time() + 900})


@pytest.mark.parametrize('value', ['http://test.invalid', 'https://x@host', 'https://host/path', 'https://host?q=x', 'https://host/#fragment', '//host', 'https://host\n'])
def test_origin_rejects_unsafe_urls(value):
    with pytest.raises(AgentError):
        origin(value)


def test_settings_are_user_scoped_and_credentials_origin_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv('SWA_API_ORIGIN', 'https://evil.invalid')
    settings = Settings(tmp_path)
    assert settings.configure('https://TEST.invalid:443/') == ORIGIN
    assert settings.load_origin() == ORIGIN
    backend = Keychain()
    one = Credentials(ORIGIN, settings.account_dir(ORIGIN), backend)
    two = Credentials('https://other.invalid', settings.account_dir('https://other.invalid'), backend)
    one.write({'version': 1, 'secret': 'private'})
    assert two.read() is None
    assert 'private' not in (tmp_path / 'config.json').read_text()


def test_login_challenge_polling_and_completion_spacing(tmp_path):
    calls, shown, now, started = [], [], [0], {}
    def handler(req):
        row = json.loads(req.content)
        calls.append((req.url.path, now[0], row))
        if req.url.path.endswith('/start'):
            started.update(row)
            return httpx.Response(200, json={'attemptId': 'i'*43, 'pollingSecret': 'p'*43, 'confirmationCode': '1234ABCD', 'interval': 5, 'expiresIn': 600, 'verificationUrl': ORIGIN + '/authorize-client?attempt=' + 'i'*43})
        if req.url.path.endswith('/status'):
            return httpx.Response(200, json={'state': 'approved'})
        assert base64.urlsafe_b64encode(hashlib.sha256(row['verifier'].encode()).digest()).rstrip(b'=').decode() == started['challenge']
        return httpx.Response(200, json=TOKENS)
    auth = account(tmp_path, handler)
    auth.login(lambda *args: shown.append(args), True, lambda delay: now.__setitem__(0, now[0] + delay), lambda: now[0])
    assert [t for _, t, _ in calls] == [0, 5, 10]
    assert auth.token() == TOKENS['accessToken']
    assert 'p'*43 not in str(shown) and TOKENS['accessToken'] not in str(shown)


def test_login_rejects_foreign_verification_url_before_browser(tmp_path):
    auth = account(tmp_path, lambda req: httpx.Response(200, json={'attemptId': 'i'*43, 'pollingSecret': 'p'*43, 'confirmationCode': '1234ABCD', 'interval': 5, 'expiresIn': 600, 'verificationUrl': 'https://evil.invalid'}))
    with pytest.raises(AgentError, match='invalid_login_attempt'):
        auth.login(lambda *args: pytest.fail('URL exposed'), True)


def test_denied_login_does_not_store_tokens(tmp_path):
    def handler(req):
        if req.url.path.endswith('/start'):
            return httpx.Response(200, json={'attemptId': 'i'*43, 'pollingSecret': 'p'*43, 'confirmationCode': '1234ABCD', 'interval': 5, 'expiresIn': 600, 'verificationUrl': ORIGIN + '/authorize-client?attempt=' + 'i'*43})
        return httpx.Response(403, json={'error': 'authorization_denied'})
    auth = account(tmp_path, handler)
    with pytest.raises(AgentError, match='authorization_denied'):
        auth.login(lambda *args: None, True, lambda delay: None)
    assert auth.credentials.read() is None


def test_uncertain_refresh_is_never_replayed_even_after_restart(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('secret response lost')
    auth = account(tmp_path, handler)
    ready(auth, 1)
    with pytest.raises(AgentError, match='connection_failed'):
        auth.token()
    restarted = Auth(auth.gateway, auth.credentials)
    with pytest.raises(AgentError, match='refresh_outcome_unknown'):
        restarted.token()
    assert len(calls) == 1
    assert auth.credentials.read()['refreshAttempted'] is True


def test_successful_rotation_saved_once_and_shared_with_other_instance(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={**TOKENS, 'accessToken': 'b'*43, 'refreshToken': 's'*43})
    auth = account(tmp_path, handler)
    ready(auth, 1)
    assert auth.token() == 'b'*43
    assert Auth(auth.gateway, auth.credentials).token() == 'b'*43
    assert len(calls) == 1


def test_lock_serializes_other_processes(tmp_path):
    auth = account(tmp_path, lambda req: None)
    script = "from filelock import FileLock,Timeout; import sys\ntry:\n with FileLock(sys.argv[1],timeout=.1): pass\nexcept Timeout: sys.exit(7)"
    with auth.credentials.locked():
        result = subprocess.run([sys.executable, '-c', script, str(auth.credentials.directory / 'credentials.lock')])
    assert result.returncode == 7


def test_offline_logout_erases_local_credentials(tmp_path):
    def handler(req):
        raise httpx.ConnectError('offline')
    auth = account(tmp_path, handler)
    ready(auth)
    assert auth.logout() is False
    assert auth.credentials.read() == {'version': 1, 'loggedOut': True}


def test_unavailable_keychain_fails_closed(tmp_path):
    class Broken(Keychain):
        def set_password(self, *args):
            raise RuntimeError('secret details')
    credentials = Credentials(ORIGIN, tmp_path, Broken())
    with pytest.raises(AgentError, match='os_keychain_write_failed'):
        credentials.write(TOKENS)
    assert list(tmp_path.iterdir()) == []


def test_no_redirect_or_unbounded_error_message(tmp_path):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(302, headers={'Location': 'https://evil.invalid'}, json={'error': 'secret-token-123'})
    gateway = Gateway(ORIGIN, httpx.MockTransport(handler))
    with pytest.raises(AgentError, match='gateway_rejected'):
        gateway.json('GET', '/api/v1/me', token='token')
    assert len(calls) == 1


def test_sse_fragmented_utf8_crlf_limits_and_invalid_version():
    frame = ('data: ' + json.dumps({'version': 1, 'type': 'text.delta', 'text': 'Jambo 👋'}, ensure_ascii=False) + '\r\n\r\n').encode()
    assert list(sse(bytes([b]) for b in frame))[0]['text'] == 'Jambo 👋'
    for raw in (b'data: {"version":2,"type":"text.delta"}\n\n', b'x'*131073, b'data: {'):
        with pytest.raises(AgentError):
            list(sse([raw]))


def test_terminal_control_sequences_removed():
    assert '\x1b' not in safe_text('\x1b]52;c;payload\x07hello')


@pytest.mark.parametrize('disconnect', [False, True])
def test_chat_receipt_saved_before_post_and_status_never_reinvokes(tmp_path, disconnect):
    posts = []
    def handler(req):
        if req.url.path == '/api/v1/me':
            return httpx.Response(200, json={'uid': 'alice'})
        if req.url.path.startswith('/api/v1/requests/'):
            return httpx.Response(200, json={'request': {'id': req.url.path.split('/')[-1], 'state': 'settled'}})
        posts.append(req)
        key = req.headers['idempotency-key']
        rid = request_id('alice', key)
        receipt = read_json(auth.credentials.directory / 'requests' / (rid + '.json'))
        assert receipt['state'] == 'pending'
        assert 'secret prompt' not in json.dumps(receipt)
        if disconnect:
            raise httpx.ReadTimeout('lost before started')
        events = [{'version': 1, 'type': kind, 'requestId': rid, **extra} for kind, extra in [
            ('request.started', {}), ('text.delta', {'text': 'answer'}), ('request.completed', {'actual': 4})]]
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=''.join('data: ' + json.dumps(e) + '\n\n' for e in events))
    auth = account(tmp_path, handler)
    ready(auth)
    chat = Chat(auth.gateway, auth, auth.credentials.directory)
    events = []
    if disconnect:
        with pytest.raises(AgentError):
            chat.send([{'role': 'user', 'content': 'secret prompt'}], 'fake', 10, events.append)
    else:
        assert chat.send([{'role': 'user', 'content': 'secret prompt'}], 'fake', 10, events.append) == 'answer'
    rid = events[0]['requestId']
    assert chat.status(rid)['request']['state'] == 'settled'
    assert len(posts) == 1


def test_offline_runtime_does_not_import_agent_dependencies():
    result = subprocess.run([sys.executable, '-c', "import swa_cli,sys; swa_cli.main(['check','-']); assert 'httpx' not in sys.modules; assert 'keyring' not in sys.modules"], input='andika("hi")', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_run_disambiguates_source_named_chat(tmp_path, capsys):
    import swa_cli
    path = tmp_path / 'chat'
    path.write_text('andika("offline")')
    assert swa_cli.main(['run', str(path)]) == 0
    assert 'offline' in capsys.readouterr().out


def test_expired_login_and_throttling_are_bounded(tmp_path):
    now, calls = [0], []
    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith('/start'):
            return httpx.Response(200, json={'attemptId': 'i'*43, 'pollingSecret': 'p'*43, 'confirmationCode': '1234ABCD', 'interval': 5, 'expiresIn': 16, 'verificationUrl': ORIGIN + '/authorize-client?attempt=' + 'i'*43})
        return httpx.Response(429, json={'error': 'slow_down'})
    auth = account(tmp_path, handler)
    with pytest.raises(AgentError, match='login_attempt_expired'):
        auth.login(lambda *args: None, True, lambda n: now.__setitem__(0, now[0] + n), lambda: now[0])
    assert len(calls) == 4


def test_login_cancellation_leaves_no_credentials(tmp_path):
    def handler(req):
        return httpx.Response(200, json={'attemptId': 'i'*43, 'pollingSecret': 'p'*43, 'confirmationCode': '1234ABCD', 'interval': 5, 'expiresIn': 600, 'verificationUrl': ORIGIN + '/authorize-client?attempt=' + 'i'*43})
    auth = account(tmp_path, handler)
    def cancel(delay):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        auth.login(lambda *args: None, True, cancel)
    assert auth.credentials.read() is None


@pytest.mark.parametrize('ending', ['disconnect', 'duplicate', 'tool', 'wrong_id'])
def test_ambiguous_or_unsupported_stream_never_retries(tmp_path, ending):
    posts, events = [], []
    def handler(req):
        if req.url.path.endswith('/me'):
            return httpx.Response(200, json={'uid': 'alice'})
        posts.append(req)
        rid = request_id('alice', req.headers['idempotency-key'])
        if ending == 'duplicate':
            return httpx.Response(202, json={'duplicate': True, 'request': {'id': rid}})
        rows = [{'version': 1, 'type': 'request.started', 'requestId': rid}]
        if ending == 'tool':
            rows.append({'version': 1, 'type': 'tool_call.delta', 'requestId': rid})
        if ending == 'wrong_id':
            rows.append({'version': 1, 'type': 'text.delta', 'requestId': 'wrong', 'text': 'x'})
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=''.join('data: ' + json.dumps(r) + '\n\n' for r in rows))
    auth = account(tmp_path, handler)
    ready(auth)
    chat = Chat(auth.gateway, auth, auth.credentials.directory)
    with pytest.raises(AgentError):
        chat.send([{'role': 'user', 'content': 'hello'}], 'fake', 10, events.append)
    rid = events[0]['requestId']
    assert read_json(chat.directory / (rid + '.json'))['state'] == 'unknown'
    assert len(posts) == 1


def test_recovery_refuses_different_account(tmp_path):
    from swa_agent.config import write_json
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={'uid': 'bob'})
    auth = account(tmp_path, handler)
    ready(auth)
    chat = Chat(auth.gateway, auth, auth.credentials.directory)
    rid = 'f'*64
    write_json(chat.directory / (rid + '.json'), {'uid': 'alice', 'origin': ORIGIN})
    with pytest.raises(AgentError, match='another_account'):
        chat.status(rid)
    assert calls == ['/api/v1/me']


def test_published_v1_event_fixture_decodes():
    fixture = json.loads((Path(__file__).parent / 'fixtures/gateway-v1.json').read_text())
    raw = ''.join('data: ' + json.dumps(row) + '\n\n' for row in fixture['events']).encode()
    assert list(sse([raw])) == fixture['events']
