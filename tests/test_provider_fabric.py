"""Execution fabric regressions: deterministic evidence, no vendor hardware claims."""
from dataclasses import asdict, replace
from pathlib import Path
import contextlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from thm.retrieval import Document, SearchIndex, TokenCounter
from thm.runtime.fabric.contracts import IndexIdentity, ProviderSpec, RuntimeSample, identity
from thm.runtime.fabric.hardware import HardwareGraph, HostDeviceProvider
from thm.runtime.fabric.registry import ProviderRegistry, ProviderUnavailable, builtin_registry
from thm.runtime.fabric.store import CompiledArtifactStore, ProfileKey, ProfileStore, scale_bucket
from thm.runtime.fabric.optimizer import Candidate, MaterialGainGate, ParetoFrontier, PassiveTelemetry, PolicySelector, SemanticGuard
from thm.runtime.fabric.indexes import ExactHost, ResidentHandleManager, VectorIndexHandle, ann_quality
from thm.runtime.fabric.microbatch import DeadlineAwareMicrobatcher
from thm.runtime.fabric.service import RuntimeService, ResidentExecutor, SafeBootstrapPolicy
from thm.runtime.fabric.explorer import BoundedShadowExplorer


def key(**changes):
    fields = dict(hardware='h', os_build='os', driver='d', provider_version='v', model_source='m',
                  model_artifact='a', dimension=4, precision='fp32', index_implementation='i',
                  corpus_bucket='tiny', index_config='c', placement='dram', workload='interactive',
                  semantic_policy='auto-safe', semantic_implementation='s')
    fields.update(changes)
    return ProfileKey(**fields)


def index_identity(**changes):
    fields = dict(scope='scope', generation='g1', embedding_profile='ep', provider='host.exact',
                  provider_version='1', index_config='c')
    fields.update(changes)
    return IndexIdentity(**fields)


def documents(n=8):
    return [Document(str(i), 'scope', 'session', i, 'Alice went to Beijing ' + str(i),
                     speaker='Alice' if i % 2 else 'Bob', source='file:fixture') for i in range(n)]


class RegistryTests(unittest.TestCase):
    def test_lazy_optional_imports(self):
        before = set(sys.modules)
        registry = builtin_registry(extensions=False)
        registry.list()
        self.assertFalse({'torch', 'onnxruntime', 'openvino', 'torch_npu', 'torch_mlu', 'torch_musa'} & (set(sys.modules)-before))

    def test_duplicate_and_priority(self):
        registry = ProviderRegistry()
        a = ProviderSpec('a', 'fixture', 'host', 'thm.runtime.fabric.hardware:HostDeviceProvider', priority=1)
        registry.register(a)
        with self.assertRaises(ValueError):
            registry.register(a)
        registry.register(replace(a, provider_id='b', priority=2))
        self.assertEqual([s['provider_id'] for s in registry.list()], ['b', 'a'])

    def test_bad_provider_isolated(self):
        registry = ProviderRegistry()
        registry.register(ProviderSpec('bad', 'fixture', 'bad', 'not_a_thm_module:Nothing'))
        registry.register(ProviderSpec('good', 'host', 'host', 'thm.runtime.fabric.hardware:HostDeviceProvider'))
        with self.assertRaises(ProviderUnavailable):
            registry.get('bad')
        self.assertTrue(registry.get('good').discover().available('cpu'))

    def test_untrusted_entrypoint_requires_explicit_load(self):
        registry = ProviderRegistry()
        registry.register(ProviderSpec('extension', 'x', 'x', 'thm.runtime.fabric.hardware:HostDeviceProvider', validation_state='untrusted-unvalidated'))
        with self.assertRaises(ProviderUnavailable):
            registry.get('extension')
        self.assertIsNotNone(registry.get('extension', allow_untrusted=True))

    def test_catalog_vendor_coverage(self):
        rows = builtin_registry(extensions=False).list()
        for vendor in ('nvidia', 'amd', 'intel', 'apple', 'qualcomm', 'ascend', 'musa', 'cambricon', 'metax', 'microsoft'):
            self.assertTrue(any(r['vendor'] == vendor for r in rows), vendor)
        self.assertTrue(all(r['maturity'] < 5 and r['validation_state'] == 'hardware-unvalidated' for r in rows))

    def test_missing_dependency_does_not_remove_core(self):
        registry = builtin_registry(extensions=False)
        with mock.patch('thm.runtime.fabric.registry.metadata.version', side_effect=__import__('importlib.metadata').metadata.PackageNotFoundError):
            self.assertEqual(registry.describe('host.exact')['availability'], 'dependency-missing')
            self.assertNotEqual(registry.describe('host.device')['availability'], 'dependency-missing')


