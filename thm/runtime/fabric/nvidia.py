"""cuBLASLt vendor heuristics and shape-bound CUDA graph execution seams."""
import importlib
import threading
import time
from .contracts import identity
from .indexes import ExactHost, ExactAccelerator, clean_failed_build
from .registry import ProviderUnavailable


class CublasLtExact(ExactHost):
    def probe(self):
        import cupy as cp
        import nvmath
        count = cp.cuda.runtime.getDeviceCount()
        return {'availability': 'available' if count else 'device-unavailable',
                'devices': ['cuda:'+str(i) for i in range(count)], 'version': nvmath.__version__,
                'driver_runtime': cp.cuda.runtime.driverGetVersion(), 'observed_kernel_dispatch': None}

    @clean_failed_build
    def build(self, vectors, ids, identity, **options):
        import cupy as cp
        host = super().build(vectors, ids, identity)
        start = time.perf_counter(); host.data = cp.asarray(host.data)
        cp.cuda.get_current_stream().synchronize(); host.load_ms += (time.perf_counter()-start)*1000
        return host

    def search(self, handle, query_vectors, top_k):
        import cupy as cp
        import numpy as np
        from nvmath.linalg import ComputeType
        from nvmath.linalg.advanced import Matmul
        raw = np.asarray(query_vectors, dtype=np.float32)
        if raw.ndim != 2 or not len(raw) or raw.shape[1] != handle.data.shape[1] or not np.isfinite(raw).all():
            raise ValueError('invalid cuBLASLt query')
        if type(top_k) is not int or not 1 <= top_k <= len(handle.ids):
            raise ValueError('invalid cuBLASLt top-k')
        # Bound temporary score/order buffers as well as the vendor workspace.
        scratch = len(handle.ids)*len(raw)*16
        if scratch > 64*1024**2:
            raise MemoryError('cuBLASLt request scratch budget exceeded')
        start = time.perf_counter(); queries = cp.asarray(raw)
        with Matmul(handle.data, queries.T, options={'compute_type': ComputeType.COMPUTE_32F_PEDANTIC,
                                                     'memory_limit': 16*1024**2, 'blocking': True}) as operation:
            algorithms = operation.plan(preferences={'limit': 1})
            plan_ms = (time.perf_counter()-start)*1000
            scores = operation.execute()
            order = cp.argsort(-scores, axis=0)[:top_k]
            values = cp.take_along_axis(scores, order, axis=0)
            indices = cp.asnumpy(order); values = cp.asnumpy(values)
        if not np.isfinite(values).all():
            raise ValueError('nonfinite cuBLASLt results')
        result = [([handle.ids[int(i)] for i in indices[:,j]], values[:,j].astype(float).tolist()) for j in range(len(raw))]
        self.last = {'search_ms': (time.perf_counter()-start)*1000, 'vendor_plan_ms': plan_ms,
                     'vendor_heuristic_candidates': len(algorithms), 'compute_type': 'COMPUTE_32F_PEDANTIC',
                     'observed_kernel_dispatch': None, 'index_identity': handle.identity.public(),
                     'semantic_class': 'exact-unvalidated-order', 'document_matrix_transferred': False,
                     'host_device_bytes': raw.nbytes+indices.nbytes+values.nbytes, 'scratch_bytes_upper_bound': scratch+16*1024**2}
        return result, dict(self.last)


class StableCudaGraph:
    """Explicit graph seam for an already validated operation and fixed inputs.

    This does not capture arbitrary user code on bootstrap or promise that an
    opaque operation fits a memory budget. The caller must run preparation in a
    bounded provider process and pass its admitted operation/shape identity.
    """
    def __init__(self, spec=None):
        self.spec = spec; self.graph = None; self.last = {}; self.lock = threading.RLock()

    def probe(self):
        from .catalog import BUILTINS
        return ExactAccelerator(next(s for s in BUILTINS if s.provider_id == 'nvidia.exact')).probe()

    def prepare(self, operation, inputs, *, operation_identity):
        import torch
        if not operation_identity or not inputs or any(x.device.type != 'cuda' for x in inputs):
            raise ValueError('validated CUDA operation and inputs required')
        with self.lock:
            self.inputs = [x.clone() for x in inputs]
            self.signature = [(tuple(x.shape), str(x.dtype), str(x.device)) for x in inputs]
            self.key = identity({'operation': operation_identity, 'inputs': self.signature})
            stream = torch.cuda.Stream(); stream.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(stream):
                operation(*self.inputs)
            torch.cuda.current_stream().wait_stream(stream)
            start = time.perf_counter(); self.graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(self.graph):
                self.outputs = operation(*self.inputs)
            self.last = {'preparation_ms': (time.perf_counter()-start)*1000, 'graph_identity': self.key, 'replayed': False}
            return {'prepared': True, **self.last}

    def execute(self, inputs):
        import torch
        with self.lock:
            if self.graph is None or [(tuple(x.shape), str(x.dtype), str(x.device)) for x in inputs] != self.signature:
                raise ProviderUnavailable('CUDA graph shape/device identity changed')
            start = time.perf_counter()
            for target, source in zip(self.inputs, inputs):
                target.copy_(source)
            self.graph.replay(); torch.cuda.synchronize()
            self.last.update(replayed=True, execution_ms=(time.perf_counter()-start)*1000)
            return self.outputs

    def telemetry(self):
        return {**self.last, 'observed_kernel_dispatch': None, 'hardware_validation': 'unvalidated'}

    def close(self):
        with self.lock:
            self.graph = None; self.inputs = []; self.outputs = None
