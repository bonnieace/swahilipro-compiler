"""Terminal adapter. JSON output is structured; no credentials or banners."""
import argparse
import json
import sys
import unicodedata
from .errors import AgentError

COMMANDS = {'configure', 'login', 'logout', 'whoami', 'credits', 'models', 'chat', 'request'}


def safe_text(value):
    # Provider output is untrusted: do not execute ANSI/OSC terminal sequences.
    return ''.join(c for c in str(value) if c in '\n\t' or not unicodedata.category(c).startswith('C'))


def parser(command, prog):
    result = argparse.ArgumentParser(prog=f'{prog} {command}')
    result.add_argument('--json', action='store_true', help='Emit JSON records only')
    if command == 'configure':
        result.add_argument('--api-origin', required=True)
    if command == 'login':
        result.add_argument('--no-browser', action='store_true')
    if command == 'chat':
        result.add_argument('--model', required=True)
        result.add_argument('--prompt', help='One text prompt; otherwise interactive')
        result.add_argument('--max-output-tokens', type=int, default=1024)
    if command == 'request':
        result.add_argument('id')
    return result


def main(arguments, prog='swa'):
    command = arguments[0]
    args = parser(command, prog).parse_args(arguments[1:])
    gateway = None

    def output(row):
        print(json.dumps(row, ensure_ascii=True) if args.json else safe_text(json.dumps(row, ensure_ascii=False)))

    try:
        from .config import Settings
        settings = Settings()
        if command == 'configure':
            output({'origin': settings.configure(args.api_origin)})
            return 0
        from .gateway import Gateway
        from .credentials import Credentials
        from .auth import Auth
        api_origin = settings.load_origin()
        directory = settings.account_dir(api_origin)
        gateway = Gateway(api_origin)
        auth = Auth(gateway, Credentials(api_origin, directory))
        if command == 'login':
            def show(url, code):
                output({'verificationUrl': url, 'confirmationCode': code})
            auth.login(show, args.no_browser)
            output({'loggedIn': True})
        elif command == 'logout':
            confirmed = auth.logout()
            output({'loggedOut': True, 'remoteRevocationConfirmed': confirmed,
                    **({} if confirmed else {'message': 'Revoke this device from your website account when connected.'})})
        elif command in ('whoami', 'credits', 'models'):
            path = 'me' if command == 'whoami' else command
            output(gateway.json('GET', '/api/v1/' + path, token=auth.token()))
        else:
            from .chat import Chat
            chat = Chat(gateway, auth, directory)
            if command == 'request':
                output(chat.status(args.id))
                return 0
            if args.json and args.prompt is None:
                raise AgentError('json_chat_requires_prompt', 2)
            messages = []
            def emit(event):
                if args.json:
                    output(event)
                elif event['type'] == 'text.delta':
                    print(safe_text(event['text']), end='', flush=True)
                elif event['type'] == 'client.request':
                    print('Request: ' + event['requestId'], file=sys.stderr)
                elif event['type'] == 'request.completed':
                    print('\nCharged microcredits: ' + safe_text(event.get('actual')), file=sys.stderr)
                elif event['type'] == 'request.failed':
                    print('Request failed; check its status before sending again.', file=sys.stderr)
            while True:
                prompt = args.prompt if args.prompt is not None else input('You (/exit to quit)> ')
                if args.prompt is None and prompt.strip() == '/exit':
                    break
                messages.append({'role': 'user', 'content': prompt})
                answer = chat.send(messages, args.model, args.max_output_tokens, emit)
                messages.append({'role': 'assistant', 'content': answer})
                if args.prompt is not None:
                    break
                print()
        return 0
    except (KeyboardInterrupt, EOFError):
        output({'error': 'cancelled', 'message': 'Any started request may still incur credits; use swa request ID.'})
        return 130
    except AgentError as error:
        output({'error': error.code})
        return error.exit_code
    except Exception:
        # Library exceptions can contain token-bearing request headers/URLs.
        output({'error': 'client_error_no_secrets_logged'})
        return 4
    finally:
        if gateway:
            gateway.close()
