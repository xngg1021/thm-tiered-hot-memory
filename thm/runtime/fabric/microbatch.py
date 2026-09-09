"""Online deadlines, bounded queue, FIFO fairness, and real queue-wait receipts."""
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
import threading
import time
from .contracts import finite


@dataclass
class Pending:
    value: object
    arrived: float
    deadline: float
    future: Future


class DeadlineAwareMicrobatcher:
    def __init__(self, execute, *, max_batch=32, max_wait_ms=2, slo_ms=100,
                 max_pending=256, clock=time.monotonic):
        if type(max_batch) is not int or not 1 <= max_batch <= 256 or not 1 <= max_pending <= 4096:
            raise ValueError('bounded batch/queue required')
        if not 0 <= max_wait_ms <= 100 or not 0 < slo_ms <= 60000:
            raise ValueError('bounded deadline required')
        self.execute = execute; self.max_batch = max_batch; self.max_wait = max_wait_ms/1000
        self.slo = slo_ms/1000; self.max_pending = max_pending; self.clock = clock
        self.queue = deque(); self.arrivals = deque(maxlen=64)
        self.condition = threading.Condition(); self.closed = False
        self.worker = threading.Thread(target=self._run, name='thm-microbatch', daemon=True)
        self.worker.start()

    def submit(self, value, *, deadline=None):
        if deadline is not None:
            finite(deadline, 'deadline')
        now = self.clock(); future = Future()
        with self.condition:
            if self.closed:
                raise RuntimeError('microbatcher closed')
            if len(self.queue) >= self.max_pending:
                raise RuntimeError('microbatch queue full')
            end = min(deadline, now+self.slo) if deadline is not None else now+self.slo
            self.queue.append(Pending(value, now, end, future))
            self.arrivals.append(now); self.condition.notify()
        return future

    def arrival_rate(self):
        if len(self.arrivals) < 2:
            return 0.0
        return (len(self.arrivals)-1)/max(1e-6, self.arrivals[-1]-self.arrivals[0])

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.queue)
                if self.closed and not self.queue:
                    return
                rate = self.arrival_rate()
                # Low arrival: serve one immediately. Only real queued opportunity grows batch.
                target = min(self.max_batch, max(1, int(rate*self.max_wait)+1))
                first = self.queue[0]
                stop = min(first.deadline, first.arrived+self.max_wait)
                while not self.closed and len(self.queue) < target and self.clock() < stop:
                    self.condition.wait(timeout=max(0, stop-self.clock()))
                batch = [self.queue.popleft() for _ in range(min(target, len(self.queue)))]
            now = self.clock(); active = []
            for pending in batch:
                if not pending.future.set_running_or_notify_cancel():
                    continue
                if now >= pending.deadline:
                    pending.future.set_exception(TimeoutError('request expired in queue'))
                else:
                    active.append(pending)
            if not active:
                continue
            started = self.clock()
            try:
                results = list(self.execute([p.value for p in active]))
                if len(results) != len(active):
                    raise ValueError('provider batch length mismatch')
                ended = self.clock()
                for pending, value in zip(active, results):
                    pending.future.set_result((value, {'actual_batch': len(active),
                        'queue_wait_ms': (started-pending.arrived)*1000,
                        'compute_time_ms': (ended-started)*1000, 'arrival_rate': rate,
                        'batch_fill_ratio': len(active)/self.max_batch, 'deadline_miss': ended > pending.deadline}))
            except Exception as exc:
                for pending in active:
                    pending.future.set_exception(exc)

    def close(self, *, wait=True):
        with self.condition:
            self.closed = True
            while self.queue:
                self.queue.popleft().future.cancel()
            self.condition.notify_all()
        if wait:
            self.worker.join()
