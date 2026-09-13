"""Versioned bounded subprocess transport with independent Python fallback."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from .contracts import finite, integer
from thm._bounded_files import bounded_file_bytes
from thm.runtime.fabric.resources import ChildBudget, stop_owned_process_tree

MAX_BYTES = 1048576


class SysCore:
    def __init__(self, executable=None, *, timeout=2.):
        finite(timeout, minimum=.001)
        if timeout > 30:
            raise ValueError('bounded SysCore timeout required')
        self.executable = str(Path(executable).resolve()) if executable else None
        self.timeout = timeout
        self.failures = 0
        self.last = {}

    def _request(self, operation, payload=b''):
        request = bytes((1, operation)) + payload
        if len(request) > 4098 or not self.executable:
            raise ValueError('SysCore unavailable or request too large')
        # The bundled executable never spawns a child or loads user code. It waits
        # for this frame until the parent's Windows Job Object is attached.
        process = subprocess.Popen([self.executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=os.name == 'posix')
        budget = None
        started = time.monotonic()
        try:
            budget = ChildBudget(process, memory=256*1024**2, cpu=self.timeout+1, io=8*MAX_BYTES)
            output, _ = process.communicate(struct.pack('<I', len(request))+request, timeout=self.timeout)
            if process.returncode or len(output) < 5 or len(output) > MAX_BYTES+5:
                raise ValueError('invalid SysCore response')
            size = struct.unpack('<I', output[:4])[0]
            if size != len(output)-4 or output[4] != 0:
                raise RuntimeError(output[5:1024].decode(errors='replace'))
            self.last = {'transport': 'thm-syscore/1', 'wall_seconds': time.monotonic()-started, 'native_executed': True}
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

    def read_verified(self, path, expected_sha256, *, native_io=True):
        if len(expected_sha256) != 64 or any(x not in '0123456789abcdef' for x in expected_sha256):
            raise ValueError('expected content identity required')
        if self.executable:
            try:
                data = self._request(2 if native_io else 1, os.fsencode(Path(path).resolve()))
                if hashlib.sha256(data).hexdigest() != expected_sha256:
                    raise ValueError('native consumed bytes identity mismatch')
                return data
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                self.failures += 1
        data = bounded_file_bytes(path, MAX_BYTES)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError('source bytes identity mismatch')
        self.last = {'transport': 'pure-python', 'native_executed': False, 'fallback_count': self.failures,
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
            original = self.syscore.timeout
            self.syscore.timeout = min(original, remaining)
            try:
                data = self.syscore.read_verified(path, sha)
                rows.append({'identity': identity, 'status': 'complete', 'data': data,
                             'receipt': dict(self.syscore.last), 'zero_copy': False})
            except Exception as exc:
                rows.append({'identity': identity, 'status': 'failed', 'error': str(exc), 'data': None})
            finally:
                self.syscore.timeout = original
        return rows

    def close(self):
        self.pending.clear()
        self.closed = True
