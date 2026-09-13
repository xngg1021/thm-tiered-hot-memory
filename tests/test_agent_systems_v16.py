import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import date
from thm.systems.contracts import HotnessVector, PermissionGate, ProfileStamp, atomic_json
from thm.systems.topology import DynamicTopologyFabric, TopologyEvent
from thm.systems.thermal import ThermalSample, SustainablePerformanceEnvelope, quantiles, duration_sweep, thermal_backpressure, LinuxThermalPowerProvider
from thm.systems.concurrency import ElasticConcurrencyController, WorkItem
from thm.systems.native import psi_snapshot, CgroupDomain
from thm.systems.syscore import SysCore, NativeAsyncIO
from thm.long_tail import TimeInterval, Event, EventGraph, EvidenceCandidate, joint_select, ordering_metrics, age_arithmetic
from thm.evaluation.ceiling import RetrievalCeilingReport
from thm.reliability import LifeObservation, survival, SelfVerificationEpochs, accelerated_life
from thm.evidence_storage import EvidenceArtifactManifest, LocalEvidenceStore, GIT_THRESHOLD
from thm.systems.agent import AgentProgramIdentity, KVRecord, KVResidencyBridge, ToolInvocation, Span, critical_path, tool_overlap
from thm.systems.simulator import AgentSystemsSimulator, AgentTaskTrace
from research.recall.mps_parity import parity_gate


class TopologyTests(unittest.TestCase):
    def online(self):
        fabric = DynamicTopologyFabric()
        fabric.event(TopologyEvent('gpu-appeared', 'gpu', 1, 'fingerprint', 'driver-v1'))
        fabric.qualify('gpu', 1, 'fingerprint', passed=True)
        fabric.open_session('s', 'gpu')
        return fabric

    def test_hotness_is_vector_and_pressure_not_residency_score(self):
        vector = HotnessVector(thermal_pressure=1.)
        self.assertEqual(vector.residency_value, 0)
        with self.assertRaises(ValueError):
            HotnessVector(thermal_pressure=float('nan'))

    def test_loss_invalidates_handle_and_session_pin(self):
        fabric = self.online()
        handle = fabric.admit('s', 'source', 'index')
        fabric.event(TopologyEvent('gpu-lost', 'gpu', 2))
        with self.assertRaises(ValueError):
            fabric.validate(handle)
        self.assertIsNone(fabric.admit('s', 'source', 'index'))

    def test_recovery_requires_new_generation_and_new_session(self):
        fabric = self.online()
        fabric.event(TopologyEvent('gpu-reset', 'gpu', 2))
        fabric.event(TopologyEvent('gpu-appeared', 'gpu', 3, 'fingerprint', 'driver-v2'))
        with self.assertRaises(ValueError):
            fabric.qualify('gpu', 1, 'fingerprint', passed=True)
        fabric.qualify('gpu', 2, 'fingerprint', passed=True)
        self.assertIsNone(fabric.admit('s', 'source', 'index'))
        fabric.open_session('s2', 'gpu')
        self.assertEqual(fabric.admit('s2', 'source', 'index').generation, 2)

    def test_concurrent_drain_stops_new_admission(self):
        fabric = self.online()
        handle = fabric.admit('s', 'source', 'index')
        fabric.begin_drain('gpu')
        results = []
        worker = threading.Thread(target=lambda: results.append(fabric.admit('s', 'source', 'index')))
        worker.start(); worker.join()
        self.assertEqual(results, [None])
        fabric.complete(handle)
        self.assertEqual(fabric.finish_drain('gpu', deadline=2, now=1)['status'], 'offline')

    def test_drain_deadline_cancels_and_preserves_rebuild_locator(self):
        fabric = self.online()
        handle = fabric.admit('s', 'source', 'index')
        fabric.begin_drain('gpu')
        self.assertEqual(fabric.finish_drain('gpu', deadline=2, now=1)['status'], 'draining')
        result = fabric.finish_drain('gpu', deadline=2, now=2)
        self.assertEqual(result['rebuild_from_source'], ('source',))
        with self.assertRaises(ValueError):
            fabric.complete(handle)

    def test_out_of_order_and_foreign_handles_fail_closed(self):
        fabric = self.online()
        with self.assertRaises(ValueError):
            fabric.event(TopologyEvent('wake', 'gpu', 1))
        handle = fabric.admit('s', 'source', 'index')
        with self.assertRaises(ValueError):
            fabric.validate(replace(handle, source_identity='other'))

    def test_profile_expiry_epoch_and_clock_regression(self):
        p = ProfileStamp('thermal', 2, 1, 'driver', 10., 5.)
        self.assertTrue(p.fresh(11, 2, 1, 'driver'))
        for args in ((15,2,1,'driver'), (9,2,1,'driver'), (11,3,1,'driver'), (11,2,2,'driver')):
            self.assertFalse(p.fresh(*args))


