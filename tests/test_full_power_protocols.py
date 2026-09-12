from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import numpy as np

from thm.economics_bridge import Measurement, EconomicAdvice, export_evidence, import_advice
from thm.evaluation.contracts import Task, GroundTruth, digest
from thm.evaluation.outcomes import AgentOutcome, attach_outcomes
from thm.evaluation.environment import EnvironmentIdentity, EnvironmentRunner, OfficialScorerBridge
from thm.evaluation.memory import AgentMemory
from thm.physical.allocation import AllocationPool, KINDS
from thm.physical.joint import JointComputeDataPlanner
from thm.runtime.fabric.contracts import IndexIdentity
from thm.runtime.fabric.indexes import ExactHost
from thm.runtime.fabric.multidevice import MultiDeviceIndex
from thm.runtime.fabric.extensions import ExtensionConfig, FunctionBinding, ExtensionSession
from thm.runtime.fabric.native import NativeExtensionSeam
from thm.runtime.fabric.catalog import BUILTINS
from thm.runtime.fabric.sdk_extensions import PJRTBinding


def receipt():
    out = {'provenance': 'external-dataset', 'source_sha256': 'a'*64, 'implementation_sha256': 'b'*64,
           'layers': {'memory-dataplane': {'rows': [dict(task_id=i, budget_used=10, latency_ms=1, scorable=True, gold_count=2, hits=1) for i in ('a','b')]},
                      'LLM-agent-outcome': {'status': 'not-run'}}}
    return {**out, 'receipt_sha256': digest(out)}


class OutcomeBridgeTests(unittest.TestCase):
    def test_partial_attach_merge_denominators_cost_and_tamper(self):
        raw = b'trace'; h = hashlib.sha256(raw).hexdigest()
        a = AgentOutcome('a', 'model', 'judge', h, 1, 0, .5, environment_id='env', latency_ms=12,
                         cost_usd=.1, answer_numerator=1, answer_denominator=2)
        partial = attach_outcomes(receipt(), [a], trace_bytes=raw, allow_partial=True)
        self.assertEqual(partial['layers']['LLM-agent-outcome']['missing_task_ids'], ['b'])
        with self.assertRaises(ValueError):
            attach_outcomes(partial, [a], trace_bytes=raw, allow_partial=True)
        b = replace(a, task_id='b', answer_accuracy=1, answer_numerator=3, answer_denominator=3)
        final = attach_outcomes(partial, [b], trace_bytes=raw, allow_partial=True)
        layer = final['layers']['LLM-agent-outcome']
        self.assertEqual(layer['answer_accuracy'], .75)
        self.assertEqual(layer['answer_micro_accuracy'], .8)
        self.assertEqual(layer['cost_usd_observed_sum'], .2)
        self.assertEqual(layer['coverage_status'], 'complete')
        final['provenance'] = 'changed'
        with self.assertRaises(ValueError):
            attach_outcomes(final, [], trace_bytes=raw, allow_partial=True)

    def test_bridge_is_standalone_and_denominator_bound(self):
        evidence = export_evidence(receipt(), source_commit='c'*40)
        self.assertEqual(evidence['measurements']['retrieval_recall']['denominator'], 4)
        self.assertIsNone(evidence['measurements']['full_history_tokens']['value'])
        advice = EconomicAdvice('Context Economics', 'd'*40, evidence['receipt_sha256'], 10, 800, 500)
        self.assertEqual(import_advice(advice.public(), expected_evidence_sha256=evidence['receipt_sha256']), advice)
        with self.assertRaises(ValueError):
            import_advice(advice.public(), expected_evidence_sha256='e'*64)
        with self.assertRaises(ValueError):
            export_evidence(receipt(), source_commit='c'*40, observations={'physical_read': Measurement(1, 'ms', 1, 'sum', 'a'*64)})

    def test_fake_environment_and_official_scorer_are_separate(self):
        closed = []
        env = types.SimpleNamespace(reset=lambda i:'observation', step=lambda a:dict(observation='done',done=True,success=a=='right'), close=lambda:closed.append(True))
        task = Task('a', 'scope', 'query', ())
        r, trace = EnvironmentRunner(env, EnvironmentIdentity('memoryarena','fixture','a'*64)).run(task, lambda q,o,m:'right')
        self.assertTrue(r['environment_success']); self.assertFalse(r['task_outcome_accepted']); self.assertEqual(closed,[True])
        scorer = OfficialScorerBridge(lambda answer,ground_truth,rubric:float(answer==ground_truth),evaluator_id='official-fixture',implementation_sha256='b'*64)
        score = scorer.score(task, GroundTruth('a', answer='gold'), 'gold', trace_sha256=hashlib.sha256(trace).hexdigest())
        self.assertEqual(score['answer_accuracy'],1)

    def test_memory_snapshot_reopen_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); a = AgentMemory(root/'a.db','scope'); a.add('database port is 5439'); a.save(root/'saved'); a.close()
            b = AgentMemory(root/'b.db','scope'); b.restore(root/'saved'); self.assertIn('5439',b.query('database port')); b.close()
            p=root/'saved'/'thm-memory.json'; v=json.loads(p.read_text()); v['documents'][0]['text']='changed'; p.write_text(json.dumps(v))
            c=AgentMemory(root/'c.db','scope')
            with self.assertRaises(ValueError):c.restore(root/'saved')
            c.close()


