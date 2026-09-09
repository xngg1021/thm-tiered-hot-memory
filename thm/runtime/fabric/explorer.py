"""Cancelable process-tree bounded shadow work. Foreground never waits for it."""
import json
import os
import signal
import subprocess
import sys
import threading
import time


class BoundedShadowExplorer:
    def __init__(self, *, wall_seconds=2, interval_seconds=60, memory_bytes=512*1024**2,
                 io_bytes=16*1024**2, cpu_seconds=1, clock=time.monotonic):
        if not 0 < wall_seconds <= 10 or interval_seconds < 10 or not 0 < cpu_seconds <= 5:
            raise ValueError('bounded shadow budget required')
        if memory_bytes <= 0 or io_bytes < 0:
            raise ValueError('invalid resource budget')
        self.wall = wall_seconds; self.interval = interval_seconds; self.memory = memory_bytes
        self.io = io_bytes; self.cpu = cpu_seconds; self.clock = clock
        self.last_started = None; self.process = None; self.thread = None
        self.cancelled = threading.Event(); self.lock = threading.RLock(); self.last_receipt = {}

    def eligible(self, *, foreground_pressure=0, battery_low=False, thermal_pressure=False,
                 estimated_io=0, estimated_compile_ms=0, gpu=False, gpu_duty_observed=False):
        return (not self.cancelled.is_set() and foreground_pressure <= .2 and not battery_low and not thermal_pressure
                and estimated_io <= self.io and estimated_compile_ms <= self.wall*1000
                and (not gpu or gpu_duty_observed)
                and (self.last_started is None or self.clock()-self.last_started >= self.interval)
                and not (self.thread and self.thread.is_alive()))

    def submit(self, task, callback, **pressure):
        with self.lock:
            if not self.eligible(**pressure):
                return False
            self.last_started = self.clock()
            self.thread = threading.Thread(target=self._run, args=(task, callback), name='thm-shadow', daemon=True)
            self.thread.start()
            return True

    def _kill(self, process):
        if process.poll() is not None:
            return
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5)
            if process.poll() is None:
                process.kill()

    def _run(self, task, callback):
        start = self.clock()
        envelope = {'task': task, 'limits': {'memory': self.memory, 'io': self.io, 'cpu': self.cpu}}
        env = dict(os.environ)
        # Child-only limits; never alter the host process or global environment.
        env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
        try:
            with self.lock:
                if self.cancelled.is_set():
                    return
                self.process = subprocess.Popen([sys.executable, '-m', 'thm.runtime.fabric.shadow_worker'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, env=env, start_new_session=os.name == 'posix')
                process = self.process
            output, _ = process.communicate(json.dumps(envelope), timeout=self.wall)
            if process.returncode:
                raise RuntimeError('shadow worker failed')
            line = next(s[11:] for s in reversed(output.splitlines()) if s.startswith('THM_RESULT:'))
            result = json.loads(line)
            if not self.cancelled.is_set():
                callback(result)
            self.last_receipt = {'status': 'completed', 'wall_ms': (self.clock()-start)*1000,
                                 'generation_calls': 0, 'authority_mutations': 0}
        except Exception as exc:
            with self.lock:
                if self.process:
                    self._kill(self.process)
                    self.process.communicate(timeout=5)
            self.last_receipt = {'status': 'deferred', 'reason': type(exc).__name__,
                                 'wall_ms': (self.clock()-start)*1000, 'generation_calls': 0}
        finally:
            with self.lock:
                self.process = None

    def close(self):
        self.cancelled.set()
        with self.lock:
            if self.process:
                self._kill(self.process)
        if self.thread and threading.current_thread() != self.thread:
            self.thread.join(timeout=self.wall+6)