class ThermalConcurrencyTests(unittest.TestCase):
    def test_power_semantics_do_not_fill_observed_from_tdp(self):
        sample = ThermalSample('cpu', 1., 0., 'fixture', design_power=100, evidence='simulated')
        self.assertIsNone(sample.public()['observed_instant_power'])
        self.assertIsNone(sample.public()['energy_wh'])

    def test_percentiles_and_sustained_envelope(self):
        self.assertGreater(quantiles(range(100))['p99.9'], quantiles(range(100))['p95'])
        samples = (ThermalSample('cpu',0,1,'fixture',energy_j=5,evidence='simulated'),
                   ThermalSample('cpu',1,1,'fixture',energy_j=7,evidence='simulated'))
        e = SustainablePerformanceEnvelope('cpu','query',1,1,1,'warm','unknown',(.1,.2),thermal=samples)
        self.assertEqual(e.public()['energy_per_operation'], 1.)

    def test_counter_reset_is_not_negative_energy(self):
        a = ThermalSample('cpu',0,0,'fixture',energy_j=7,evidence='simulated')
        b = replace(a, sample_timestamp=1, energy_j=1)
        e = SustainablePerformanceEnvelope('cpu','q',1,1,1,'warm','unknown',(.1,),thermal=(a,b))
        self.assertIsNone(e.public()['energy_per_operation'])

    def test_unobserved_or_rising_temperature_limits_background(self):
        self.assertEqual(thermal_backpressure([],now=1)['background_share'],0)
        a = ThermalSample('gpu',1,1,'fixture',temperature_c=75,thermal_headroom_c=10,evidence='simulated')
        b = replace(a,sample_timestamp=2,temperature_c=80,thermal_headroom_c=5)
        self.assertEqual(thermal_backpressure((a,b),now=2)['background_share'],0)

    def test_duration_full_research_is_explicit(self):
        with self.assertRaises(ValueError):
            duration_sweep()
        self.assertEqual(duration_sweep(full_research=True)[-1],300)

    def test_interactive_queue_preempts_background(self):
        ctrl = ElasticConcurrencyController(concurrency=2)
        ctrl.submit(WorkItem('b','p','background',0,5),0)
        ctrl.submit(WorkItem('i','p','interactive',0,5),0)
        batch = ctrl.dispatch(1)
        self.assertEqual([x.identity for x in batch],['i'])
        ctrl.complete('i',2)
        self.assertEqual(ctrl.receipt()['latency']['p95'],2.)

    def test_tail_and_psi_feed_backpressure(self):
        ctrl = ElasticConcurrencyController()
        result = ctrl.feedback([],{'cpu':.5},now=1)
        self.assertEqual(result['concurrency'],3)
        self.assertEqual(result['background_share'],0)

    def test_native_psi_parsing_and_permission_gated_cgroup_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'cpu.pressure').write_text('some avg10=10.00 avg60=1.00 avg300=0.00 total=1000\n')
            self.assertEqual(psi_snapshot(root)['resources']['cpu']['rows']['some']['avg10'],10.)
            (root/'cpu.weight').write_text('100')
            domain=CgroupDomain(root)
            with self.assertRaises(PermissionError):
                domain.configure({'cpu.weight':50})
            gate=PermissionGate('S1',True,True,False,False,True)
            domain.configure({'cpu.weight':50},gate)
            self.assertEqual((root/'cpu.weight').read_text(),'50')
            domain.rollback()
            self.assertEqual((root/'cpu.weight').read_text(),'100')
            with self.assertRaises(PermissionError):
                domain.configure({'cpu.max':'1000 100000'},gate)

    def test_sysfs_fixture_leaves_requested_clock_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); p=root/'devices/system/cpu/cpufreq/policy0'; p.mkdir(parents=True)
            (p/'scaling_cur_freq').write_text('2400000')
            sample=LinuxThermalPowerProvider(root).samples()[0]
            self.assertEqual(sample.requested_clock_hz,2400000000)
            self.assertIsNone(sample.effective_clock_hz)


