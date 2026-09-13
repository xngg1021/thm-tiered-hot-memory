"""Bounded queue/admission/batching controller with tail and stall feedback."""
from collections import deque
from dataclasses import dataclass
import threading
from .contracts import finite, integer, nonempty
from .thermal import quantiles, thermal_backpressure

QOS = ('interactive', 'bulk', 'background', 'research', 'maintenance')


@dataclass(frozen=True)
class WorkItem:
    identity: str
    program: str
    qos: str
    arrived: float
    deadline: float
    provider: str = 'reference-cpu'
    storage: str = 'portable'

    def __post_init__(self):
        nonempty(self.identity)
        nonempty(self.program)
        if self.qos not in QOS:
            raise ValueError('invalid QoS')
        finite(self.arrived)
        finite(self.deadline)
        if self.deadline < self.arrived:
            raise ValueError('deadline precedes arrival')


class ElasticConcurrencyController:
    def __init__(self, *, concurrency=4, batch_size=1, worker_count=4, queue_depth=256, p95_slo=1., p99_slo=2.):
        for value in (concurrency, batch_size, worker_count, queue_depth):
            integer(value, minimum=1, maximum=100000)
        finite(p95_slo, minimum=1e-9)
        finite(p99_slo, minimum=p95_slo)
        self.limit = concurrency
        self.concurrency = concurrency
        self.batch_size = batch_size
        self.worker_count = worker_count
        self.queue_depth = queue_depth
        self.p95_slo, self.p99_slo = p95_slo, p99_slo
        self.background_share = .25
        self.queues = {q: deque() for q in QOS}
        self.active = {}
        self.known = set()
        self.latencies = deque(maxlen=2048)
        self.waits = deque(maxlen=2048)
        self.failures = 0
        self._lock = threading.RLock()

    def submit(self, item, now):
        finite(now)
        with self._lock:
            if now < item.arrived:
                raise ValueError('clock precedes arrival')
            if item.identity in self.known:
                raise ValueError('duplicate work identity')
            if now >= item.deadline or sum(map(len, self.queues.values())) >= self.queue_depth:
                return False
            self.queues[item.qos].append(item)
            self.known.add(item.identity)
            return True

    def dispatch(self, now):
        finite(now)
        with self._lock:
            available = max(0, min(self.concurrency, self.worker_count)-len(self.active))
            selected = []
            for qos in QOS:
                queue = self.queues[qos]
                while queue and queue[0].deadline <= now:
                    expired = queue.popleft()
                    self.known.remove(expired.identity)
                    self.failures += 1
                if qos in ('background', 'research', 'maintenance'):
                    background_active = sum(x.qos in ('background', 'research', 'maintenance') for x, _ in self.active.values())
                    capacity = max(0, int(self.concurrency*self.background_share)-background_active)
                else:
                    capacity = available
                count = min(available, capacity, self.batch_size, len(queue))
                for _ in range(count):
                    item = queue.popleft()
                    if now < item.arrived:
                        raise ValueError('clock regressed')
                    self.active[item.identity] = (item, now)
                    self.waits.append(now-item.arrived)
                    selected.append(item)
                    available -= 1
                if available == 0:
                    break
            return tuple(selected)

    def complete(self, identity, now, *, failed=False):
        finite(now)
        with self._lock:
            item, started = self.active[identity]
            if now < started:
                raise ValueError('clock regressed')
            self.active.pop(identity)
            self.known.remove(identity)
            self.latencies.append(now-item.arrived)
            self.failures += bool(failed or now > item.deadline)

    def cancel_expired(self, now):
        with self._lock:
            ids = [key for key, (item, _) in self.active.items() if item.deadline <= now]
            for key in ids:
                self.complete(key, now, failed=True)
            return tuple(ids)  # worker owner must cancel/reap before capacity is reused

    def feedback(self, thermal, pressure, *, now):
        with self._lock:
            advice = thermal_backpressure(thermal, now=now)
            self.background_share = advice['background_share']
            stalls = [finite(v) for v in pressure.values() if v is not None]
            tail = quantiles(self.latencies)
            if (stalls and max(stalls) >= .2) or (tail['p95'] is not None and tail['p95'] > self.p95_slo) or (tail['p99'] is not None and tail['p99'] > self.p99_slo):
                self.background_share = 0.
                self.concurrency = max(1, self.concurrency-1)
            elif len(self.latencies) >= 20 and advice['background_share'] >= .5 and stalls and max(stalls) < .05:
                self.concurrency = min(self.limit, self.concurrency+1)
            return {**self.receipt(), 'thermal_advice': advice}

    def receipt(self):
        with self._lock:
            return {'concurrency': self.concurrency, 'batch_size': self.batch_size,
                'worker_count': self.worker_count, 'queue_depth': self.queue_depth,
                'background_share': self.background_share, 'queue': {k: len(v) for k, v in self.queues.items()},
                'active': len(self.active), 'latency': quantiles(self.latencies), 'queue_wait': quantiles(self.waits),
                'failure_count': self.failures, 'device_assignment': {k: v[0].provider for k, v in self.active.items()}}
