"""Versioned bounded subprocess transport with independent Python fallback."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from .contracts import finite, integer
from thm._bounded_files import bounded_file_bytes
from thm.runtime.fabric.resources import ChildBudget, stop_owned_process_tree

MAX_BYTES = 1048576


class TransportError(ValueError):
    """Retryable frame/protocol failure; distinct from source identity failure."""


class SysCore:
    def __init__(self, executable=None, *, timeout=2.):
        finite(timeout, minimum=.001)
        if timeout > 30:
            raise ValueError('bounded SysCore timeout required')
        self.executable = str(Path(executable).resolve()) if executable else None
        self.timeout = timeout
        self.failures = 0
        self.last = {}

    def _request(self, operation, payload=b'', *, portable=False, deadline=None):
        deadline = time.monotonic()+self.timeout if deadline is None else deadline
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('SysCore operation deadline exhausted')
        request = bytes((1, operation)) + payload
        if len(request) > 4098 or (not self.executable and not portable):
            raise ValueError('SysCore unavailable or request too large')
        # The bundled executable never spawns a child or loads user code. It waits
        # for this frame until the parent's Windows Job Object is attached.
        command=[sys.executable,'-m','thm.systems.portable_worker'] if portable else [self.executable]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=os.name == 'posix')
        budget = None
        started = time.monotonic()
        try:
            budget = ChildBudget(process, memory=256*1024**2, cpu=remaining+1, io=8*MAX_BYTES)
            output, _ = process.communicate(struct.pack('<I', len(request))+request, timeout=max(.000001, deadline-time.monotonic()))
            if process.returncode or len(output) < 5 or len(output) > MAX_BYTES+5:
                raise TransportError('invalid SysCore response')
            size = struct.unpack('<I', output[:4])[0]
            if size != len(output)-4:
                raise TransportError('SysCore response framing mismatch')
            if output[4] != 0:
                raise OSError(output[5:1024].decode(errors='replace'))
            self.last = {'transport': 'pure-python' if portable else 'thm-syscore/1',
                         'wall_seconds': time.monotonic()-started, 'native_executed': not portable}
            return output[5:]
        finally:
            stop_owned_process_tree(process, budget)
            if budget is not None:
                budget.close()
            for stream in (process.stdout, process.stdin):
                if stream is not None and not stream.closed:
                    stream.close()

    def capabilities(self):
        if self.executable:
            try:
                value = json.loads(self._request(0))
                if value.get('schema') != 'thm-syscore/1' or value.get('max_bytes') != MAX_BYTES:
                    raise ValueError('capability negotiation mismatch')
                return value
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                self.failures += 1
        return {'schema': 'thm-syscore/1', 'native_io': False, 'fallback': 'pure-python', 'max_bytes': MAX_BYTES}

    def read_verified(self, path, expected_sha256, *, native_io=True, deadline=None):
        fallback_count=0
        if deadline is not None:finite(deadline)
        deadline = min(deadline, time.monotonic()+self.timeout) if deadline is not None else time.monotonic()+self.timeout
        if len(expected_sha256) != 64 or any(x not in '0123456789abcdef' for x in expected_sha256):
            raise ValueError('expected content identity required')
        if self.executable:
            try:
                data = self._request(2 if native_io else 1, os.fsencode(Path(path).absolute()), deadline=deadline)
                if hashlib.sha256(data).hexdigest() != expected_sha256:
                    raise ValueError('native consumed bytes identity mismatch')
                self.last['fallback_count']=0
                return data
            except (OSError, RuntimeError, TransportError, subprocess.TimeoutExpired):
                self.failures += 1
                fallback_count=1
        data = self._request(1,os.fsencode(Path(path).absolute()),portable=True,deadline=deadline)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError('source bytes identity mismatch')
        self.last = {'transport': 'pure-python', 'native_executed': False, 'fallback_count': fallback_count,
                     'zero_copy': False, 'copy_path': 'file-to-owned-bytes'}
        return data


class NativeAsyncIO:
    """Bounded batch completions; ownership lasts through completion/cancel/reap."""
    def __init__(self, syscore=None, *, capacity=16):
        integer(capacity, minimum=1, maximum=1024)
        self.syscore = syscore or SysCore()
        self.capacity = capacity
        self.pending = {}
        self.closed = False

    def submit(self, identity, path, sha256, deadline):
        finite(deadline)
        if self.closed or identity in self.pending or len(self.pending) >= self.capacity:
            raise ValueError('closed/duplicate/full completion queue')
        self.pending[identity] = (path, sha256, deadline)

    def cancel(self, identity):
        return self.pending.pop(identity, None) is not None

    def complete_batch(self):
        rows = []
        for identity in tuple(self.pending):
            path, sha, deadline = self.pending.pop(identity)
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                rows.append({'identity': identity, 'status': 'deadline', 'data': None})
                continue
            try:
                data = self.syscore.read_verified(path, sha, deadline=deadline)
                on_time=time.monotonic()<=deadline
                rows.append({'identity': identity, 'status': 'complete' if on_time else 'deadline', 'data': data if on_time else None,
                             'receipt': dict(self.syscore.last), 'zero_copy': False})
            except Exception as exc:
                rows.append({'identity': identity, 'status': 'failed', 'error': str(exc), 'data': None})
        return rows

    def close(self):
        self.pending.clear()
        self.closed = True
