"""Owned process boundary for trusted, explicitly configured storage transports.

Definitions must be pickleable instances or top-level factories. Native SDK
clients with non-pickleable handles are constructed by a factory in the worker.
Only the parent creates requests; never load user-supplied pickle artifacts.
"""
import builtins
import os
from pathlib import Path
import pickle
import signal
import subprocess
import sys
import tempfile
import time


def stop_tree(process, budget):
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif budget is not None:
        budget.close()
    elif process.poll() is None:
        process.kill()  # no supplied code runs before Job Object attachment
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    if process.stdin and not process.stdin.closed:
        process.stdin.close()


class TransportWorker:
    def __init__(self, definition, maximum):
        try:
            self.definition = pickle.dumps(definition)
        except (TypeError, AttributeError, pickle.PicklingError) as exc:
            raise TypeError('transport requires a pickleable instance or top-level factory') from exc
        if len(self.definition) > maximum + 1_000_000:
            raise ValueError('transport configuration exceeds bound')
        self.maximum = maximum + 1_000_000
        self.process = self.budget = self.workspace = None
        self.sequence = 0
        self.evidence = None

    def _start(self, deadline):
        from thm.runtime.fabric.resources import ChildBudget
        self.workspace = tempfile.TemporaryDirectory(prefix='thm-transport-')
        root = Path(self.workspace.name)
        (root / 'definition').write_bytes(self.definition)
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join(str(Path(p or '.').resolve()) for p in sys.path
                                          if Path(p or '.').is_dir())
        try:
            self.process = subprocess.Popen(
                [sys.executable, '-m', __name__, str(root), str(self.maximum)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=os.name == 'posix', env=env)
            if os.name == 'nt':
                # Wall deadlines are parent-enforced. Job Object owns descendants.
                self.budget = ChildBudget(self.process, memory=2**31, cpu=86400, io=2**50)
            if time.monotonic() >= deadline:
                raise TimeoutError('storage deadline exhausted before construction')
            self.process.stdin.write(b'go\n')
            self.process.stdin.flush()
        except BaseException:
            self.stop()
            raise

    def call(self, method, args, deadline):
        if time.monotonic() >= deadline:
            self.stop()
            raise TimeoutError('storage deadline exhausted before ' + method)
        try:
            if self.process is None:
                self._start(deadline)
            root = Path(self.workspace.name)
            self.sequence += 1
            request, response = root / 'request', root / 'response'
            raw = pickle.dumps((self.sequence, method, args))
            if len(raw) > self.maximum:
                raise ValueError('storage request exceeds bound')
            pending = root / 'request.pending'
            pending.write_bytes(raw)
            os.replace(pending, request)
            while time.monotonic() < deadline:
                if response.exists():
                    if response.stat().st_size > self.maximum:
                        raise ValueError('storage response exceeds bound')
                    value = pickle.loads(response.read_bytes())
                    response.unlink()
                    if time.monotonic() >= deadline:
                        break
                    self.evidence = value['evidence']
                    if self.evidence not in ('fixture-validated', 'environment-unvalidated'):
                        raise ValueError('transport provenance required')
                    if value['sequence'] != self.sequence:
                        raise ValueError('storage response identity mismatch')
                    if value.get('error'):
                        kind = getattr(builtins, value['error'], RuntimeError)
                        if not isinstance(kind, type) or not issubclass(kind, Exception):
                            kind = RuntimeError
                        raise kind('storage transport ' + method + ' failed')
                    return value['result']
                if self.process.poll() is not None:
                    raise RuntimeError('storage transport worker exited')
                time.sleep(min(.005, max(0, deadline - time.monotonic())))
            raise TimeoutError('storage transport deadline: ' + method)
        except (TimeoutError, BrokenPipeError):
            self.stop()
            raise

    def stop(self):
        try:
            if self.process is not None:
                stop_tree(self.process, self.budget)
        finally:
            self.process = self.budget = None
            if self.workspace is not None:
                self.workspace.cleanup()
                self.workspace = None

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass


def main():
    if sys.stdin.buffer.readline(4) != b'go\n':
        return 2
    root, maximum = Path(sys.argv[1]), int(sys.argv[2])
    definition = pickle.loads((root / 'definition').read_bytes())
    transport = definition() if callable(definition) else definition
    request, response = root / 'request', root / 'response'
    while True:
        if not request.exists():
            time.sleep(.005)
            continue
        if request.stat().st_size > maximum:
            raise ValueError('storage request bound')
        sequence, method, args = pickle.loads(request.read_bytes())
        request.unlink()
        try:
            if method not in ('stage', 'commit', 'abort', 'size', 'read', 'close'):
                raise ValueError('storage method not allowed')
            result = getattr(transport, method)(*args)
            if method == 'read' and (not isinstance(result, bytes) or len(result) > maximum - 1_000_000):
                raise ValueError('storage read result bound')
            value = dict(sequence=sequence, result=result)
        except Exception as exc:
            value = dict(sequence=sequence, error=type(exc).__name__)
        value['evidence'] = transport.evidence
        raw = pickle.dumps(value)
        if len(raw) > maximum:
            raw = pickle.dumps(dict(sequence=sequence, error='ValueError', evidence=transport.evidence))
        pending = root / 'response.pending'
        pending.write_bytes(raw)
        os.replace(pending, response)
        if method == 'close':
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
