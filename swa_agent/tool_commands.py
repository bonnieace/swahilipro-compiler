"""Explicit CLI tools share the engine with the future editor host."""
import argparse
import json
from pathlib import Path
import sys
from .commands import safe_text
from .config import Settings
from .engine import ToolEngine
from .errors import AgentError
from .workspace import MAX_FILE


def main(argv, prog='swa'):
    parser = argparse.ArgumentParser(prog=prog + ' tool')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--json', action='store_true')
    sub = parser.add_subparsers(dest='tool', required=True)
    sub.add_parser('list')
    sub.add_parser('read').add_argument('path')
    sub.add_parser('search').add_argument('query')
    edit = sub.add_parser('edit')
    edit.add_argument('path')
    edit.add_argument('--text-file', required=True)
    edit.add_argument('--base-hash', required=True, help='Hash returned by read, or absent for a new file')
    sub.add_parser('undo').add_argument('operationId')
    sub.add_parser('operation').add_argument('operationId')
    execute = sub.add_parser('execute')
    execute.add_argument('--cwd', default='.')
    execute.add_argument('--timeout', type=int, default=30)
    execute.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    def output(value):
        print(json.dumps(value, ensure_ascii=True) if args.json else safe_text(json.dumps(value, ensure_ascii=False)))
    def approve(proposal):
        if args.json:
            output({'type': 'approval.required', **proposal})
        else:
            print('Workspace: ' + safe_text(proposal['root']))
            print('Operation: ' + proposal['tool'])
            if proposal['tool'] == 'edit':
                print('File: ' + safe_text(proposal['path']))
                print(safe_text(proposal['diff']))
                if proposal['syntax']:
                    output({'syntax': proposal['syntax']})
            else:
                output({k: proposal[k] for k in ('argv', 'cwd', 'timeout', 'warning')})
            print('Approval hash: ' + proposal['approvalHash'])
        if args.json or not sys.stdin.isatty():
            return False
        return input('Approve this exact operation? Type yes: ').strip() == 'yes'
    try:
        params = {}
        if args.tool == 'read':
            params = {'path': args.path}
        elif args.tool == 'search':
            params = {'query': args.query}
        elif args.tool == 'edit':
            if not Path(args.text_file).is_file():
                raise AgentError('proposal_must_be_a_regular_file', 2)
            with Path(args.text_file).open('rb') as source:
                raw = source.read(MAX_FILE + 1)
            params = {'path': args.path, 'text': raw.decode('utf-8'), 'baseHash': None if args.base_hash == 'absent' else args.base_hash}
        elif args.tool in ('undo', 'operation'):
            params = {'operationId': args.operationId}
        elif args.tool == 'execute':
            params = {'argv': args.argv[1:] if args.argv[:1] == ['--'] else args.argv, 'cwd': args.cwd, 'timeout': args.timeout}
        result = ToolEngine(args.workspace, Settings().root).invoke(args.tool, params, approve)
        output(result)
        return 0
    except (KeyboardInterrupt, EOFError):
        output({'error': 'cancelled'})
        return 130
    except AgentError as error:
        output({'error': error.code})
        return error.exit_code
    except Exception:
        output({'error': 'tool_failed_no_details_logged'})
        return 4
