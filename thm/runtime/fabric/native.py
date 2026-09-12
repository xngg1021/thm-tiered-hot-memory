"""Native vector libraries and explicit public SDK extension seams."""
import ctypes.util
import importlib
from pathlib import Path
import time
from .contracts import identity
from .indexes import ExactHost, clean_failed_build
from .inference import OrtInference
from .registry import ProviderUnavailable


class CuvsProvider(ExactHost):
    def fp32_accumulation(self):
        return False  # Public dtype alone does not establish the reduction math mode.

    def _api(self):
        algorithm = dict(self.spec.options)['algorithm']
        return importlib.import_module('cuvs.neighbors.' + algorithm), algorithm

    def probe(self):
        api, algorithm = self._api()
        import cupy as cp
        count = cp.cuda.runtime.getDeviceCount()
        return {'availability': 'available' if count else 'device-unavailable',
                'devices': ['cuda:'+str(i) for i in range(count)], 'algorithm': algorithm,
                'execution': 'build-only' if algorithm == 'vamana' else 'search', 'observed_kernel_dispatch': None}

    @clean_failed_build
    def build(self, vectors, ids, identity, **options):
        import cupy as cp
        api, algorithm = self._api(); start = time.perf_counter()
        host = super().build(vectors, ids, identity)
        params = dict(options.get('index_params', {}))
        ace = algorithm == 'cagra' and params.get('build_algo') == 'ace'
        if ace:
            budget = options.get('resident_budget_bytes', host.bytes*4)
            params['ace_params'] = api.AceParams(max_host_memory_gb=budget/1024**3,
                                                max_gpu_memory_gb=budget/1024**3, use_disk=False)
        dataset = host.data if ace else cp.asarray(host.data)
        if algorithm == 'brute_force':
            graph = api.build(dataset, metric='inner_product')
        else:
            if algorithm != 'vamana':
                params.setdefault('metric', 'inner_product')
            if algorithm == 'tiered_index':
                params.setdefault('algo', 'cagra')
            graph = api.build(api.IndexParams(**params), dataset)
        host.data = {'graph': graph, 'dataset': dataset, 'api': api, 'algorithm': algorithm,
                     'search_params': options.get('search_params', {}), 'dimension': dataset.shape[1],
                     'search_family': params.get('algo', 'cagra'), 'host_build': ace}
        cp.cuda.get_current_stream().synchronize()
        host.load_ms = (time.perf_counter()-start)*1000
        # Graph allocation varies by SDK; caller must budget a measured/declared ceiling.
        host.bytes = max(host.bytes, options.get('resident_budget_bytes', host.bytes*4))
        return host

    def search(self, handle, query_vectors, top_k):
        import cupy as cp
        state = handle.data; api = state['api']; algorithm = state['algorithm']
        if algorithm == 'vamana':
            raise ProviderUnavailable('Vamana is a build/export seam; DiskANN CPU search requires a separate provider')
        if type(top_k) is not int or not 1 <= top_k <= len(handle.ids):
            raise ValueError('invalid top-k')
        start = time.perf_counter(); queries = cp.asarray(query_vectors, dtype=cp.float32)
        if queries.ndim != 2 or queries.shape[1] != state['dimension']:
            raise ValueError('query dimension mismatch')
        if algorithm == 'brute_force':
            distances, neighbors = api.search(state['graph'], queries, top_k)
        elif algorithm == 'tiered_index':
            family = importlib.import_module('cuvs.neighbors.' + state['search_family'])
            distances, neighbors = api.search(family.SearchParams(**state['search_params']), state['graph'], queries, top_k)
        else:
            distances, neighbors = api.search(api.SearchParams(**state['search_params']), state['graph'], queries, top_k)
        distances = cp.asnumpy(distances); neighbors = cp.asnumpy(neighbors)
        import numpy as np
        if not np.isfinite(distances).all() or (neighbors < 0).any() or (neighbors >= len(handle.ids)).any():
            raise ValueError('invalid cuVS top-k receipt')
        # Inner product scores are returned directly. Approximate order is disclosed.
        result = [([handle.ids[int(i)] for i in row], distances[j].astype(float).tolist()) for j, row in enumerate(neighbors)]
        self.last = {'search_ms': (time.perf_counter()-start)*1000,
                     'host_device_bytes': int(queries.nbytes+distances.nbytes+neighbors.nbytes),
                     'document_matrix_transferred': False, 'resident_hit': True,
                     'index_identity': handle.identity.public(),
                     'semantic_class': 'exact-unvalidated-order' if algorithm == 'brute_force' else 'approximate',
                     'recall_against_exact': None, 'observed_kernel_dispatch': None}
        return result, dict(self.last)

    def export_vamana(self, handle, path):
        if handle.data['algorithm'] != 'vamana':
            raise ValueError('Vamana handle required')
        if Path(path).exists():
            raise FileExistsError('fresh export destination required')
        handle.data['api'].save(str(path), handle.data['graph'])
        return {'exported': True, 'format': 'DiskANN-compatible', 'source': handle.identity.public(), 'search_validated': False}