class GraphTests(unittest.TestCase):
    def test_visibility_is_not_availability(self):
        graph = HardwareGraph.from_profile({'os': 'Linux', 'architecture': 'x86', 'os_visible_cpus': 64,
            'installed_logical_cpus': 128, 'process_available_cpus': 2, 'cpu_affinity': [3,4],
            'numa_nodes': {'n0': [0,1], 'n1': [3,4]}, 'accelerators': [{'driver': '1'}]})
        self.assertEqual(graph.available('cpu')[0].properties['available_count'], 2)
        self.assertFalse(graph.available('gpu'))
        self.assertEqual(len(graph.available('numa')), 1)

    def test_unknowns_stay_unknown(self):
        graph = HardwareGraph.from_profile({'os': 'Darwin', 'architecture': 'arm64'})
        self.assertIsNone(graph.nodes[0].process_available)
        self.assertIsNone(graph.nodes[1].properties['unified'])

    def test_bootstrap_never_launches_probe_subprocess(self):
        with mock.patch('subprocess.run', side_effect=AssertionError('slow probe')):
            HostDeviceProvider().discover()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = ProfileStore(Path(self.temp.name)/'profiles.db'); self.addCleanup(self.store.close)

    def put(self, k=None):
        self.store.put(k or key(), 'candidate', {'p95': 10, 'sample_count': 7}, semantic_status='strict', material_gain='accepted', pareto=True)

    def test_persistent_exact_fingerprint(self):
        self.put()
        second = ProfileStore(self.store.path)
        try:
            self.assertEqual(len(second.observations(key())), 1)
        finally:
            second.close()

    def test_every_critical_key_component_invalidates(self):
        self.put()
        for field in ('hardware','os_build','driver','provider_version','model_source','model_artifact','index_implementation','corpus_bucket','index_config','placement','semantic_implementation','shape_bucket'):
            self.assertEqual(self.store.observations(replace(key(), **{field:'changed'})), [], field)
        self.assertEqual(self.store.observations(replace(key(), workload='bulk')), [])

    def test_profile_privacy(self):
        k = key(model_source='/private/secret/model', hardware='serial-123')
        self.put(k)
        raw = self.store.path.read_bytes()
        self.assertNotIn(b'/private/secret/model', raw)
        self.assertNotIn(b'serial-123', raw)
        with self.assertRaises(ValueError):
            self.store.put(k, 'c', {'text': 'secret'}, semantic_status='strict', material_gain='accepted')

    def test_corrupt_row_fails_closed(self):
        self.put()
        with self.store.db:
            self.store.db.execute("UPDATE observations SET payload='{}'")
        self.assertEqual(self.store.observations(key()), [])

    def test_invalidation_marker(self):
        self.put(); self.store.invalidate(key())
        self.assertEqual(self.store.observations(key()), [])

    def test_quarantine_expiry_and_new_driver(self):
        now = [10]
        self.store.clock = lambda: now[0]
        self.store.failure(key(), 'p', 'oom', cooldown=5)
        self.assertTrue(self.store.quarantined(key(), 'p'))
        self.assertFalse(self.store.quarantined(replace(key(), driver='new'), 'p'))
        now[0] = 16
        self.assertFalse(self.store.quarantined(key(), 'p'))

    def test_scale_responds_to_memory_fit(self):
        self.assertNotEqual(scale_bucket(10000, 384, 2**20), scale_bucket(10000, 384, 2**30))

    def test_artifact_atomic_identity_and_corruption(self):
        artifacts = CompiledArtifactStore(Path(self.temp.name)/'artifacts')
        deps = {k:'value' for k in artifacts.REQUIRED}
        artifacts.publish(deps, b'compiled')
        self.assertEqual(artifacts.load(deps), b'compiled')
        self.assertIsNone(artifacts.load({**deps, 'driver_runtime':'new'}))
        with self.assertRaises(ValueError):
            artifacts.publish(deps, b'different')
        path = next(artifacts.root.glob('*.artifact')); path.write_bytes(b'{}\nbroken')
        with self.assertRaises(ValueError):
            artifacts.load(deps)


