"""Generation-bound exact/ANN replicas. All optional arrays and runtimes are lazy."""
from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import threading
import time
from functools import wraps
from .contracts import IndexIdentity


def clean_failed_build(function):
    @wraps(function)
    def build(self, vectors, ids, identity, **options):
        before = self.handles.get(identity.key)
        try:
            return function(self, vectors, ids, identity, **options)
        except Exception:
            current = self.handles.get(identity.key)
            if current is not None and current is not before:
                current.close()
            if before is not None:
                self.handles[identity.key] = before
            raise
    return build


@dataclass
class VectorIndexHandle:
    identity: IndexIdentity
    ids: tuple
    data: object
    bytes: int
    close_callback: object = None
    last_used: float = 0
    load_ms: float = 0
    inflight: int = 0
    evicting: bool = False

    def close(self):
        if self.close_callback:
            self.close_callback()
        self.data = None


class ResidentHandleManager:
    def __init__(self, budgets=None):
        self.budgets = budgets or {'cpu': 256*1024**2}
        if any(type(v) is not int or v <= 0 for v in self.budgets.values()):
            raise ValueError('positive device memory budgets required')
        self.handles = {}; self.lock = threading.RLock()

    def usage(self, device):
        return sum(h.bytes for h in self.handles.values() if h.identity.device == device)

    def _remove(self, key):
        handle = self.handles[key]
        if handle.inflight:
            handle.evicting = True
        else:
            self.handles.pop(key); handle.close()

    def publish(self, handle, *, current_generation):
        with self.lock:
            if handle.identity.generation != current_generation:
                handle.close(); raise ValueError('index source generation changed')
            key = handle.identity.key
            if key in self.handles:
                handle.close(); return self.handles[key]
            device = handle.identity.device; budget = self.budgets.get(device, 0)
            if handle.bytes > budget:
                handle.close(); raise MemoryError('resident handle exceeds device budget')
            for old_key, old in sorted(self.handles.items(), key=lambda x: x[1].last_used):
                if self.usage(device)+handle.bytes <= budget:
                    break
                if old.identity.device == device and not old.inflight:
                    self._remove(old_key)
            if self.usage(device)+handle.bytes > budget:
                handle.close(); raise MemoryError('resident memory pinned by inflight requests')
            self.handles[key] = handle
            return handle

    @contextmanager
    def acquire(self, index_identity):
        with self.lock:
            handle = self.handles.get(index_identity.key)
            if handle is None or handle.evicting or handle.identity != index_identity:
                raise KeyError('resident handle missing or stale')
            handle.inflight += 1; handle.last_used = time.monotonic()
        try:
            yield handle
        finally:
            with self.lock:
                handle.inflight -= 1
                if handle.evicting and not handle.inflight:
                    self._remove(index_identity.key)

    def invalidate(self, *, scope=None, generation=None, device=None, provider=None):
        with self.lock:
            for key, handle in list(self.handles.items()):
                i = handle.identity
                if (scope is None or i.scope == scope) and (generation is None or i.generation != generation) and (device is None or i.device == device) and (provider is None or i.provider == provider):
                    self._remove(key)

    def pressure(self, device, available_bytes):
        with self.lock:
            for key, handle in sorted(list(self.handles.items()), key=lambda x: x[1].last_used):
                if self.usage(device) <= available_bytes:
                    break
                if handle.identity.device == device:
                    self._remove(key)

    def close(self):
        self.invalidate()


