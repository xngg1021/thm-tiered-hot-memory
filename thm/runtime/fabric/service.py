"""Product runtime: safe first request, passive observations, bounded idle replay."""
from dataclasses import asdict
from pathlib import Path
import threading
import time
from .contracts import IndexIdentity, RuntimeSample, identity
from .explorer import BoundedShadowExplorer
from .hardware import HostDeviceProvider
from .indexes import ResidentHandleManager
from .optimizer import Candidate, MaterialGainGate, PassiveTelemetry, PolicySelector, SemanticGuard
from .registry import builtin_registry
from .store import ProfileKey, ProfileStore, scale_bucket


class ResidentExecutor:
    def __init__(self, registry, provider='host.exact', device='cpu', memory_budget=256*1024**2):
        self.registry = registry; self.provider_id = provider; self.device = device
        self.manager = ResidentHandleManager({device: memory_budget}); self.last = {}

    def search(self, *, scope, generation, embedding_profile, ids, matrix, queries, top_k, placement='dram'):
        provider = self.registry.get(self.provider_id)
        description = self.registry.describe(self.provider_id)
        key = IndexIdentity(scope, generation, embedding_profile, self.provider_id,
                            identity(description['versions']), identity({'metric': 'inner_product'}),
                            device=self.device, placement=placement, runtime=identity(description))
        with self.manager.lock:
            self.manager.invalidate(scope=scope, generation=generation)
            hit = key.key in self.manager.handles
            if not hit:
                handle = provider.build(matrix, ids, key)
                self.manager.publish(handle, current_generation=generation)
        with self.manager.acquire(key) as handle:
            result, receipt = provider.search(handle, queries, min(top_k, len(ids)))
            self.last = {**receipt, 'resident_hit': hit, 'load_ms': 0 if hit else handle.load_ms,
                         'resident_bytes': handle.bytes}
        return result, dict(self.last)

    def close(self):
        self.manager.close()


class SafeBootstrapPolicy:
    def select(self, *, mode, encoder):
        if mode in ('literal', 'sparse'):
            return {'profile': 'sparse-safe', 'mode': mode, 'source': 'bootstrap', 'fallback': None}
        if encoder is not None and getattr(getattr(encoder, 'profile', None), 'precision', 'fp32') == 'fp32':
            return {'profile': 'fp32-reference', 'mode': mode, 'source': 'bootstrap', 'fallback': None}
        return {'profile': 'sparse-safe', 'mode': 'sparse', 'source': 'bootstrap', 'fallback': 'dense-reference-not-ready'}