class OptimizerTests(unittest.TestCase):
    def test_one_percent_jitter_not_optimized(self):
        result = MaterialGainGate().evaluate([100,99,101,100,100], [99,100,98,99,99])
        self.assertTrue(result['measured_faster'])
        self.assertFalse(result['materially_faster'])

    def test_historical_trivial_gain_rejected(self):
        result = MaterialGainGate().evaluate([26.08]*5, [25.63]*5)
        self.assertFalse(result['materially_faster'])

    def test_stable_large_gain_and_hysteresis(self):
        now = [0]
        gate = MaterialGainGate(clock=lambda: now[0])
        self.assertTrue(gate.evaluate([100]*5, [70]*5)['materially_faster'])
        gate.switched()
        self.assertFalse(gate.evaluate([100]*5, [70]*5)['materially_faster'])
        now[0] = 61
        self.assertTrue(gate.evaluate([100]*5, [70]*5)['materially_faster'])

    def test_semantic_or_resource_failure_rejects(self):
        gate = MaterialGainGate()
        self.assertFalse(gate.evaluate([100]*5, [30]*5, semantic=False)['materially_faster'])
        self.assertFalse(gate.evaluate([100]*5, [30]*5, resources={'ram':200}, limits={'ram':100})['materially_faster'])
        self.assertFalse(gate.evaluate([100]*5, [30]*5, limits={'ram':100})['materially_faster'])

    def test_ann_and_precision_cannot_enter_safe(self):
        for candidate in (Candidate('ann', index='hnsw', semantic_class='approximate'), Candidate('fp16', precision='fp16')):
            self.assertFalse(SemanticGuard.eligible(candidate, 'auto-safe'))
            self.assertFalse(SemanticGuard.eligible(candidate, 'reference'))
            self.assertTrue(SemanticGuard.eligible(candidate, 'approximate-performance'))

    def test_pareto_preserves_tradeoffs_and_workload(self):
        a = dict(id='a', workload='interactive', semantic_safe=True, semantic_class='strict', p95=10, ram=100, throughput=10)
        b = {**a,'id':'b','p95':11,'ram':110,'throughput':9}
        c = {**a,'id':'c','p95':8,'ram':120}
        other = {**a,'id':'bulk','workload':'bulk','p95':1}
        self.assertEqual([x['id'] for x in ParetoFrontier().build([a,b,c,other])], ['a','c'])
        self.assertEqual([x['id'] for x in ParetoFrontier().build([a,b,c],constraints={'ram':105})], ['a'])

    def test_unknown_metrics_do_not_dominate(self):
        a = dict(workload='interactive', semantic_class='strict', p95=1, ram=None)
        b = {**a,'p95':2,'ram':100}
        self.assertFalse(ParetoFrontier.dominates(a,b))

    def test_cost_model_includes_queue_stage_and_compile(self):
        prediction = PolicySelector().predict({'p95':10,'startup':30,'compile':100},
                    {'queue_depth':2,'concurrency':1,'model_warm':False,'provider_ready':False,'index_resident':False,'stage_ms':20})
        self.assertEqual(prediction, 180)

    def test_telemetry_resource_cost_is_measured(self):
        telemetry = PassiveTelemetry()
        for _ in range(5):
            telemetry.observe(RuntimeSample('a','interactive',10,cpu_seconds=.03,requested_threads=1))
        summary = telemetry.summary('a','interactive')
        self.assertEqual(summary['cpu_seconds'], .03)
        self.assertIsNone(summary['energy'])
        self.assertIsNone(summary['gpu_seconds'])


