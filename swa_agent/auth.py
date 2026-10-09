import base64
import hashlib
import re
import secrets
import time
import webbrowser
from .errors import AgentError

TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')


def pair(value):
    if (not isinstance(value, dict) or value.get('tokenType') != 'Bearer'
            or any(not isinstance(value.get(k), str) or not TOKEN.fullmatch(value[k])
                   for k in ('accessToken', 'refreshToken', 'grantId'))
            or type(value.get('expiresIn')) is not int or not 1 <= value['expiresIn'] <= 900):
        raise AgentError('invalid_token_response', 3)
    return {'version': 1, 'accessToken': value['accessToken'],
            'refreshToken': value['refreshToken'], 'grantId': value['grantId'],
            'expiresAt': time.time() + value['expiresIn']}


class Auth:
    def __init__(self, gateway, credentials):
        self.gateway, self.credentials = gateway, credentials

    def login(self, show, no_browser=False, sleep=time.sleep, clock=time.monotonic):
        with self.credentials.locked():
            old = self.credentials.read()
            if old and not old.get('loggedOut'):
                raise AgentError('logout_before_starting_another_login', 3)
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            attempt = self.gateway.json('POST', '/api/v1/auth/client/start',
                                        {'clientType': 'cli', 'label': 'SwahiliPro CLI', 'challenge': challenge})
            for key in ('attemptId', 'pollingSecret'):
                if not isinstance(attempt.get(key), str) or not TOKEN.fullmatch(attempt[key]):
                    raise AgentError('invalid_login_attempt', 3)
            expected_url = self.gateway.origin + '/authorize-client?attempt=' + attempt['attemptId']
            if (attempt.get('verificationUrl') != expected_url
                    or not re.fullmatch('[A-F0-9]{8}', str(attempt.get('confirmationCode', '')))
                    or type(attempt.get('interval')) is not int or not 5 <= attempt['interval'] <= 30
                    or type(attempt.get('expiresIn')) is not int or not 1 <= attempt['expiresIn'] <= 600):
                raise AgentError('invalid_login_attempt', 3)
            show(expected_url, attempt['confirmationCode'])
            if not no_browser:
                try:
                    webbrowser.open(expected_url)
                except webbrowser.Error:
                    pass  # Printed URL remains usable on headless terminals.
            deadline = clock() + attempt['expiresIn']
            body = {k: attempt[k] for k in ('attemptId', 'pollingSecret')}
            approved = False
            while clock() < deadline:
                sleep(attempt['interval'])
                if clock() >= deadline:
                    break
                try:
                    if approved:
                        result = self.gateway.json('POST', '/api/v1/auth/client/complete', {**body, 'verifier': verifier})
                        self.credentials.write(pair(result))
                        return
                    result = self.gateway.json('POST', '/api/v1/auth/client/status', body)
                except AgentError as error:
                    if error.status == 429:
                        continue  # Read-only poll / rejected completion; no token consumed.
                    raise
                state = result.get('state')
                if state not in ('pending', 'approved'):
                    raise AgentError('authorization_denied_or_expired', 3)
                approved = state == 'approved'
            raise AgentError('login_attempt_expired', 3)

    def token(self):
        with self.credentials.locked():
            row = self.credentials.read()
            if not row or row.get('loggedOut'):
                raise AgentError('login_required', 3)
            if row.get('refreshAttempted'):
                raise AgentError('refresh_outcome_unknown_logout_and_login_again', 3)
            if not isinstance(row.get('expiresAt'), (int, float)):
                raise AgentError('invalid_stored_credentials', 3)
            if row['expiresAt'] > time.time() + 30:
                return row['accessToken']
            # Write before sending. If interrupted at any point, the old refresh
            # credential must never be replayed (server revokes on reuse).
            self.credentials.write({**row, 'refreshAttempted': True})
            result = self.gateway.json('POST', '/api/v1/auth/client/refresh', {'refreshToken': row['refreshToken']})
            refreshed = pair(result)
            if refreshed['grantId'] != row['grantId']:
                raise AgentError('invalid_refresh_grant', 3)
            self.credentials.write(refreshed)
            return refreshed['accessToken']

    def logout(self):
        with self.credentials.locked():
            row = self.credentials.read()
            confirmed = not row or row.get('loggedOut', False)
            try:
                if row and row.get('accessToken'):
                    self.gateway.json('POST', '/api/v1/auth/client/logout', token=row['accessToken'])
                    confirmed = True
            except AgentError:
                pass
            finally:
                self.credentials.clear()
            return confirmed