class LongTailTests(unittest.TestCase):
    def event(self,key,when,**kwargs):
        return Event(key,'scope',key,'a'*64,TimeInterval.parse(when),**kwargs)

    def test_partial_date_precision_does_not_invent_order(self):
        month=TimeInterval.parse('2026-02'); day=TimeInterval.parse('2026-02-12')
        self.assertTrue(month.overlaps(day)); self.assertFalse(month.before(day)); self.assertFalse(month.after(day))
        self.assertEqual(TimeInterval.parse('yesterday',anchor=date(2026,3,1)).start,date(2026,2,28))

    def test_age_arithmetic_preserves_uncertainty(self):
        value=age_arithmetic(TimeInterval.parse('1997'),TimeInterval.parse('2026-09-13'))
        self.assertEqual((value['minimum_years'],value['maximum_years']),(28,29))

    def test_temporal_operator_suite(self):
        graph=EventGraph('scope',[self.event('a','2026-01-01'),self.event('b','2026-02-01'),self.event('c','2026-03-01')])
        reference=TimeInterval.parse('2026-02-01')
        for operation,ids in [('before',['a']),('after',['c']),('closest-before',['a']),('closest-after',['c']),
                               ('same-day',['b']),('interval-overlap',['b']),('date-range',['b']),('first',['a']),('last',['c'])]:
            self.assertEqual([e.identity for e in graph.select(operation,reference)],ids)

    def test_supersession_is_explicit_and_source_scoped(self):
        graph=EventGraph('scope',[self.event('a','2026'),self.event('b','2026',supersedes=('a',),contradicts=('c',))])
        self.assertEqual([r['state'] for r in graph.claims()],['superseded','unresolved-conflict'])
        with self.assertRaises(ValueError):
            graph.add(replace(self.event('c','2026'),scope='other'))

    def test_event_cycles_and_unresolved_predecessors(self):
        graph=EventGraph('scope',[self.event('a','2026',predecessor=('b',))])
        with self.assertRaises(ValueError):
            graph.add(self.event('b','2026',predecessor=('a',)))
        with self.assertRaises(ValueError):
            graph.required_chain('a')

    def test_joint_selection_beats_top_rank_truncation(self):
        rows=[EvidenceCandidate('large',10,1),EvidenceCandidate('b',5,.9),EvidenceCandidate('c',5,.9)]
        selected=joint_select(rows,10)
        self.assertEqual(set(selected['ids']),{'b','c'}); self.assertEqual(selected['method'],'exact')

    def test_complementary_required_set_cannot_be_partially_admitted(self):
        rows=[EvidenceCandidate('a',6,10,required_set=frozenset({'b'})),EvidenceCandidate('b',6,1)]
        self.assertNotIn('a',joint_select(rows,6)['ids'])

    def test_ceiling_distinguishes_ranking_and_packing_loss(self):
        rows=tuple(EvidenceCandidate(key,2,0,frozenset({key})) for key in 'abc')
        report=RetrievalCeilingReport('t',frozenset('abc'),rows,('a','b'),('a',),6).public()
        self.assertEqual(report['ranking_loss'],1); self.assertEqual(report['packing_loss'],1)
        self.assertEqual(report['budget_oracle']['covered_units'],3)

    def test_budget_ceiling_explains_impossible_all_gold(self):
        rows=(EvidenceCandidate('a',5,0,frozenset('a')),EvidenceCandidate('b',5,0,frozenset('b')))
        result=RetrievalCeilingReport('t',frozenset('ab'),rows,('a','b'),('a',),5).public()
        self.assertFalse(result['budget_oracle']['all_gold']); self.assertEqual(result['ranking_loss'],0)
        self.assertEqual(result['packing_loss'],0)

    def test_ordering_metric_separates_missing_and_misordered(self):
        result=ordering_metrics('abcd','cba')
        self.assertEqual(result['set_recall'],.75); self.assertEqual(result['kendall_tau'],-1)
        self.assertEqual(result['missing'],['d'])


class ReliabilityAndArtifactTests(unittest.TestCase):
    def test_censored_runs_preserved_and_small_sample_b10_absent(self):
        result=survival([LifeObservation('a',100,False),LifeObservation('b',200,False)])
        self.assertEqual(result['right_censored_runs'],2); self.assertIsNone(result['life_quantiles']['B10'])
        self.assertEqual(result['failure_free_demonstrated_exposure'],300)
        self.assertGreater(result['zero_failure_poisson_rate_upper'],0)

    def test_mixed_exposures_rejected(self):
        with self.assertRaises(ValueError):
            survival([LifeObservation('a',1,False),LifeObservation('b',1,False,'sessions')])

    def test_survival_with_failures_and_censoring(self):
        rows=[LifeObservation(str(i),i+1,i<10,failure_class='F2' if i<10 else None) for i in range(20)]
        result=survival(rows)
        self.assertEqual(result['life_quantiles']['B10'],2)
        self.assertEqual(result['right_censored_runs'],10)
        self.assertIsNone(result['MTBF']); self.assertIsNone(result['MTTF'])

    def test_accelerated_bounds_and_failure_not_suppressed(self):
        with self.assertRaises(ValueError):
            accelerated_life(lambda *_:None,events=1000000)
        result=accelerated_life(lambda fault,index,rng:{'recovered':index != 3},events=20)
        self.assertEqual(len(result['invariant_failures']),1)
        self.assertIsNone(result['production_MTBF'])

    def test_content_addressed_store_rejects_corrupt_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store=LocalEvidenceStore(directory); data=b'original evidence'; location=store.put(data)
            m=EvidenceArtifactManifest(**location,mime='text/plain',schema='test/1',source_commit='a'*40,
                                       producer='test',dataset='fixture',workload='read')
            self.assertEqual(store.get(m),data)
            (Path(directory)/location['sha256']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError): store.get(m)
            with self.assertRaises(ValueError): store.put(data)

    def test_large_artifact_manifest_does_not_require_git_blob(self):
        m=EvidenceArtifactManifest('a'*64,GIT_THRESHOLD+1,'application/json','test/1','b'*40,'test','fixture','read','object')
        self.assertFalse(m.public()['normal_git_eligible'])

    def test_atomic_json_is_valid_consumed_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'; sha=atomic_json(path,{'schema':'test/1'})
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)
            self.assertEqual(json.loads(path.read_text())['schema'],'test/1')


