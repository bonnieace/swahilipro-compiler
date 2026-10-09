"""Protocol v1: one active operation, explicit host replies, no sockets or secrets on stdout."""
import json
import re
import secrets
import sys
import threading
import time
from .config import Settings, origin
from .engine import ToolEngine, fingerprint
from .errors import AgentError

MAX_FRAME = 262144
ID = re.compile(r'^[A-Za-z0-9_-]{1,80}$')


class Protocol:
    def __init__(self, source, sink, version, state_dir=None, gateway_factory=None):
        self.source, self.sink, self.version = source, sink, version
        self.state_dir = state_dir
        self.gateway_factory = gateway_factory
        self.output_lock = threading.Lock()
        self.condition = threading.Condition()
        self.pending = {}
        self.seen = set()
        self.worker = None
        self.busy = False
        self.active = None
        self.cancelled = threading.Event()
        self.engine = None
        self.origin = None
        self.uid = None
        self.gateway = None

    def send(self, value):
        raw = json.dumps({'v': 1, **value}, ensure_ascii=True, separators=(',', ':')).encode() + b'\n'
        if len(raw) > MAX_FRAME:
            raise AgentError('protocol_output_limit', 4)
        with self.output_lock:
            self.sink.write(raw)
            self.sink.flush()

    def report(self, value):
        try:
            self.send(value)
        except (BrokenPipeError, OSError):
            self.cancelled.set()

    def finish(self, value):
        self.busy = False
        self.report(value)

    def request_host(self, kind, payload, cancel):
        call_id = secrets.token_hex(16)
        body = {'kind': kind, 'operationRequestId': self.active, **payload}
        binding = fingerprint(body)
        with self.condition:
            self.pending[call_id] = {'binding': binding, 'done': False}
        try:
            self.send({'id': self.active, 'type': 'event', 'event': 'host.request',
                       'callId': call_id, 'binding': binding, **body})
            deadline = time.monotonic() + (120 if kind == 'approval' else 30)
            with self.condition:
                while not self.pending[call_id]['done']:
                    if cancel.is_set():
                        raise AgentError('cancelled', 130)
                    if time.monotonic() >= deadline:
                        raise AgentError('host_reply_timeout', 5)
                    self.condition.wait(.1)
                return self.pending[call_id]['result']
        finally:
            with self.condition:
                self.pending.pop(call_id, None)

    def approve(self, proposal):
        reply = self.request_host('approval', {'proposal': proposal}, self.cancelled)
        return isinstance(reply, dict) and reply == {'approved': True, 'approvalHash': proposal['approvalHash']}

    def host_tool(self, kind, payload, cancel):
        return self.request_host(kind, {'payload': payload}, cancel)

    def token(self):
        reply = self.request_host('credential', {'origin': self.origin, 'uid': self.uid}, self.cancelled)
        if (not isinstance(reply, dict) or set(reply) != {'accessToken', 'expiresIn'}
                or not isinstance(reply['accessToken'], str) or not re.fullmatch('[A-Za-z0-9_-]{43}', reply['accessToken'])
                or type(reply['expiresIn']) is not int or not 120 <= reply['expiresIn'] <= 900):
            raise AgentError('invalid_host_credential', 3)
        return reply['accessToken']

    def initialize(self, params):
        if self.engine or set(params) - {'workspace', 'mode', 'apiOrigin', 'uid'} or not {'workspace', 'mode'} <= set(params):
            raise AgentError('invalid_initialize', 2)
        if params['mode'] not in ('host', 'disk'):
            raise AgentError('invalid_tool_mode', 2)
        if ('apiOrigin' in params) != ('uid' in params):
            raise AgentError('origin_and_uid_required_together', 2)
        api_origin = origin(params['apiOrigin']) if 'apiOrigin' in params else None
        uid = params.get('uid')
        if uid is not None and (not isinstance(uid, str) or not 1 <= len(uid) <= 128):
            raise AgentError('invalid_account', 2)
        state = self.state_dir or Settings().root
        self.engine = ToolEngine(params['workspace'], state, self.host_tool if params['mode'] == 'host' else None)
        self.state_dir, self.origin, self.uid = state, api_origin, uid
        import os
        return {'initialized': True, 'workspace': str(self.engine.workspace.root), 'mode': params['mode'],
                'capabilities': {'read': True, 'list': True, 'hostEdits': params['mode'] == 'host',
                                 'diskEdits': params['mode'] == 'disk' and os.name == 'posix',
                                 'execute': params['mode'] == 'disk' and os.name == 'posix',
                                 'search': params['mode'] == 'disk', 'prompt': bool(api_origin),
                                 'autonomousToolLoop': False, 'resume': False}}

    def work(self, message):
        request_id = message['id']
        try:
            params = message.get('params', {})
            if message['method'] == 'tool':
                if set(params) != {'name', 'arguments'}:
                    raise AgentError('invalid_tool_request', 2)
                result = self.engine.invoke(params['name'], params['arguments'], self.approve, self.cancelled)
            else:
                if not self.origin:
                    raise AgentError('account_not_initialized', 3)
                if message['method'] == 'request.status':
                    if set(params) != {'requestId'}:
                        raise AgentError('invalid_status_request', 2)
                elif set(params) != {'messages', 'model', 'maxOutputTokens'}:
                    raise AgentError('invalid_prompt_request', 2)
                from .chat import Chat
                from .gateway import Gateway
                if self.gateway is None:
                    self.gateway = (self.gateway_factory or Gateway)(self.origin)
                directory = Settings(self.state_dir).account_dir(self.origin)
                chat = Chat(self.gateway, self, directory, expected_uid=self.uid)
                def emit(event):
                    if self.cancelled.is_set():
                        raise AgentError('cancelled', 130)
                    self.send({'id': request_id, 'type': 'event', 'event': 'gateway', 'data': event})
                if message['method'] == 'request.status':
                    result = chat.status(params['requestId'])
                else:
                    chat.send(params['messages'], params['model'], params['maxOutputTokens'], emit)
                    result = {'completed': True, 'responseRetained': False}
            if self.cancelled.is_set():
                raise AgentError('cancelled', 130)
            self.finish({'id': request_id, 'type': 'result', 'result': result})
        except AgentError as error:
            self.finish({'id': request_id, 'type': 'error', 'error': error.code, 'exitCode': error.exit_code})
        except Exception:
            self.finish({'id': request_id, 'type': 'error', 'error': 'engine_failed_no_details_logged'})

    def accept(self, message):
        if (not isinstance(message, dict) or set(message) - {'v', 'id', 'method', 'params'}
                or type(message.get('v')) is not int or message['v'] != 1
                or not isinstance(message.get('id'), str) or not ID.fullmatch(message['id'])
                or not isinstance(message.get('params', {}), dict)):
            raise AgentError('invalid_protocol_message', 2)
        mid, method, params = message['id'], message.get('method'), message.get('params', {})
        if mid in self.seen or len(self.seen) >= 10000:
            raise AgentError('duplicate_or_exhausted_request_id', 2)
        self.seen.add(mid)
        if method == 'reply':
            if set(params) != {'callId', 'binding', 'result'} or not isinstance(params['callId'], str):
                raise AgentError('invalid_host_reply', 2)
            with self.condition:
                pending = self.pending.get(params['callId'])
                if not pending or pending['done'] or params['binding'] != pending['binding']:
                    raise AgentError('stale_or_mismatched_host_reply', 5)
                pending.update(done=True, result=params['result'])
                self.condition.notify_all()
            # Never echo reply payloads: credential replies contain access tokens.
            self.send({'id': mid, 'type': 'result', 'result': {'accepted': True}})
        elif method == 'cancel':
            if set(params) != {'requestId'} or params['requestId'] != self.active or not self.busy:
                raise AgentError('invalid_cancel_target', 2)
            self.cancelled.set()
            self.send({'id': mid, 'type': 'result', 'result': {'cancellationRequested': True}})
        elif method == 'shutdown':
            self.cancelled.set()
            return False
        elif method == 'initialize':
            self.send({'id': mid, 'type': 'result', 'result': self.initialize(params)})
        elif method in ('tool', 'prompt', 'request.status'):
            if not self.engine:
                raise AgentError('initialize_required', 2)
            if self.busy:
                raise AgentError('engine_busy', 5)
            self.busy = True
            self.active = mid
            self.cancelled = threading.Event()
            self.worker = threading.Thread(target=self.work, args=(message,), daemon=True)
            self.worker.start()
        else:
            raise AgentError('unsupported_method', 2)
        return True

    def serve(self):
        self.send({'type': 'hello', 'protocol': 1, 'runtimeVersion': self.version,
                   'capabilities': ['initialize', 'tool', 'prompt', 'request.status', 'reply', 'cancel', 'shutdown']})
        try:
            while True:
                raw = self.source.readline(MAX_FRAME + 1)
                if not raw:
                    break
                if len(raw) > MAX_FRAME or not raw.endswith(b'\n'):
                    self.send({'type': 'error', 'error': 'protocol_frame_limit_or_truncated'})
                    break
                message = None
                try:
                    message = json.loads(raw)
                    if not self.accept(message):
                        break
                except (ValueError, UnicodeError):
                    self.send({'type': 'error', 'error': 'invalid_json'})
                except AgentError as error:
                    mid = message.get('id') if isinstance(message, dict) else None
                    # An invalid id might itself contain a secret. Never echo it.
                    if not isinstance(mid, str) or not ID.fullmatch(mid):
                        mid = None
                    self.send({'id': mid, 'type': 'error', 'error': error.code})
                except Exception:
                    self.send({'type': 'error', 'error': 'invalid_protocol_request'})
        finally:
            self.cancelled.set()
            with self.condition:
                self.condition.notify_all()
            if self.worker:
                self.worker.join(timeout=35)
            if self.gateway:
                self.gateway.close()
        return 0


def main(argv, version):
    if argv != ['--stdio']:
        print('Usage: swa agent --stdio', file=sys.stderr)
        return 2
    try:
        return Protocol(sys.stdin.buffer, sys.stdout.buffer, version).serve()
    except (BrokenPipeError, KeyboardInterrupt):
        return 130
