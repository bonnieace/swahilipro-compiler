"""Conservative, bounded workspace access. File access is not a process sandbox."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import secrets
from pathspec import GitIgnoreSpec
from .errors import AgentError

MAX_FILE = 32768
MAX_ENTRIES = 2000


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def text_valid(text):
    if not isinstance(text, str) or '\x00' in text or len(text.encode('utf-8')) > MAX_FILE:
        raise AgentError('text_file_limit_or_binary', 2)
    return text


def denied(name):
    name = name.lower()
    return (name in {'.git', '.ssh', '.aws', '.azure', '.gnupg', '.venv', 'node_modules', '__pycache__', '.npmrc', '.pypirc', '.netrc'}
            or name.startswith(('.env', 'id_rsa', 'id_ed25519', 'credentials', 'secrets'))
            or name.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore')))


class Workspace:
    def __init__(self, root):
        path = Path(root).expanduser()
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise AgentError('workspace_requires_absolute_directory', 2)
        self.root = path.resolve()
        info = self.root.stat()
        self.identity = (info.st_dev, info.st_ino)

    def path(self, name, directory=False):
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self.identity:
            raise AgentError('workspace_changed', 5)
        if not isinstance(name, str) or len(name) > 1024 or '\\' in name or ':' in name or any(ord(c) < 32 for c in name):
            raise AgentError('invalid_workspace_path', 2)
        parts = PurePosixPath(name).parts
        if name == '.' and directory:
            return self.root
        if not parts or name.startswith('/') or any(p in ('..', '.') or denied(p) for p in parts):
            raise AgentError('excluded_workspace_path', 5)
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
                raise AgentError('workspace_link_refused', 5)
            if current.exists():
                info = current.stat()
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1):
                    raise AgentError('workspace_special_file_refused', 5)
            if self.ignored(current):
                raise AgentError('ignored_workspace_path', 5)
        if not current.resolve().is_relative_to(self.root):
            raise AgentError('outside_workspace', 5)
        return current

    def ignored(self, path):
        # Conservative across nested ignore files: a nested rule cannot reopen an
        # excluded ancestor. Negation within each file follows gitwildmatch.
        parent = path.parent
        while parent.is_relative_to(self.root):
            for filename in ('.gitignore', '.swaignore'):
                rules = parent / filename
                if rules.is_symlink():
                    raise AgentError('ignore_file_link_refused', 5)
                if rules.exists():
                    data = self._read(rules).decode('utf-8')
                    relative = path.relative_to(parent).as_posix() + ('/' if path.is_dir() else '')
                    if GitIgnoreSpec.from_lines(data.splitlines()).match_file(relative):
                        return True
            if parent == self.root:
                break
            parent = parent.parent
        return False

    @contextmanager
    def parent_fd(self, path):
        # Walk directory descriptors on POSIX: renamed/symlink-swapped ancestors
        # cannot redirect reads or writes outside the selected root.
        if os.name != 'posix':
            yield None
            return
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root, flags)
        try:
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self.identity:
                raise AgentError('workspace_changed', 5)
            for part in path.parent.relative_to(self.root).parts:
                nxt = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = nxt
            yield fd
        finally:
            os.close(fd)

    def _read(self, path):
        with self.parent_fd(path) as parent:
            if parent is None:
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    raise AgentError('workspace_link_refused', 5)
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            else:
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'rb') as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
                    raise AgentError('text_file_limit_or_binary', 2)
                data = source.read(MAX_FILE + 1)
                if len(data) > MAX_FILE:
                    raise AgentError('text_file_limit_or_binary', 2)
                return data

    def read(self, name, missing=False):
        path = self.path(name)
        try:
            text = text_valid(self._read(path).decode('utf-8'))
            return {'path': name, 'text': text, 'hash': digest(text), 'version': None}
        except FileNotFoundError:
            if missing and path.parent.is_dir():
                return {'path': name, 'text': '', 'hash': None, 'version': None}
            raise AgentError('file_not_found', 2) from None
        except UnicodeError:
            raise AgentError('text_file_limit_or_binary', 2) from None

    def files(self):
        self.path('.', directory=True)
        results, pending, visited = [], [self.root], 0
        while pending:
            directory = pending.pop()
            # Revalidate before scanning; links never enter pending.
            if directory != self.root:
                self.path(directory.relative_to(self.root).as_posix(), True)
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    if visited > MAX_ENTRIES:
                        return {'paths': sorted(results), 'truncated': True}
                    if entry.is_symlink() or denied(entry.name):
                        continue
                    name = Path(entry.path).relative_to(self.root).as_posix()
                    try:
                        path = self.path(name)
                    except AgentError:
                        continue
                    if path.is_dir():
                        pending.append(path)
                    elif path.is_file():
                        results.append(name)
        return {'paths': sorted(results), 'truncated': False}

    def search(self, query):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise AgentError('invalid_search', 2)
        listed, matches, scanned = self.files(), [], 0
        for name in listed['paths']:
            try:
                row = self.read(name)
            except AgentError:
                continue
            scanned += len(row['text'].encode())
            if scanned > 512000:
                return {'matches': matches, 'truncated': True}
            for number, line in enumerate(row['text'].splitlines(), 1):
                if query in line:
                    matches.append({'path': name, 'line': number, 'text': line[:500]})
                    if len(matches) == 100:
                        return {'matches': matches, 'truncated': True}
        return {'matches': matches, 'truncated': listed['truncated']}

    def write(self, name, text, base_hash):
        text_valid(text)
        if os.name != 'posix':
            # Host-managed editor edits work on every platform. Native disk
            # mutation requires the descriptor-based adapter until Windows QA.
            raise AgentError('use_host_managed_edits_on_this_platform', 5)
        current = self.read(name, missing=True)
        if current['hash'] != base_hash:
            raise AgentError('stale_file', 5)
        path = self.path(name)
        temporary = '.swa-edit-' + secrets.token_hex(12)
        with self.parent_fd(path) as parent:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as output:
                    if base_hash is not None:
                        mode = os.stat(path.name, dir_fd=parent, follow_symlinks=False).st_mode
                        os.fchmod(output.fileno(), stat.S_IMODE(mode) & 0o777)
                    output.write(text.encode('utf-8'))
                    output.flush()
                    os.fsync(output.fileno())
                # Recheck after preparing bytes. Cooperative writers serialize
                # via engine lock; external writers can still race a final rename.
                if self.read(name, missing=True)['hash'] != base_hash:
                    raise AgentError('stale_file', 5)
                if base_hash is None:
                    os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                    os.unlink(temporary, dir_fd=parent)
                else:
                    os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
        return digest(text)