class HandleTests(unittest.TestCase):
    def test_exact_stable_ties_and_replica_ownership(self):
        import numpy as np
        source = np.array([[1,0],[1,0],[0,1]], dtype=np.float32)
        provider = ExactHost(); handle = provider.build(source, [1,2,3], index_identity())
        source[0] = [0,0]
        rows, receipt = provider.search(handle, [[1,0]], 2)
        self.assertEqual(rows[0][0], [1,2])
        self.assertEqual(receipt['host_device_bytes'], 0)

    def test_reuse_and_generation_identity(self):
        registry = builtin_registry(extensions=False); executor = ResidentExecutor(registry)
        try:
            kw = dict(scope='s',generation='g',embedding_profile='p',ids=[1,2],matrix=[[1,0],[0,1]],queries=[[1,0]],top_k=1)
            _, first = executor.search(**kw); _, second = executor.search(**kw)
            self.assertFalse(first['resident_hit']); self.assertTrue(second['resident_hit'])
            _, changed = executor.search(**{**kw,'generation':'g2'})
            self.assertFalse(changed['resident_hit'])
            self.assertEqual(len(executor.manager.handles),1)
        finally:
            executor.close(); registry.close()

    def test_inflight_eviction_deferred(self):
        manager = ResidentHandleManager({'cpu':100})
        handle = VectorIndexHandle(index_identity(),(1,),object(),80)
        manager.publish(handle,current_generation='g1')
        with manager.acquire(handle.identity):
            manager.invalidate(scope='scope',generation='g2')
            self.assertIsNotNone(handle.data)
            with self.assertRaises(KeyError):
                with manager.acquire(handle.identity):
                    pass
        self.assertIsNone(handle.data)

    def test_oom_does_not_replace_live_handle(self):
        manager = ResidentHandleManager({'cpu':100})
        h = VectorIndexHandle(index_identity(),(1,),object(),80)
        manager.publish(h,current_generation='g1')
        with manager.acquire(h.identity):
            with self.assertRaises(MemoryError):
                manager.publish(VectorIndexHandle(index_identity(generation='g2'),(1,),object(),80),current_generation='g2')
            self.assertIsNotNone(h.data)

    def test_ann_quality_separate(self):
        result = ann_quality([1,2,3],[1,3,4])
        self.assertAlmostEqual(result['recall_against_exact'],2/3)
        self.assertIsNone(result['context_quality_delta'])