class PhysicalComputeTests(unittest.TestCase):
    def test_memory_kinds_preserve_owner_and_deferred_eviction(self):
        for kind in KINDS:
            released=[]; p=AllocationPool(32)
            a=p.allocate(representation_sha256='a'*64,generation='g',kind=kind,device='d',size=16,owner='o',
                         allocator=lambda n:(bytearray(n),lambda:released.append(True)))
            with p.acquire(a.allocation_id,generation='g',owner='o') as data:
                p.evict(a.allocation_id); self.assertEqual(len(data),16); self.assertEqual(released,[])
            self.assertEqual(released,[True]); self.assertEqual(p.allocations,{})
            p.close()

    def test_multidevice_exact_global_ties_and_failed_rebuild(self):
        providers=[ExactHost(),ExactHost()]; p=MultiDeviceIndex(providers,budgets=[64,64])
        ident=IndexIdentity('s','g','ep','multi','1','cfg')
        p.build([[1,0],[1,0],[0,1]],['a','b','c'],ident)
        rows,_=p.search([[1,0]],2,generation='g'); self.assertEqual(rows[0][0],['a','b'])
        with self.assertRaises(MemoryError):p.build(np.ones((100,2)),list(range(100)),replace(ident,generation='new'))
        rows,_=p.search([[1,0]],2,generation='g'); self.assertEqual(rows[0][0],['a','b'])
        p.close()

    def test_joint_unknown_fails_closed_and_named_order(self):
        c={k:k for k in ('logical_object','representation','compute_profile','placement','transfer_plan','resident_index','runtime_provider')}
        c.update(generation='g',profile_identity='p',semantic_safe=True,
                 metrics=dict(latency_ms=1,transfer_ms=20,startup_ms=20,compile_ms=20,throughput=10,cpu_seconds=2,replicas=2))
        planner=JointComputeDataPlanner()
        r=planner.choose([c],objective='interactive',constraints={'replicas':('min',2)},current_generation='g',profile_identity='p',expected_reuses=10)
        self.assertEqual(r['predicted_latency_ms'],7)
        c['metrics']['transfer_ms']=None
        self.assertIsNone(planner.choose([c],objective='bulk',constraints={},current_generation='g',profile_identity='p')['selected'])

    def test_all_native_seams_have_executable_configured_lifecycle(self):
        for spec in BUILTINS:
            if not spec.factory.endswith(':NativeExtensionSeam'):continue
            with self.subTest(provider=spec.provider_id):
                cfg=ExtensionConfig(spec.provider_id,'g',hashlib.sha256(b'source').hexdigest(),'sdk','1','d',evidence='fixture-validated')
                binding=FunctionBinding(operations=('transfer',),prepare=lambda x,c:x,compile=lambda x,c:x,
                                        load=lambda x,c:x,execute=lambda h,o,x:bytes(x[::-1]),close=lambda:None)
                p=NativeExtensionSeam(spec).configure(cfg,binding)
                p.prepare(b'source');p.compile();p.load()
                self.assertEqual(p.execute('transfer',b'abc',generation='g'),b'cba')
                self.assertEqual(p.telemetry()['config']['evidence'],'fixture-validated');p.close()

    def test_pjrt_public_compile_path_with_fake_sdk(self):
        class Jit:
            def __init__(self, f):self.f=f
            def lower(self,x):return self
            def compile(self):return self.f
        jax=types.SimpleNamespace(devices=lambda b:['fixture'],device_put=lambda x,d:x,jit=Jit)
        matrix=np.array([[1,2],[3,4]],dtype=np.float32)
        cfg=ExtensionConfig('google.pjrt','g',hashlib.sha256(matrix.tobytes()).hexdigest(),'jax','fixture','cpu',evidence='fixture-validated')
        with mock.patch.dict('sys.modules',{'jax':jax}):
            session=ExtensionSession(cfg,PJRTBinding()); session.prepare(matrix);session.compile();session.load()
            np.testing.assert_array_equal(session.execute('score',np.array([1,0],dtype=np.float32),generation='g'),[1,3]);session.close()


if __name__ == '__main__':unittest.main()
