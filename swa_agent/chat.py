"""Text-only chat and durable request receipts, without local code execution."""
import hashlib
import re
import secrets
from .config import private_dir, write_json, read_json
from .errors import AgentError


def request_id(uid, key):
    return hashlib.sha256(f'{uid}:inference:{key}'.encode()).hexdigest()


class Chat:
    def __init__(self, gateway, auth, directory, expected_uid=None):
        self.gateway, self.auth = gateway, auth
        self.expected_uid = expected_uid
        self.directory = private_dir(directory / 'requests')

    def send(self, messages, model, max_output, emit):
        if (not messages or len(messages) > 30 or any(not isinstance(m.get('content'), str)
                or not 1 <= len(m['content']) <= 30000 for m in messages)
                or type(max_output) is not int or not 1 <= max_output <= 8192):
            raise AgentError('message_or_output_limit_exceeded', 2)
        payload = {'model': model, 'messages': messages, 'maxOutputTokens': max_output}
        import json
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 60000:
            raise AgentError('conversation_too_large_start_a_new_chat', 2)
        token = self.auth.token()
        identity = self.gateway.json('GET', '/api/v1/me', token=token)
        uid = identity.get('uid')
        if not isinstance(uid, str) or not uid:
            raise AgentError('invalid_account_response', 3)
        if self.expected_uid is not None and uid != self.expected_uid:
            raise AgentError('host_account_changed', 3)
        key = secrets.token_urlsafe(24)
        rid = request_id(uid, key)
        path = self.directory / (rid + '.json')
        receipt = {'version': 1, 'requestId': rid, 'idempotencyKey': key, 'uid': uid,
                   'origin': self.gateway.origin, 'state': 'pending', 'responseRetained': False}
        # Persist before networking. ID is deterministically derivable even if
        # the connection drops before request.started. Recovery only uses GET.
        write_json(path, receipt)
        emit({'version': 1, 'type': 'client.request', 'requestId': rid})
        started, completed, failed = False, False, False
        text = []
        try:
            for event in self.gateway.stream(payload, key, token):
                kind = event['type']
                if kind not in ('request.started', 'text.delta', 'usage', 'request.completed', 'request.failed'):
                    if kind.startswith('tool'):
                        raise AgentError('tool_events_unsupported')
                    continue  # Compatible future informational event.
                if event.get('requestId') != rid or completed or failed:
                    raise AgentError('invalid_stream_sequence')
                if kind == 'request.started':
                    if started:
                        raise AgentError('invalid_stream_sequence')
                    started = True
                elif kind == 'request.failed':
                    failed = True
                elif not started:
                    raise AgentError('invalid_stream_sequence')
                elif kind == 'text.delta':
                    if not isinstance(event.get('text'), str):
                        raise AgentError('invalid_text_delta')
                    text.append(event['text'])
                elif kind in ('usage', 'request.completed'):
                    if type(event.get('actual')) is not int or event['actual'] < 0:
                        raise AgentError('invalid_usage_event')
                    completed = kind == 'request.completed'
                emit(event)
            if not completed or failed:
                raise AgentError('request_incomplete_check_status')
            receipt['state'] = 'completed'
            write_json(path, receipt)
            return ''.join(text)
        except BaseException:
            receipt['state'] = 'unknown'
            write_json(path, receipt)
            raise

    def status(self, rid):
        if not re.fullmatch('[a-f0-9]{64}', rid):
            raise AgentError('invalid_request_id', 2)
        path = self.directory / (rid + '.json')
        receipt = read_json(path)
        if not receipt or receipt.get('origin') != self.gateway.origin:
            raise AgentError('request_receipt_not_found', 2)
        token = self.auth.token()
        identity = self.gateway.json('GET', '/api/v1/me', token=token)
        if (identity.get('uid') != receipt.get('uid') or
                (self.expected_uid is not None and identity.get('uid') != self.expected_uid)):
            raise AgentError('request_belongs_to_another_account', 3)
        result = self.gateway.json('GET', '/api/v1/requests/' + rid, token=token)
        return result