class ExactHost:
    def __init__(self, spec=None):
        self.spec = spec; self.handles = {}; self.last = {}

    def probe(self):
        try:
            import numpy
            return {'availability': 'available', 'version': numpy.__version__, 'devices': ['cpu']}
        except ImportError:
            return {'availability': 'dependency-missing', 'devices': []}

    def build(self, vectors, ids, identity, **options):
        import numpy as np
        start = time.perf_counter()
        values = np.ascontiguousarray(vectors, dtype=np.float32)
        if values.ndim != 2 or len(values) != len(ids) or not len(ids) or not np.isfinite(values).all() or len(set(ids)) != len(ids):
            raise ValueError('invalid index vectors/IDs')
        # Immutable owned replica; caller mutation cannot change a serving index.
        values = values.copy(); values.setflags(write=False)
        handle = VectorIndexHandle(identity, tuple(ids), values, values.nbytes,
                                   load_ms=(time.perf_counter()-start)*1000)
        self.handles[identity.key] = handle
        handle.close_callback = lambda: self.handles.pop(identity.key, None) if self.handles.get(identity.key) is handle else None
        return handle

    def load_handle(self, identity):
        handle = self.handles[identity.key]
        if handle.identity != identity or handle.data is None:
            raise ValueError('index identity stale')
        return handle

    def search(self, handle, query_vectors, top_k):
        import numpy as np
        queries = np.asarray(query_vectors, dtype=np.float32)
        if queries.ndim != 2 or queries.shape[1] != handle.data.shape[1] or not np.isfinite(queries).all():
            raise ValueError('invalid query vectors')
        if type(top_k) is not int or not 1 <= top_k <= len(handle.ids):
            raise ValueError('invalid top-k')
        start = time.perf_counter()
        scores = handle.data @ queries[0] if len(queries) == 1 else handle.data @ queries.T
        if scores.ndim == 1:
            scores = scores[:, None]
        order = np.argsort(-scores, axis=0, kind='stable')[:top_k]
        result = [([handle.ids[int(i)] for i in order[:, q]], [float(scores[i, q]) for i in order[:, q]]) for q in range(len(queries))]
        self.last = {'search_ms': (time.perf_counter()-start)*1000, 'host_device_bytes': 0,
                     'resident_hit': True, 'index_identity': handle.identity.public(), 'semantic_class': 'exact',
                     'observed_kernel_dispatch': None}
        return result, dict(self.last)

    def update_or_rebuild(self, vectors, ids, identity, **options):
        return self.build(vectors, ids, identity, **options)

    def memory_usage(self):
        return sum(h.bytes for h in self.handles.values() if h.data is not None)

    def capabilities(self):
        return {'exact': True, 'resident_handle': True, 'incremental_update': False, 'atomic_publish': 'manager'}

    def telemetry(self):
        return dict(self.last)

    def close(self):
        for handle in list(self.handles.values()):
            handle.close()
        self.handles.clear()