class MicrobatchTests(unittest.TestCase):
    def test_low_arrival_immediate_one(self):
        batcher = DeadlineAwareMicrobatcher(lambda xs: xs,max_wait_ms=50)
        try:
            value, receipt = batcher.submit('x').result(timeout=1)
            self.assertEqual(value,'x'); self.assertEqual(receipt['actual_batch'],1)
            self.assertLess(receipt['queue_wait_ms'],40)
        finally:
            batcher.close()

    def test_high_arrival_grows_and_no_starvation(self):
        batcher = DeadlineAwareMicrobatcher(lambda xs: xs,max_wait_ms=10,max_batch=8,slo_ms=1000)
        try:
            with batcher.condition:
                futures = [batcher.submit(i) for i in range(16)]
            results = [future.result(timeout=2) for future in futures]
            self.assertEqual([x[0] for x in results],list(range(16)))
            self.assertTrue(any(x[1]['actual_batch'] > 1 for x in results))
            self.assertTrue(all(x[1]['queue_wait_ms'] < 1000 for x in results))
        finally:
            batcher.close()

    def test_expired_request_does_not_execute(self):
        execute = mock.Mock(return_value=[])
        batcher = DeadlineAwareMicrobatcher(execute)
        try:
            with self.assertRaises(TimeoutError):
                batcher.submit('x',deadline=time.monotonic()-1).result(timeout=1)
            execute.assert_not_called()
        finally:
            batcher.close()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.index = SearchIndex(Path(self.temp.name)/'index.db'); self.addCleanup(self.index.close)
        self.index.replace_scope('scope',documents())

    def test_idle_queue_groups_recycle_after_many_settings(self):
        service = RuntimeService(self.index, background=False)
        try:
            for budget in range(100, 116):
                self.assertLessEqual(service.search('scope','Beijing',budget=budget)['budget_used'],budget)
            self.assertLessEqual(len(service.batchers),8)
        finally:
            service.close()

    def test_new_discovery_does_not_promote_inside_session(self):
        service = RuntimeService(self.index, background=False)
        try:
            original, _, _ = service._key('scope','interactive',{'mode':'dense'})
            self.assertIsNone(service._select(original,'interactive'))
            changed = replace(original,driver='new-driver',provider_version='new-provider',hardware='new-hardware')
            candidate = service.candidates[0]
            service.store.put(changed,candidate.id,{'p50':1,'p95':1,'startup':1},
                semantic_status='strict',material_gain='accepted',pareto=True)
            self.assertIsNone(service._select(changed,'interactive'))
            service.new_session()
            self.assertEqual(service._select(changed,'interactive'),candidate)
        finally:
            service.close()

    def test_cold_staging_can_exceed_interactive_slo(self):
        service = RuntimeService(self.index, background=False)
        try:
            profile, _, _ = service._key('scope','interactive',{'mode':'dense'})
            candidate = service.candidates[0]
            service.store.put(profile,candidate.id,{'p50':1,'p95':2,'startup':101},
                semantic_status='strict',material_gain='accepted',pareto=True)
            self.assertIsNone(service._select(profile,'interactive'))
        finally:
            service.close()

    def test_unknown_driver_prevents_cross_process_profile_reuse(self):
        service = RuntimeService(self.index, background=False)
        second = RuntimeService(self.index, background=False,store_path=':memory:')
        try:
            discovery = {'providers':[{'provider':'nvidia.exact','availability':'available',
                'devices':['cuda'],'version':'fixture','driver_runtime':{'driver':None,'runtime':{'cuda':'fixture'}}}]}
            service._discovered(discovery); second._discovered(discovery)
            left, _, _ = service._key('scope','interactive',{})
            right, _, _ = second._key('scope','interactive',{})
            self.assertNotEqual(left.id,right.id)
        finally:
            service.close(); second.close()

    def test_unsupported_profile_schema_falls_back_without_overwrite(self):
        import sqlite3
        path = Path(self.temp.name)/'future.sqlite'
        db = sqlite3.connect(path); db.execute('PRAGMA user_version=99'); db.close()
        service = RuntimeService(self.index,background=False,store_path=path)
        try:
            self.assertEqual(service.store_state,'volatile-safe-fallback')
            self.assertTrue(service.search('scope','Beijing')['context'])
        finally:
            service.close()
        db = sqlite3.connect(path)
        try:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)
        finally:
            db.close()

    def test_first_request_never_runs_tuning(self):
        with mock.patch.object(BoundedShadowExplorer,'submit',side_effect=AssertionError('no sparse tuning')):
            service = RuntimeService(self.index)
            try:
                result = service.search('scope','Beijing',mode='sparse')
                self.assertTrue(result['context'])
                self.assertEqual(result['runtime_receipt']['profile_source'],'bootstrap')
                self.assertFalse(service.explain()['user_benchmark_required'])
            finally:
                service.close()

    def test_unready_dense_uses_explicit_sparse_receipt(self):
        service = RuntimeService(self.index)
        try:
            result = service.search('scope','Beijing',mode='hybrid')
            self.assertEqual(result['mode'],'sparse')
            self.assertEqual(result['runtime_receipt']['fallback'],'dense-reference-not-ready')
        finally:
            service.close()

    def test_foreground_pressure_prevents_shadow(self):
        explorer = BoundedShadowExplorer()
        self.assertFalse(explorer.eligible(foreground_pressure=.9))
        self.assertFalse(explorer.eligible(battery_low=True))
        self.assertTrue(explorer.eligible(gpu=True,gpu_duty_observed=False))
        explorer.wall = 10
        self.assertFalse(explorer.eligible(gpu=True,gpu_duty_observed=False))
        self.assertFalse(explorer.eligible(estimated_io=2**40))
        explorer.close()

    def test_real_bounded_shadow_probe(self):
        from thm.runtime.fabric.resources import ChildBudget
        import traceback
        accounting_errors = []
        check = ChildBudget.check
        def checked(budget):
            try:
                return check(budget)
            except Exception:
                accounting_errors.append(traceback.format_exc())
                raise
        explorer = BoundedShadowExplorer(wall_seconds=5)
        done = threading.Event(); results = []
        try:
            with mock.patch.object(ChildBudget, 'check', checked):
                self.assertTrue(explorer.submit({'operation':'probe','provider':'host.device'},lambda r:(results.append(r),done.set())))
                self.assertTrue(done.wait(6),explorer.last_receipt)
            self.assertIn('availability', results[0], {'callback': results[0], 'receipt': explorer.last_receipt,
                                                     'accounting_errors': accounting_errors})
            self.assertEqual(results[0]['availability'],'available')
        finally:
            explorer.close()

    def test_speaker_cache_and_generation_invalidation(self):
        trace = []; self.index.db.set_trace_callback(trace.append)
        self.index.search('scope','Alice Beijing')
        self.index.search('scope','Bob Beijing')
        self.assertEqual(sum('SELECT DISTINCT speaker' in x for x in trace),1)
        self.index.replace_scope('scope',[replace(d,speaker='Carol') for d in documents()])
        self.index.search('scope','Carol Beijing')
        self.assertEqual(sum('SELECT DISTINCT speaker' in x for x in trace),2)

    def test_neighbor_prefetch_has_exact_original_order(self):
        rows = self.index.rows('scope')
        actual = self.index._prefetch_neighbors('scope',rows,2)
        for row in rows:
            expected = [dict(r) for r in self.index.db.execute('SELECT * FROM docs WHERE scope=? AND session=? AND ord BETWEEN ? AND ? AND rowid!=? ORDER BY ABS(ord-?),ord,id',('scope',row['session'],row['ord']-2,row['ord']+2,row['rowid'],row['ord']))]
            self.assertEqual(actual[row['rowid']],expected)

    def test_row_cache_does_not_leak_mutation(self):
        generation = self.index.db.execute('SELECT generation FROM scopes').fetchone()[0]
        rowids = [x['rowid'] for x in self.index.rows('scope')]
        first = self.index._materialize('scope',generation,rowids)
        first[rowids[0]]['text'] = 'bad'
        second = self.index._materialize('scope',generation,rowids)
        self.assertNotEqual(second[rowids[0]]['text'],'bad')

    def test_custom_token_counter_keeps_exact_packing(self):
        def nonadditive(text):
            return len(text.replace(' ','').replace('\n\n',''))
        custom = SearchIndex(Path(self.temp.name)/'custom.db',nonadditive)
        try:
            custom.replace_scope('scope',documents())
            result = custom.search('scope','Beijing',budget=220,neighbor_turns=1)
            self.assertEqual(result['budget_used'],nonadditive(result['context']))
            self.assertLessEqual(result['budget_used'],220)
        finally:
            custom.close()


if __name__ == '__main__':
    unittest.main()


class DarwinBudgetTests(unittest.TestCase):
    def test_public_accounting_enforces_each_limit(self):
        from thm.runtime.fabric.resources import ChildBudget
        process = types.SimpleNamespace(pid=123)
        with mock.patch('thm.runtime.fabric.resources.os.name', 'posix'):
            budget = ChildBudget(process, memory=100, cpu=1, io=20)
        base = {'ram_bytes': 90, 'cpu_seconds': .5, 'bytes_read': 5, 'bytes_written': 3,
                'resource_source': 'darwin-proc-pid-rusage-v2-physical-io'}
        with mock.patch('thm.runtime.fabric.resources.sys.platform', 'darwin'):
            with mock.patch.object(budget, '_darwin_usage', return_value=base):
                budget.check()
                self.assertEqual(budget.last, base)
            for metric, value in [('ram_bytes',101),('cpu_seconds',1.1),('bytes_written',21)]:
                with mock.patch.object(budget, '_darwin_usage', return_value={**base, metric:value}):
                    with self.assertRaises(RuntimeError):
                        budget.check()
