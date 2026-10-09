"""Approved argv execution with clean environment and bounded process groups."""
import os
import signal
import subprocess
import threading
import time
from .errors import AgentError


def run(argv, cwd, cancel, timeout=30, limit=32768, input_bytes=None):
    if os.name != 'posix':
        raise AgentError('native_execution_unavailable_on_this_platform', 5)
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 64
            or any(not isinstance(x, str) or '\x00' in x or len(x) > 4096 for x in argv)
            or not os.path.isabs(argv[0]) or type(timeout) is not int or not 1 <= timeout <= 60):
        raise AgentError('invalid_command_use_absolute_executable', 2)
    if cancel.is_set():
        raise AgentError('cancelled', 130)
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    process = subprocess.Popen(argv, cwd=cwd, env=env, shell=False,
                               stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True, close_fds=True)
    output, overflow = bytearray(), threading.Event()
    def read():
        try:
            while True:
                chunk = process.stdout.read1(4096)
                if not chunk:
                    break
                available = limit - len(output)
                output.extend(chunk[:available])
                if len(chunk) > available:
                    overflow.set()
        finally:
            process.stdout.close()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    def feed():
        try:
            process.stdin.write(input_bytes)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    if input_bytes is not None:
        threading.Thread(target=feed, daemon=True).start()
    reason = None
    started = time.monotonic()
    try:
        while process.poll() is None:
            if cancel.is_set():
                reason = 'cancelled'
                break
            if overflow.is_set():
                reason = 'output_limit'
                break
            if time.monotonic() - started >= timeout:
                reason = 'timeout'
                break
            time.sleep(.02)
    finally:
        # Includes background children left behind by an already-exited parent.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        reader.join(timeout=2)
    return {'exitCode': process.returncode, 'output': output.decode('utf-8', errors='replace'),
            'outcome': reason or ('output_limit' if overflow.is_set() else 'completed')}