class ExactAccelerator(ExactHost):
    """Resident Torch device matrix; only queries and top-k results transfer."""
    def _runtime(self):
        options = dict(self.spec.options) if self.spec else {}
        if options.get('extension'):
            importlib.import_module(options['extension'])
        torch = importlib.import_module('torch')
        return torch, options.get('device', 'cuda')

    def probe(self):
        torch, device = self._runtime()
        api = torch.backends.mps if device == 'mps' else getattr(torch, device)
        available = api.is_available()
        options = dict(self.spec.options) if self.spec else {}
        if options.get('require_hip') and not getattr(torch.version, 'hip', None):
            available = False
        if options.get('require_cuda') and (getattr(torch.version, 'hip', None) or 'metax' in torch.__version__.lower()):
            available = False
        if options.get('require_maca') and not ('metax' in torch.__version__.lower() or getattr(torch.version, 'maca', None)):
            available = False
        from .drivers import torch_runtime
        return {'availability': 'available' if available else 'device-unavailable',
                'devices': [device] if available else [], 'version': torch.__version__,
                'driver_runtime': torch_runtime(torch, device) if available else None, 'observed_kernel_dispatch': None}

    @clean_failed_build
    def build(self, vectors, ids, identity, **options):
        host = super().build(vectors, ids, identity)
        torch, device = self._runtime()
        if identity.device.split(':')[0] != device:
            raise ValueError('device identity mismatch')
        start = time.perf_counter()
        host.data = torch.tensor(host.data, dtype=torch.float32, device=identity.device)
        getattr(torch, device).synchronize()
        host.load_ms += (time.perf_counter()-start)*1000
        self.last = {'build_host_device_bytes': host.bytes, 'load_ms': host.load_ms}
        return host

    def search(self, handle, query_vectors, top_k):
        import numpy as np
        torch, device = self._runtime()
        queries = np.asarray(query_vectors, dtype=np.float32)
        if queries.ndim != 2 or not len(queries) or queries.shape[1] != handle.data.shape[1] or not np.isfinite(queries).all() or type(top_k) is not int or not 1 <= top_k <= len(handle.ids):
            raise ValueError('invalid resident search')
        start = time.perf_counter()
        q = torch.as_tensor(queries, dtype=torch.float32, device=handle.identity.device)
        scores = handle.data @ q.T
        # Stable ordering preserves original row order for equal device scores.
        order = torch.argsort(scores, dim=0, descending=True, stable=True)[:top_k]
        values = torch.gather(scores, 0, order)
        indices = order.cpu().numpy(); values = values.cpu().numpy()
        getattr(torch, device).synchronize()
        if not np.isfinite(values).all():
            raise ValueError('nonfinite device scores')
        results = [([handle.ids[int(i)] for i in indices[:, j]], values[:, j].astype(float).tolist()) for j in range(len(queries))]
        self.last = {'search_ms': (time.perf_counter()-start)*1000,
                     'host_device_bytes': queries.nbytes + indices.nbytes + values.nbytes,
                     'document_matrix_transferred': False, 'resident_hit': True,
                     'index_identity': handle.identity.public(), 'semantic_class': 'exact',
                     'observed_kernel_dispatch': None}
        return results, dict(self.last)


class HNSWGeneric(ExactHost):
    def probe(self):
        import hnswlib
        return {'availability': 'available', 'devices': ['cpu'], 'semantic_class': 'approximate'}

    @clean_failed_build
    def build(self, vectors, ids, identity, **options):
        import hnswlib
        import numpy as np
        host = super().build(vectors, ids, identity)
        graph = hnswlib.Index(space='ip', dim=host.data.shape[1])
        graph.init_index(max_elements=len(ids), ef_construction=options.get('ef_construction', 100),
                         M=options.get('M', 16), random_seed=options.get('seed', 0))
        graph.add_items(host.data, np.arange(len(ids)), num_threads=1)
        graph.set_ef(options.get('ef_search', 100))
        graph.set_num_threads(1)
        host.data = graph
        # Public serialization size would require I/O; conservative allocated estimate.
        host.bytes += len(ids)*options.get('M', 16)*16
        return host

    def search(self, handle, query_vectors, top_k):
        start = time.perf_counter()
        labels, distances = handle.data.knn_query(query_vectors, k=min(top_k, len(handle.ids)), num_threads=1)
        result = [([handle.ids[int(i)] for i in labels[j]], [float(1-v) for v in distances[j]]) for j in range(len(labels))]
        self.last = {'search_ms': (time.perf_counter()-start)*1000, 'semantic_class': 'approximate',
                     'recall_against_exact': None, 'selected_id_delta': None, 'rank_delta': None,
                     'context_quality_delta': None, 'host_device_bytes': 0, 'index_identity': handle.identity.public()}
        return result, dict(self.last)

    def capabilities(self):
        return {**super().capabilities(), 'exact': False, 'approximate': True}


def ann_quality(reference, candidate):
    """Ranking quality only; context quality requires a separate packed receipt."""
    ref_ids = list(reference); ids = list(candidate)
    overlap = len(set(ref_ids) & set(ids))
    return {'recall_against_exact': overlap/len(set(ref_ids)) if ref_ids else 1.0,
            'top_k_overlap': overlap, 'selected_id_delta': len(set(ref_ids)^set(ids)),
            'rank_delta': sum(a != b for a, b in zip(ref_ids, ids)) + abs(len(ref_ids)-len(ids)),
            'context_quality_delta': None}