class McFaissProvider(ExactHost):
    def fp32_accumulation(self):
        return False  # Requires a version-specific MACA accumulation contract.

    def _api(self):
        import faiss
        # mcFaiss deliberately uses the faiss module name. Do not credit ordinary Faiss as MetaX.
        import ctypes.util
        if not ctypes.util.find_library('mcr') and not ctypes.util.find_library('runtime_cu'):
            raise ProviderUnavailable('MXMACA runtime provenance unavailable')
        return faiss

    def probe(self):
        api = self._api(); count = api.get_num_gpus()
        return {'availability': 'available' if count else 'device-unavailable',
                'devices': ['maca:'+str(i) for i in range(count)], 'observed_kernel_dispatch': None}

    @clean_failed_build
    def build(self, vectors, ids, identity, **options):
        api = self._api(); host = super().build(vectors, ids, identity)
        resources = api.StandardGpuResources()
        config = api.GpuIndexFlatConfig(); config.device = int(options.get('device_index', 0))
        graph = api.GpuIndexFlatIP(resources, host.data.shape[1], config)
        graph.add(host.data)
        host.data = {'index': graph, 'resources': resources}
        return host

    def search(self, handle, query_vectors, top_k):
        import numpy as np
        queries = np.ascontiguousarray(query_vectors, dtype=np.float32); start = time.perf_counter()
        if queries.ndim != 2 or not len(queries) or not np.isfinite(queries).all() or type(top_k) is not int or not 1 <= top_k <= len(handle.ids):
            raise ValueError('invalid mcFaiss query')
        scores, indices = handle.data['index'].search(queries, min(top_k, len(handle.ids)))
        if (indices < 0).any() or (indices >= len(handle.ids)).any() or not np.isfinite(scores).all():
            raise ValueError('incomplete mcFaiss results')
        result = [([handle.ids[int(i)] for i in indices[j]], scores[j].astype(float).tolist()) for j in range(len(queries))]
        self.last = {'search_ms': (time.perf_counter()-start)*1000,
                     'host_device_bytes': queries.nbytes+scores.nbytes+indices.nbytes,
                     'semantic_class': 'exact-unvalidated-order', 'resident_hit': True,
                     'document_matrix_transferred': False, 'index_identity': handle.identity.public()}
        return result, dict(self.last)


class WindowsMLCatalog(OrtInference):
    """Only already-ready provider libraries are registered. No EnsureReady calls."""
    def _catalog(self):
        if not hasattr(self, '_bootstrap'):
            from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import initialize
            self._bootstrap = initialize()
            self._bootstrap.__enter__()
        import winui3.microsoft.windows.ai.machinelearning as winml
        return winml.ExecutionProviderCatalog.get_default(), winml

    def discover(self):
        catalog, winml = self._catalog()
        self.ready = {p.name: p.library_path for p in catalog.find_all_providers()
                      if p.ready_state == winml.ExecutionProviderReadyState.READY and p.library_path}
        return [{'provider': name, 'state': 'ready', 'library_identity': identity(path)} for name, path in sorted(self.ready.items())]

    def probe(self):
        return {'provider': self.spec.provider_id, 'availability': 'available',
                'devices': self.discover(), 'automatic_install': False, 'observed_kernel_dispatch': None}

    def load(self, artifact, **options):
        self.discover(); ep = options.get('ep')
        if ep not in self.ready:
            raise ProviderUnavailable('selected Windows ML EP is not already ready')
        self.options['ep'] = ep
        return super().load(artifact, ep_library=self.ready[ep], **options)

    def close(self):
        super().close()
        if hasattr(self, '_bootstrap'):
            self._bootstrap.__exit__(None, None, None)
            del self._bootstrap


class NativeExtensionSeam:
    """Explicit SDK seam; discovery is L1, execution belongs to a registered bridge.

    C/ObjC headers and runtime releases vary by installation. This object never
    pretends symbol presence is a runnable Python implementation.
    """
    def __init__(self, spec):
        self.spec = spec; self.bridge = None

    def probe(self):
        libraries = dict(self.spec.options).get('libraries', ())
        observed = {name: bool(ctypes.util.find_library(name)) for name in libraries}
        return {'provider': self.spec.provider_id, 'availability': 'library-discovered' if any(observed.values()) else 'unavailable',
                'libraries': observed, 'devices': [], 'maturity': self.spec.maturity,
                'execution': 'extension-contract-only', 'observed_kernel_dispatch': None}

    def attach(self, bridge):
        if not all(callable(getattr(bridge, name, None)) for name in ('prepare', 'execute', 'receipt', 'close')):
            raise TypeError('native bridge protocol required')
        self.bridge = bridge

    def prepare(self, artifact, **options):
        if self.bridge is None:
            raise ProviderUnavailable('native SDK bridge not registered')
        return self.bridge.prepare(artifact, **options)

    def execute(self, *args, **kwargs):
        if self.bridge is None:
            raise ProviderUnavailable('native SDK bridge not registered')
        return self.bridge.execute(*args, **kwargs)

    def telemetry(self):
        return self.bridge.receipt() if self.bridge else {'hardware_validation': 'unvalidated', 'execution': 'unavailable'}

    def close(self):
        if self.bridge:
            self.bridge.close()
