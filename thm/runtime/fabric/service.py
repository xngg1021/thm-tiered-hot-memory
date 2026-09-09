"""Product runtime: safe first request, passive observations, bounded idle replay."""
from dataclasses import asdict
from pathlib import Path
import threading
import time
from .contracts import IndexIdentity, RuntimeSample, identity
from .explorer import BoundedShadowExplorer
from .hardware import HostDeviceProvider
from .indexes import ResidentHandleManager
from .optimizer import Candidate, CandidatePlanner, MaterialGainGate, PassiveTelemetry, PolicySelector, SemanticGuard
from .registry import builtin_registry
from .store import ProfileKey, ProfileStore, scale_bucket


class ResidentExecutor:
    def __init__(self, registry, provider='host.exact', device='cpu', memory_budget=256*1024**2):
        self.registry = registry; self.provider_id = provider; self.device = device
        self.manager = ResidentHandleManager({device: memory_budget}); self.last = {}
        self.description = registry.describe(provider)

    def search(self, *, scope, generation, embedding_profile, ids, matrix, queries, top_k, placement='dram'):
        provider = self.registry.get(self.provider_id)
        description = self.description
        key = IndexIdentity(scope, generation, embedding_profile, self.provider_id,
                            identity(description['versions']), identity({'metric': 'inner_product'}),
                            device=self.device, placement=placement, runtime=identity(description))
        with self.manager.lock:
            self.manager.invalidate(scope=scope, generation=generation)
            hit = key.key in self.manager.handles
            if not hit:
                footprint = matrix.nbytes if hasattr(matrix, 'nbytes') else len(matrix)*len(matrix[0])*4
                if footprint > self.manager.budgets.get(self.device, 0):
                    raise MemoryError('replica does not fit before allocation')
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
        self.store_state = 'persistent'
        try:
            self.store = ProfileStore(store_path or index.path.parent / ('runtime-'+identity(str(index.path))[:16]+'.sqlite'))
        except (OSError, ValueError, __import__('sqlite3').DatabaseError):
            self.store = ProfileStore(':memory:')
            self.store_state = 'volatile-safe-fallback'
        self.telemetry = PassiveTelemetry(); self.gate = MaterialGainGate()
        self.explorer = explorer or BoundedShadowExplorer(memory_bytes=memory_budget)
        self.background = background and policy != 'reference'; self.lock = threading.RLock()
        self.pinned = {}; self.session_pins = {}; self.executors = {}; self.decisions = []; self.closed = False
        self.candidates = [Candidate('host.exact', workload=w) for w in ('interactive', 'bulk', 'background')]
        self.provider_versions = identity(self.registry.describe('host.exact')['versions'])
        self.discovery = {}; self.discovery_cursor = 0; self.batchers = {}; self.discovery_done = False
        self.queue_lock = threading.RLock()
        self.encode_costs = []
        self.discovery_epoch = __import__('uuid').uuid4().hex
        from .models import ModelPortfolio
        self.models = ModelPortfolio(self)

    def submit(self, scope, query, *, workload='interactive', deadline=None, **settings):
        """Nonblocking online API. Compatible requests share one bounded queue."""
        from thm.features import RetrievalFeatures
        from .microbatch import DeadlineAwareMicrobatcher
        normalized = dict(settings)
        if 'features' in normalized:
            normalized['features'] = RetrievalFeatures.parse(normalized['features']).identity()
        group = identity({'scope': scope, 'workload': workload, 'settings': normalized})
        with self.queue_lock:
            if self.closed:
                raise RuntimeError('runtime service closed')
            if group not in self.batchers:
                if len(self.batchers) >= 8:
                    idle = next((k for k,b in self.batchers.items() if b.idle()), None)
                    if idle is None:
                        raise RuntimeError('bounded runtime queue groups busy')
                    self.batchers.pop(idle).close(wait=False)
                self.batchers[group] = DeadlineAwareMicrobatcher(
                    lambda queries: self._execute(scope, queries, workload=workload, **settings), max_batch=32)
            future = self.batchers[group].submit(query, deadline=deadline)
        # Receipt is attached before forwarding the completed result to callers.
        from concurrent.futures import Future
        output = Future()
        def finish(done):
            if not output.set_running_or_notify_cancel():
                return
            try:
                result, batch = done.result()
                result['runtime_receipt'].update(batch)
                result['runtime_receipt']['latency_ms'] = batch['queue_wait_ms'] + batch['compute_time_ms']
                receipt = result['runtime_receipt']; clocks = result.get('timing_ms', {})
                self.telemetry.observe(RuntimeSample(receipt['actual_provider'], workload, receipt['latency_ms'],
                    queue_wait_ms=batch['queue_wait_ms'], batch=batch['actual_batch'], cpu_seconds=receipt['cpu_seconds'],
                    encode_ms=clocks.get('query_embedding'), search_ms=clocks.get('dense_scoring'),
                    materialization_ms=clocks.get('row_materialization'), packing_ms=clocks.get('pack'),
                    fallback=bool(receipt['fallback']), semantic_policy=self.policy, profile_source=receipt['profile_source']))
                output.set_result(result)
            except Exception as exc:
                output.set_exception(exc)
        future.add_done_callback(finish)
        output.add_done_callback(lambda done: future.cancel() if done.cancelled() else None)
        return output

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
        from thm.physical.segments import current
        placement = current(self.index, scope, getattr(p, 'id', None)) if p is not None else None
        versions = identity({'host': self.provider_versions, 'discovered': self.discovery})
        key = ProfileKey(self.graph.fingerprint, self.graph.os+':'+self.graph.build, identity(self.discovery),
                         identity(versions), getattr(p, 'source_manifest_sha256', 'none'),
                         getattr(p, 'derived_manifest_sha256', None) or 'none', getattr(p, 'dimension', 0),
                         getattr(p, 'precision', 'fp32'), identity({'generation': generation[0], 'profile': getattr(p, 'id', None)}),
                         scale_bucket(count, getattr(p, 'dimension', 0), self.memory_budget),
                         identity(settings), identity(placement) if placement else 'sqlite-local', workload, self.policy, self.implementation,
                         shape_bucket=identity({'scope': scope, 'fanout': settings.get('candidate_limit', 100)}))
        return key, generation[0], count

    def _select(self, key, workload):
        if key.id in self.pinned:
            return self.pinned[key.id]
        anchor = identity({k:v for k,v in asdict(key).items() if k not in ('hardware','driver','provider_version')})
        if anchor in self.session_pins:
            # New device observations may invalidate a choice, but cannot promote
            # a different provider within an already pinned logical session.
            prior_key, prior = self.session_pins[anchor]
            self.pinned[key.id] = prior if prior_key == key.id else None
            return self.pinned[key.id]
        classes = ('strict','approximate') if self.policy == 'approximate-performance' else ('strict',)
        accepted = {x['candidate']: x for x in self.store.observations(key)
                    if x['semantic_status'] in classes and x['material_gain_status'] == 'accepted' and x['pareto']}
        points = []; states = {'slo_ms': 100 if workload == 'interactive' else float('inf')}
        for c in self.candidates:
            row = accepted.get(identity(c.id))
            if row and not self.store.quarantined(key, c.provider) and SemanticGuard.eligible(c, self.policy):
                points.append({'id': c.id, 'workload': workload, 'semantic_safe': True, 'semantic_class': row['semantic_status'], **row['measurement']})
                executor = self.executors.get(c.id)
                resident = bool(executor and executor.manager.handles)
                states[c.id] = {'queue_depth': sum(len(b.queue) for b in self.batchers.values()),
                    'concurrency': 1, 'model_warm': True, 'provider_ready': True,
                    'index_resident': resident, 'stage_ms': row['measurement'].get('startup')}
        selected = PolicySelector().select(points, workload, states)
        candidate = next((c for c in self.candidates if selected and c.id == selected['id']), None)
        if len(self.pinned) >= 128:
            self.pinned.pop(next(iter(self.pinned)))
        if len(self.session_pins) >= 128:
            self.session_pins.pop(next(iter(self.session_pins)))
        self.pinned[key.id] = candidate
        self.session_pins[anchor] = (key.id, candidate)
        return candidate

    def new_session(self):
        with self.lock:
            self.pinned.clear(); self.session_pins.clear()
            self.models.new_session()
            return {'reason': 'explicit-new-session', 'profile_migration': 'eligible-stored-point', 'semantic_policy': self.policy}

    def search(self, scope, query, *, workload='interactive', **settings):
        return self.submit(scope, query, workload=workload, **settings).result()

    def _execute(self, scope, queries, *, workload='interactive', **settings):
        start = time.perf_counter(); cpu = time.process_time()
        # Hold the derived index lock across plan construction and execution.
        # External SQLite writers are detected by the returned generation below.
        with self.lock, self.index._lock:
            if self.closed:
                raise RuntimeError('runtime service closed')
            if any(k in settings for k in ('encoder', 'model_id', 'scorer')):
                raise ValueError('runtime owns execution settings')
            mode = settings.get('mode', 'sparse')
            boot = SafeBootstrapPolicy().select(mode=mode, encoder=self.encoder)
            effective = {**settings, 'mode': boot['mode']}
            key, generation, count = self._key(scope, workload, effective)
            model_point = self.models.select(key) if self.policy != 'reference' and boot['mode'] in ('dense','hybrid') else None
            candidate = self._select(key, workload) if not model_point and self.policy != 'reference' and boot['mode'] in ('dense', 'hybrid') else None
            model_output = None
            provider = model_point[2].inference_provider if model_point else candidate.provider if candidate else 'reference'
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
                if model_point:
                    model_output = model_point[1].search(queries,generation)
                    results = model_output['results']
                elif len(queries) == 1:
                    results = [self.index.search(scope, queries[0], encoder=self.encoder, model_id=self.model_id, **effective)]
                else:
                    results = self.index.search_many(scope, queries, encoder=self.encoder, model_id=self.model_id,
                        query_batch_size=len(queries), semantic_guard=self.policy != 'approximate-performance', **effective)
            except Exception as exc:
                if model_point:
                    self.models.fail(key,model_point[2]); model_point = None; model_output = None
                elif not candidate:
                    raise
                self.store.failure(key, provider, 'execution')
                self.index._vector_executor = None; self.index._results.clear()
                results = [self.index.search(scope, q, encoder=self.encoder, model_id=self.model_id, **effective) for q in queries]
                self.pinned[key.id] = None; fallback = 'provider-failed:' + type(exc).__name__
                candidate = None; provider = 'reference'
                plan = JointComputeDataPlanner().plan(self.index, scope,
                    embedding_profile=getattr(getattr(self.encoder, 'profile', None), 'id', None),
                    workload=workload, policy=self.policy)
            finally:
                self.index._vector_executor = None
            try:
                JointComputeDataPlanner().validate(plan, self.index, scope)
                plan_stale = False
            except ValueError:
                plan_stale = True
            if plan_stale or any(r['generation'] != generation for r in results):
                # Replan once on the new snapshot; the old observation cannot be
                # published under the new source generation.
                self.pinned.pop(key.id, None)
                key, generation, count = self._key(scope, workload, effective)
                plan = JointComputeDataPlanner().plan(self.index, scope,
                    embedding_profile=getattr(getattr(self.encoder, 'profile', None), 'id', None), workload=workload, policy=self.policy)
                results = [self.index.search(scope, q, encoder=self.encoder, model_id=self.model_id, **effective) for q in queries]
                if any(r['generation'] != generation for r in results):
                    raise RuntimeError('source generation changed repeatedly')
                fallback = 'generation-replan'; candidate = None; model_point = None; model_output = None; provider = 'reference'
            elapsed = (time.perf_counter()-start)*1000
            result = results[0]
            receipt = {'schema': 2, 'evidence_layer': 'systems-runtime',
                'hardware_fingerprint': self.graph.fingerprint, 'provider': provider,
                'actual_provider': 'reference' if fallback and candidate else provider,
                'device': model_output['embedding_profile']['device'] if model_output else candidate.device if candidate and not fallback else 'cpu',
                'embedding_profile': getattr(getattr(self.encoder, 'profile', None), 'id', None),
                'inference_provider': provider if model_point else 'reference',
                'authority_embedding_profile': getattr(getattr(self.encoder, 'profile', None), 'id', None),
                'index_provider': 'numpy_reference' if model_point else provider, 'physical_placement': plan.current_placement, 'semantic_policy': self.policy,
                'semantic_class': candidate.semantic_class if candidate else 'strict',
                'quality_evidence_scope': 'observed-request-only' if candidate or model_point else 'reference',
                'profile_source': 'stored' if candidate or model_point else 'bootstrap', 'profile_freshness': 'fresh',
                'profile_key': key.id, 'batch_policy': 'deadline-aware-opportunity',
                'latency_ms': elapsed, 'fallback': fallback, 'generation_calls': 0,
                'cpu_seconds': (time.process_time()-cpu+(model_output or {}).get('cpu_seconds',0))/len(queries), 'cpu_accounting': 'process-amortized',
                'query_embedding_batch': 1, 'vector_search_batch': len(queries) if not model_point and boot['mode'] in ('dense','hybrid') else 1,
                'memory_quality_improved': None, 'observed_kernel_dispatch': None}
            if model_output:
                receipt['embedding_profile'] = model_output['embedding_profile']['embedding_profile_id']
            for result in results:
                result['execution_plan'] = plan.receipt()
                if model_point:
                    result['execution_plan'].update(inference_provider=provider, vector_index_provider='numpy_reference',
                        embedding_profile=receipt['embedding_profile'], source_representation='private-profile-replica',
                        target_residency='isolated-worker', device=receipt['device'])
                    result['execution_plan']['plan_id'] = identity({k:v for k,v in result['execution_plan'].items() if k != 'plan_id'})
                result['runtime_receipt'] = dict(receipt)
                if not result.get('query_embedding_cache_hit'):
                    self.encode_costs = (self.encode_costs + [result.get('timing_ms', {}).get('query_embedding', 0)])[-64:]
            self._maybe_explore(key, generation, count, scope, queries[0], effective)
            return results

    def _maybe_explore(self, key, generation, count, scope, query, settings):
        p = getattr(self.encoder, 'profile', None)
        if self.models.preparing:
            return
        if not self.background or p is None or settings.get('mode') not in ('dense', 'hybrid'):
            return
        with self.queue_lock:
            if any(b.queue for b in self.batchers.values()):
                return
        pressure = HostDeviceProvider.pressure()
        if any(pressure.values()):
            return
        if not self.discovery_done:
            self.explorer.submit({'operation': 'discover', 'cursor': self.discovery_cursor}, self._discovered)
            return
        # Custom token counters and retrieval feature experiments are not replayed.
        from thm.retrieval import TokenCounter
        from thm.features import RetrievalFeatures
        if type(self.index.counter) is not TokenCounter or RetrievalFeatures.parse(settings.get('features')) != RetrievalFeatures():
            return
        vector = self.index._cache.get((p.id, query))
        if vector is None:
            return
        task_settings = {k: v for k, v in settings.items() if k in ('mode', 'budget', 'candidate_limit', 'neighbor_turns')}
        if self.models.maybe_start(key, {'db':str(self.index.path), 'scope':scope, 'generation':generation,
                'query':query, 'counter':self.index.counter.name, 'settings':task_settings}):
            return
        planned = CandidatePlanner().plan(self.candidates, workload=key.workload, policy=self.policy,
            required_bytes=count*p.dimension*4, memory_budget={c.device: self.memory_budget for c in self.candidates},
            observations=self.store.observations(key), limit=2)
        candidates = [c for c in planned if not self.store.quarantined(key, c.provider)]
        candidate = candidates[len(self.decisions) % len(candidates)] if candidates else None
        if candidate is None:
            return
        task_settings = {k: v for k, v in settings.items() if k in ('mode', 'budget', 'candidate_limit', 'neighbor_turns')}
        task = {'operation': 'replay', 'db': str(self.index.path), 'scope': scope, 'query': query,
                'generation': generation, 'query_vector': list(vector), 'embedding_profile': asdict(p),
                'model_id': self.model_id, 'counter': self.index.counter.name, 'settings': task_settings,
                'candidate_id': candidate.id, 'provider': candidate.provider, 'device': candidate.device,
                'key': key.id, 'memory_budget': self.memory_budget, 'repeats': 5,
                'observed_encode_floor_ms': max(self.encode_costs, default=0)}
        self.explorer.submit(task, lambda result: self._publish(key, candidate, result),
                             estimated_io=count*max(1, p.dimension)*4, gpu=candidate.device != 'cpu')

    def _discovered(self, result):
        """Publish only sanitized, observed runtime facts from the private child."""
        from .hardware import DeviceNode
        with self.lock:
            if self.closed:
                return
            if result.get('status') == 'deferred':
                self.discovery_cursor = (result.get('cursor') or 0)+1
                return
            self.discovery_cursor = result.get('next_cursor', 0)
            self.discovery_done = result.get('done', False)
            for row in result.get('providers', ()):
                name = row['provider']
                description = self.registry.describe(name)
                self.discovery[name] = {k: row.get(k) for k in ('availability', 'version', 'driver_runtime', 'devices')}
                native = row.get('driver_runtime')
                known_driver = native.get('driver') if isinstance(native, dict) else native
                if name != 'host.hnsw' and not known_driver:
                    self.discovery[name]['freshness_epoch'] = self.discovery_epoch
                self.models.add(name, description, row)
                if row.get('availability') != 'available':
                    continue
                device = dict(description['options']).get('device')
                exact = name.endswith('.exact') or name in ('nvidia.cuvs.brute_force','metax.mcfaiss','nvidia.cublaslt')
                approximate = name == 'host.hnsw' or name.startswith('nvidia.cuvs.') and not exact
                if not exact and not approximate:
                    continue
                if approximate and self.policy != 'approximate-performance':
                    continue
                device = device or ('cpu' if name == 'host.hnsw' else (row.get('devices') or ['cuda'])[0])
                self.graph.nodes.append(DeviceNode('provider:'+name, 'npu' if device == 'npu' else 'gpu',
                    True, True, True, {'vendor': description['vendor'], 'runtime': row.get('version'),
                                      'driver': row.get('driver_runtime'), 'vram_total': row.get('memory_bytes')}))
                self.graph.edges.append(('provider:'+name, 'dram', 'explicit-copy'))
                for workload in ('interactive', 'bulk', 'background'):
                    self.candidates.append(Candidate(name, device=device, placement='dram' if device == 'cpu' else 'device-memory',
                        transfer=description['vendor']+'.transfer', workload=workload,
                        index='exact-flat' if exact else name.split('.')[-1], semantic_class='strict' if exact else 'approximate'))

    def _publish(self, key, candidate, result):
        if result.get('key') != key.id or result.get('candidate_id') != candidate.id:
            return
        if result.get('status') == 'deferred':
            with self.lock:
                if not self.closed:
                    self.store.failure(key, candidate.provider, 'timeout')
            return
        semantic = SemanticGuard.compare(result['reference'], result['result'], dimension=key.dimension)['semantic_admission'] and result.get('all_repeats_consistent',True)
        approximate = self.policy == 'approximate-performance' and candidate.semantic_class == 'approximate'
        import statistics
        cpu_samples = result.get('cpu_samples', {})
        cpu_candidate = statistics.median(cpu_samples['candidate']) if cpu_samples.get('candidate') else None
        cpu_baseline = statistics.median(cpu_samples['baseline']) if cpu_samples.get('baseline') else None
        resource_limits = {'ram': self.memory_budget}
        if cpu_baseline is not None:
            resource_limits['cpu_seconds'] = max(cpu_baseline*1.25, cpu_baseline+.001)
        gain = self.gate.evaluate(result['baseline'], result['candidate'], semantic=semantic or approximate,
                                  resources={'ram': result['memory_bytes'], 'cpu_seconds': cpu_candidate}, limits=resource_limits)
        values = result['candidate']
        from .optimizer import percentile
        import statistics
        measurement = {'p50': statistics.median(values), 'p95': percentile(values, .95), 'p99': percentile(values, .99),
                       'throughput': 1000/statistics.median(values), 'ram': result['memory_bytes'],
                       'sample_count': len(values), 'noise': gain.get('noise_floor', 0),
                       'cpu_seconds': cpu_candidate, 'startup': result.get('startup_ms'),
                       'transfer': result.get('host_device_bytes')}
        if approximate:
            from .indexes import ann_quality
            quality = ann_quality(result['reference']['ranked_ids'], result['result']['ranked_ids'])
            measurement.update({k: v for k,v in quality.items() if v is not None})
            measurement['packed_context_changed'] = int(result['reference']['context'] != result['result']['context'])
        with self.lock:
            if self.closed:
                return
            self.store.put(key, candidate.id, measurement, semantic_status='approximate' if approximate else 'strict' if semantic else 'rejected',
                           material_gain=gain['decision'], pareto=gain['materially_faster'],
                           evidence={'sample_kind': result.get('sample_kind'),
                                     'observed_encode_floor_ms': result.get('observed_encode_floor_ms', 0),
                                     'semantic_scope': 'observed-request-only'})
            self.decisions = (self.decisions + [{'candidate': candidate.id, **gain}])[-32:]
            if not semantic and not approximate:
                self.store.failure(key, candidate.provider, 'semantic')
            if gain['materially_faster']:
                self.gate.switched()

    def explain(self):
        return {'mode': 'zero-touch', 'semantic_policy': self.policy, 'bootstrap': 'sparse-or-explicit-fp32-reference',
                'session_profile_pinning': True, 'providers': self.registry.list(), 'profiles': self.store.summary(), 'profile_store_state': self.store_state,
                'decisions': list(self.decisions), 'shadow': dict(self.explorer.last_receipt),
                'provider_discovery': dict(self.discovery), 'discovery_complete': self.discovery_done,
                'model_optimization': dict(self.models.last),
                'generation_calls': 0, 'user_benchmark_required': False}

    def status(self):
        with self.lock:
            return {'schema': 2, 'mode': 'zero-touch', 'semantic_policy': self.policy,
                    'hardware_fingerprint': self.graph.fingerprint, 'profile_store_state': self.store_state,
                    'profiles': self.store.summary(), 'discovery_complete': self.discovery_done,
                    'session_profiles': [{'key': key, 'provider': c.provider if c else 'reference'} for key,c in self.pinned.items()],
                    'shadow': dict(self.explorer.last_receipt), 'model_optimization': dict(self.models.last),
                    'generation_calls': 0, 'user_benchmark_required': False}

    def close(self):
        with self.queue_lock:
            self.closed = True
        for batcher in self.batchers.values():
            batcher.close()
        self.explorer.close(); self.models.close()
        for executor in self.executors.values():
            executor.close()
        self.registry.close(); self.store.close()
