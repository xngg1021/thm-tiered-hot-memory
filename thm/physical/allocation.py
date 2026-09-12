"""Physical representations and caller-owned allocator bindings, orthogonal to T0-T3."""
from dataclasses import dataclass
import threading
import uuid
from thm.runtime.fabric.contracts import identity


KINDS = ('host-dram', 'pinned-host', 'unified-memory', 'device-vram', 'staging', 'pmem', 'dax', 'cxl')


class AllocationCleanupError(RuntimeError):
    """All evictions were attempted; failed ownership remains quarantined."""

    def __init__(self, failures):
        self.failure_count = len(failures)
        self.failures = tuple(failures[:128])
        super().__init__(f'{self.failure_count} allocation releases failed')


@dataclass
class Allocation:
    allocation_id: str
    representation_sha256: str
    generation: str
    kind: str
    device: str
    byte_length: int
    owner: str
    data: object
    release: object
    inflight: int = 0
    evicted: bool = False

    def public(self):
        return {'allocation_id': self.allocation_id, 'representation_sha256': self.representation_sha256,
                'generation': identity(self.generation), 'kind': self.kind, 'device': identity(self.device),
                'byte_length': self.byte_length, 'owner': identity(self.owner), 'inflight': self.inflight,
                'evicted': self.evicted, 'logical_tier': None}


class AllocationPool:
    def __init__(self, capacity_bytes):
        if type(capacity_bytes) is not int or capacity_bytes <= 0:
            raise ValueError('positive physical capacity required')
        self.capacity = capacity_bytes
        self.allocations, self.lock, self.closed = {}, threading.RLock(), False

    def allocate(self, *, representation_sha256, generation, kind, device, size, owner, allocator=None):
        if kind not in KINDS or type(size) is not int or size < 1 or not generation or not device or not owner:
            raise ValueError('complete allocation identity required')
        if len(representation_sha256) != 64 or any(c not in '0123456789abcdef' for c in representation_sha256):
            raise ValueError('representation hash required')
        with self.lock:
            if self.closed:
                raise ValueError('allocation pool closed')
            if sum(a.byte_length for a in self.allocations.values()) + size > self.capacity:
                raise MemoryError('physical allocation capacity')
            if allocator is None:
                if kind not in ('host-dram', 'staging'):
                    raise ValueError('specialized memory requires explicit allocator')
                data, release = bytearray(size), lambda: None
            else:
                data, release = allocator(size)
                if not callable(release):
                    raise TypeError('allocator must return ownership release callback')
            a = Allocation(uuid.uuid4().hex, representation_sha256, generation, kind, device, size, owner, data, release)
            self.allocations[a.allocation_id] = a
            return a

    def acquire(self, allocation_id, *, generation, owner):
        from contextlib import contextmanager
        @contextmanager
        def lease():
            with self.lock:
                a = self.allocations[allocation_id]
                if self.closed or a.evicted or a.generation != generation or a.owner != owner:
                    raise ValueError('stale or foreign allocation')
                a.inflight += 1
            try:
                yield a.data
            finally:
                with self.lock:
                    a.inflight -= 1
                    if a.evicted and not a.inflight:
                        self._release(a)
        return lease()

    def _release(self, allocation):
        # A failed release retains ownership but cannot be acquired again.
        # A subsequent explicit close/evict may retry the caller's callback.
        allocation.release()
        allocation.data = None
        self.allocations.pop(allocation.allocation_id, None)

    def evict(self, allocation_id):
        with self.lock:
            a = self.allocations[allocation_id]
            a.evicted = True
            if not a.inflight:
                self._release(a)

    def close(self):
        with self.lock:
            self.closed = True
            failures = []
            for key in list(self.allocations):
                try:
                    self.evict(key)
                except Exception as exc:
                    failures.append((key, type(exc).__name__))
            if failures:
                raise AllocationCleanupError(failures)
