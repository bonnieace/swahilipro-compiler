"""Bounded HTTPS client. No redirects, inherited proxies, automatic retries or logs."""
import json
import re
import time
import httpx
from .errors import AgentError


class Gateway:
    def __init__(self, api_origin, transport=None):
        self.origin = api_origin
        self.client = httpx.Client(base_url=api_origin, transport=transport,
                                   timeout=httpx.Timeout(30, connect=10),
                                   follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def _object(self, response):
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 131072:
                raise AgentError('gateway_response_too_large')
        try:
            row = json.loads(data)
            if not isinstance(row, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise AgentError('invalid_gateway_response') from None
        if response.status_code >= 300:
            code = row.get('error', 'gateway_rejected')
            if not isinstance(code, str) or not re.fullmatch('[a-z_]{1,80}', code):
                code = 'gateway_rejected'
            raise AgentError(code, 3 if response.status_code == 401 else 4, response.status_code)
        return row

    def json(self, method, path, body=None, token=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        try:
            with self.client.stream(method, path, json=body, headers=headers) as response:
                return self._object(response)
        except httpx.HTTPError:
            raise AgentError('gateway_connection_failed') from None

    def stream(self, payload, key, token):
        headers = {'Authorization': 'Bearer ' + token, 'Idempotency-Key': key}
        try:
            with self.client.stream('POST', '/api/v1/inference', json=payload, headers=headers) as response:
                if response.status_code != 200:
                    row = self._object(response)
                    if response.status_code == 202 and row.get('duplicate'):
                        raise AgentError('request_already_exists_check_status')
                    raise AgentError('unexpected_gateway_status')
                if response.headers.get('content-type', '').split(';')[0] != 'text/event-stream':
                    raise AgentError('invalid_stream_content_type')
                yield from sse(response.iter_bytes())
        except httpx.HTTPError:
            raise AgentError('stream_interrupted_check_request_status') from None


def sse(chunks):
    """Decode only complete bounded frames, so split UTF-8 stays intact."""
    pending = bytearray()
    total = 0
    deadline = time.monotonic() + 100
    for chunk in chunks:
        total += len(chunk)
        if total > 2 * 1024 * 1024 or time.monotonic() > deadline:
            raise AgentError('stream_limit_exceeded')
        pending.extend(chunk)
        while True:
            boundary = re.search(b'\r?\n\r?\n', pending)
            if not boundary:
                break
            frame = bytes(pending[:boundary.start()])
            del pending[:boundary.end()]
            if len(frame) > 131072:
                raise AgentError('stream_frame_too_large')
            try:
                lines = frame.decode('utf-8').splitlines()
                data = '\n'.join(line[5:].lstrip(' ') for line in lines if line.startswith('data:'))
                if not data:
                    continue
                row = json.loads(data)
                if not isinstance(row, dict) or row.get('version') != 1 or not isinstance(row.get('type'), str):
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise AgentError('invalid_stream_event') from None
            yield row
        if len(pending) > 131072:
            raise AgentError('stream_frame_too_large')
    if pending.strip():
        raise AgentError('incomplete_stream_frame')