class AgentAndAppleTests(unittest.TestCase):
    def identity(self):
        return AgentProgramIdentity('p','trajectory','session','turn','tool','ToolCall')

    def test_side_effecting_tool_never_speculates(self):
        tool=ToolInvocation(self.identity(),'proposed','ready','side-effecting','a'*64)
        self.assertEqual(tool.speculation(opt_in=True)['mode'],'shadow')

    def test_safe_tool_defaults_shadow(self):
        tool=ToolInvocation(self.identity(),'proposed','ready','read-only','a'*64)
        self.assertEqual(tool.speculation()['mode'],'shadow')
        self.assertEqual(tool.speculation(opt_in=True)['mode'],'execute')

    def test_tool_overlap_is_interval_union_not_product(self):
        r=tool_overlap(1,4,0,3)
        self.assertEqual(r['total_tool_latency'],3); self.assertEqual(r['overlapped_tool_latency'],2)
        self.assertEqual(r['exposed_tool_latency'],1)

    def test_critical_path_and_tufr_have_distinct_denominators(self):
        spans=(Span('r','retrieval',0,1),Span('d','decode',1,5,('r',)),Span('t','tool',1,3,('r',)))
        r=critical_path(spans,submitted=0,useful_first=2)
        self.assertEqual(r['TUFR'],2); self.assertEqual(r['task_completion_time'],5)
        self.assertEqual(r['critical_path'],['r','d']); self.assertEqual(r['raw_component_time']['tool'],2)

    def test_simulator_common_denominator_never_hardware_acceptance(self):
        task=AgentTaskTrace('t1','u','s',0,.1,.1,.2,.3,.2,.1,'prefix')
        runs=AgentSystemsSimulator().ablation_ladder([task,replace(task,task_id='t2',arrival=1)])
        self.assertEqual(len({r['task_denominator_sha256'] for r in runs}),1)
        self.assertTrue(all(r['evidence']=='simulated' and not r['hardware_acceptance'] for r in runs))
        self.assertIsNone(runs[0]['rows'][0]['TUFR'])

    def test_parity_threshold_regression_rejects_old_false_positive(self):
        self.assertFalse(parity_gate([.5],1e-7,True))
        self.assertTrue(parity_gate([.9999998808],1.825e-7,True))
        self.assertFalse(parity_gate([1.],.1,True))
        self.assertFalse(parity_gate([1.],0,False))
        self.assertFalse(parity_gate([float('nan')],0,True))

    def test_headless_syscore_fallback_and_source_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'data'; path.write_bytes(b'content')
            core=SysCore(); sha=hashlib.sha256(b'content').hexdigest()
            self.assertEqual(core.read_verified(path,sha),b'content')
            self.assertFalse(core.last['native_executed'])
            with self.assertRaises(ValueError): core.read_verified(path,'0'*64)
            io=NativeAsyncIO(core); io.submit('r',path,sha,time.monotonic()+1)
            self.assertEqual(io.complete_batch()[0]['status'],'complete')
            io.submit('cancel',path,sha,time.monotonic()+1); self.assertTrue(io.cancel('cancel')); io.close()

    @unittest.skipUnless(os.environ.get('THM_SYSCORE_EXECUTABLE'), 'native executable not supplied; Python fallback tested separately')
    def test_native_syscore_protocol_and_file_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'payload'; path.write_bytes(b'native read')
            core=SysCore(os.environ['THM_SYSCORE_EXECUTABLE'])
            caps=core.capabilities(); self.assertNotIn('fallback',caps)
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(core.read_verified(path,sha,native_io=False),b'native read')
            self.assertTrue(core.last['native_executed'])
            self.assertEqual(core.read_verified(path,sha),b'native read')


if __name__=='__main__': unittest.main()