class RuntimeService:
    """Wrap an existing derived SearchIndex; no mutation of source or embedding authority.

    Request replay is private, small, CPU bounded and disposable. A published point
    is considered only at the next explicit session boundary. Research runners
    continue to call SearchIndex directly for fixed-identity reference execution.
    """
    def __init__(self, index, *, encoder=None, model_id=None, policy='auto-safe', store_path=None,
                 memory_budget=256*1024**2, background=True, registry=None, explorer=None):
        if policy not in ('reference', 'auto-safe', 'auto-throughput', 'approximate-performance'):
            raise ValueError('invalid runtime policy')
        self.index = index; self.encoder = encoder; self.model_id = model_id; self.policy = policy
        self.memory_budget = memory_budget; self.registry = registry or builtin_registry()
        self.graph = HostDeviceProvider().discover()
        from ..identity import implementation_identity
        self.implementation = implementation_identity()
        self.store = ProfileStore(store_path or index.path.parent / ('runtime-'+identity(str(index.path))[:16]+'.sqlite'))
        self.telemetry = PassiveTelemetry(); self.gate = MaterialGainGate()
        self.explorer = explorer or BoundedShadowExplorer(memory_bytes=memory_budget)
        self.background = background and policy != 'reference'; self.lock = threading.RLock()
        self.pinned = {}; self.executors = {}; self.decisions = []; self.closed = False
        self.candidates = [Candidate('host.exact')]

    def _key(self, scope, workload, settings):
        p = getattr(self.encoder, 'profile', None)
        with self.index._lock:
            self.index._refresh_caches()
            generation = self.index.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
            if generation is None:
                raise ValueError('scope not indexed')
            count = self.index.db.execute('SELECT count(*) FROM docs WHERE scope=?', (scope,)).fetchone()[0]
        from thm.features import RetrievalFeatures
        settings = dict(settings)
        if 'features' in settings:
            settings['features'] = RetrievalFeatures.parse(settings['features']).identity()
        versions = [self.registry.describe(c.provider)['versions'] for c in self.candidates]
        key = ProfileKey(self.graph.fingerprint, self.graph.os+':'+self.graph.build, identity('cpu-no-driver'),
                         identity(versions), getattr(p, 'source_manifest_sha256', 'none'),
                         getattr(p, 'derived_manifest_sha256', None) or 'none', getattr(p, 'dimension', 0),
                         getattr(p, 'precision', 'fp32'), identity({'generation': generation[0], 'profile': getattr(p, 'id', None)}),
                         scale_bucket(count, getattr(p, 'dimension', 0), self.memory_budget),
                         identity(settings), 'dram', workload, self.policy, self.implementation,
                         shape_bucket=identity({'scope': scope, 'fanout': settings.get('candidate_limit', 100)}))
        return key, generation[0], count

    def _select(self, key, workload):
        if key.id in self.pinned:
            return self.pinned[key.id]
        accepted = {x['candidate']: x for x in self.store.observations(key)
                    if x['semantic_status'] == 'strict' and x['material_gain_status'] == 'accepted' and x['pareto']}
        points = []
        for c in self.candidates:
            row = accepted.get(identity(c.id))
            if row and not self.store.quarantined(key, c.provider) and SemanticGuard.eligible(c, self.policy):
                points.append({'id': c.id, 'workload': workload, 'semantic_safe': True, 'semantic_class': 'strict', **row['measurement']})
        selected = PolicySelector().select(points, workload, {})
        candidate = next((c for c in self.candidates if selected and c.id == selected['id']), None)
        self.pinned[key.id] = candidate
        return candidate

    def new_session(self):
        with self.lock:
            self.pinned.clear()
            return {'reason': 'explicit-new-session', 'profile_migration': 'eligible-stored-point', 'semantic_policy': self.policy}

    def search(self, scope, query, *, workload='interactive', **settings):
        start = time.perf_counter(); cpu = time.process_time()
        with self.lock:
            if self.closed:
                raise RuntimeError('runtime service closed')
            if any(k in settings for k in ('encoder', 'model_id', 'scorer')):
                raise ValueError('runtime owns execution settings')
            mode = settings.get('mode', 'sparse')
            boot = SafeBootstrapPolicy().select(mode=mode, encoder=self.encoder)
            effective = {**settings, 'mode': boot['mode']}
            key, generation, count = self._key(scope, workload, effective)
            candidate = self._select(key, workload) if self.policy != 'reference' and mode in ('dense', 'hybrid') else None
            provider = candidate.provider if candidate else 'reference'
            fallback = boot['fallback']
            executor = None
            if candidate:
                if candidate.id not in self.executors:
                    self.executors[candidate.id] = ResidentExecutor(self.registry, candidate.provider, candidate.device, self.memory_budget)
                executor = self.executors[candidate.id]
            from thm.physical.joint import JointComputeDataPlanner
            plan = JointComputeDataPlanner().plan(self.index, scope, embedding_profile=getattr(getattr(self.encoder, 'profile', None), 'id', None),
                candidate=candidate, workload=workload, policy=self.policy)
            self.index._vector_executor = executor
            try:
                result = self.index.search(scope, query, encoder=self.encoder, model_id=self.model_id, **effective)
            except Exception as exc:
                if not candidate:
                    raise
                self.store.failure(key, provider, 'execution')
                self.index._vector_executor = None; self.index._results.clear()
                result = self.index.search(scope, query, encoder=self.encoder, model_id=self.model_id, **effective)
                self.pinned[key.id] = None; fallback = 'provider-failed:' + type(exc).__name__
            finally:
                self.index._vector_executor = None
            elapsed = (time.perf_counter()-start)*1000
            clocks = result.get('timing_ms', {})
            self.telemetry.observe(RuntimeSample(provider, workload, elapsed, cpu_seconds=time.process_time()-cpu,
                encode_ms=clocks.get('query_embedding'), search_ms=clocks.get('dense_scoring'),
                materialization_ms=clocks.get('row_materialization'), packing_ms=clocks.get('pack'),
                fallback=bool(fallback), semantic_policy=self.policy,
                queries_per_second=1000/elapsed if elapsed else None,
                profile_source='stored' if candidate else 'bootstrap'))
            result['execution_plan'] = plan.receipt()
            result['runtime_receipt'] = {'schema': 2, 'evidence_layer': 'systems-runtime',
                'hardware_fingerprint': self.graph.fingerprint, 'provider': provider,
                'actual_provider': 'reference' if fallback and candidate else provider,
                'device': candidate.device if candidate and not fallback else 'cpu',
                'embedding_profile': getattr(getattr(self.encoder, 'profile', None), 'id', None),
                'index_provider': provider, 'physical_placement': 'dram', 'semantic_policy': self.policy,
                'profile_source': 'stored' if candidate else 'bootstrap', 'profile_freshness': 'fresh',
                'profile_key': key.id, 'batch_policy': 'deadline-aware-opportunity',
                'latency_ms': elapsed, 'fallback': fallback, 'generation_calls': 0,
                'memory_quality_improved': None, 'observed_kernel_dispatch': None}
            self._maybe_explore(key, generation, count, scope, query, effective)
            return result

    def _maybe_explore(self, key, generation, count, scope, query, settings):
        p = getattr(self.encoder, 'profile', None)
        if not self.background or p is None or settings.get('mode') not in ('dense', 'hybrid'):
            return
        # Custom token counters and retrieval feature experiments are not replayed.
        from thm.retrieval import TokenCounter
        from thm.features import RetrievalFeatures
        if type(self.index.counter) is not TokenCounter or RetrievalFeatures.parse(settings.get('features')) != RetrievalFeatures():
            return
        vector = self.index._cache.get((p.id, query))
        if vector is None:
            return
        candidate = next((c for c in self.candidates if c.workload == key.workload
                          and not self.store.quarantined(key, c.provider)), None)
        if candidate is None:
            return
        task_settings = {k: v for k, v in settings.items() if k in ('mode', 'budget', 'candidate_limit', 'neighbor_turns')}
        task = {'operation': 'replay', 'db': str(self.index.path), 'scope': scope, 'query': query,
                'generation': generation, 'query_vector': list(vector), 'embedding_profile': asdict(p),
                'model_id': self.model_id, 'counter': self.index.counter.name, 'settings': task_settings,
                'candidate_id': candidate.id, 'provider': candidate.provider, 'device': candidate.device,
                'key': key.id, 'memory_budget': self.memory_budget, 'repeats': 5}
        self.explorer.submit(task, lambda result: self._publish(key, candidate, result),
                             estimated_io=count*max(1, p.dimension)*4)

    def _publish(self, key, candidate, result):
        if result.get('key') != key.id or result.get('candidate_id') != candidate.id:
            return
        semantic = SemanticGuard.compare(result['reference'], result['result'])['semantic_admission']
        gain = self.gate.evaluate(result['baseline'], result['candidate'], semantic=semantic,
                                  resources={'ram': result['memory_bytes']}, limits={'ram': self.memory_budget})
        values = result['candidate']
        from .optimizer import percentile
        import statistics
        measurement = {'p50': statistics.median(values), 'p95': percentile(values, .95), 'p99': percentile(values, .99),
                       'throughput': 1000/statistics.median(values), 'ram': result['memory_bytes'],
                       'sample_count': len(values), 'noise': gain.get('noise_floor', 0)}
        with self.lock:
            if self.closed:
                return
            self.store.put(key, candidate.id, measurement, semantic_status='strict' if semantic else 'rejected',
                           material_gain=gain['decision'], pareto=gain['materially_faster'])
            self.decisions = (self.decisions + [{'candidate': candidate.id, **gain}])[-32:]
            if not semantic:
                self.store.failure(key, candidate.provider, 'semantic')
            if gain['materially_faster']:
                self.gate.switched()

    def explain(self):
        return {'mode': 'zero-touch', 'semantic_policy': self.policy, 'bootstrap': 'sparse-or-explicit-fp32-reference',
                'session_profile_pinning': True, 'providers': self.registry.list(), 'profiles': self.store.summary(),
                'decisions': list(self.decisions), 'shadow': dict(self.explorer.last_receipt),
                'generation_calls': 0, 'user_benchmark_required': False}

    def close(self):
        with self.lock:
            self.closed = True
        self.explorer.close()
        for executor in self.executors.values():
            executor.close()
        self.registry.close(); self.store.close()
