import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from thm.systems.runtime import AgentSystemsRuntime
from thm.systems.topology import TopologyEvent
from thm.systems.syscore import SysCore, TransportError
from thm.systems.thermal import ThermalActuator, LinuxThermalPowerProvider
from thm.systems.contracts import PermissionGate
from thm.evaluation.adapters import ADAPTERS
from thm.evaluation.fixtures import FIXTURES
from thm.evaluation.runner import run
from thm.retrieval import SearchIndex


class ReviewRegressions(unittest.TestCase):
    def test_epoch_publication_is_atomic_against_concurrent_event(self):
        runtime=AgentSystemsRuntime(SimpleNamespace(search=lambda *a,**k:{'marker':'old'}))
        attempted=threading.Event();published=threading.Event()
        original=runtime.controller.complete
        def event():
            attempted.set();runtime.event(TopologyEvent('reprobe','gpu',1));published.set()
        thread=threading.Thread(target=event)
        def complete(*a,**k):
            thread.start();self.assertTrue(attempted.wait(1))
            self.assertFalse(published.wait(.02))
            return original(*a,**k)
        with patch.object(runtime.controller,'complete',complete):
            result=runtime.search('scope','query')
        thread.join(1);self.assertTrue(published.is_set())
        self.assertEqual(result['systems_receipt']['topology_epoch'],0)
        self.assertEqual(result['systems_receipt']['topology']['topology_epoch'],0)
        self.assertEqual(runtime.topology.epoch,1)

    def test_native_timeout_does_not_restart_fallback_deadline(self):
        core=SysCore(__file__,timeout=.04);attempts=[]
        original=core._request
        def request(op,payload=b'',**kw):
            attempts.append(kw)
            if not kw.get('portable'):
                time.sleep(.05);raise subprocess.TimeoutExpired('worker',.04)
            return original(op,payload,**kw)
        with patch.object(core,'_request',request):
            with self.assertRaises(TimeoutError):core.read_verified(__file__,'a'*64)
        self.assertEqual(attempts[0]['deadline'],attempts[1]['deadline'])

    def test_invalid_transport_falls_back_but_bad_content_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source';path.write_bytes(b'valid')
            core=SysCore(__file__);original=core._request
            def invalid(op,payload=b'',**kw):
                if not kw.get('portable'):raise TransportError('truncated')
                return original(op,payload,**kw)
            with patch.object(core,'_request',invalid):
                self.assertEqual(core.read_verified(path,hashlib.sha256(b'valid').hexdigest()),b'valid')
            with patch.object(core,'_request',return_value=b'corrupt') as request:
                with self.assertRaisesRegex(ValueError,'native consumed bytes'):
                    core.read_verified(path,hashlib.sha256(b'valid').hexdigest())
                self.assertEqual(request.call_count,1)

    def test_runner_retains_candidates_excluded_by_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(SearchIndex,'_rank_candidates',lambda self,scope,query,rows:[]):
                receipt=run(ADAPTERS['locomo'],FIXTURES['locomo'],Path(directory)/'run',ceiling=True)
        ceilings=[r['ceiling'] for r in receipt['layers']['memory-dataplane']['rows']]
        self.assertTrue(any(r['ranking_loss']>0 for r in ceilings))
        self.assertTrue(all(r['ranked_budget_oracle']['covered_units']==0 for r in ceilings))

    def test_thermal_actuation_gate_and_failure_rollback(self):
        class Binding:
            evidence='callable-fixture'
            value=100
            def supports(self,control):return control=='power-cap'
            def read(self,control):return self.value
            def validate(self,control,value):
                if value<10:raise ValueError('out of range')
            def write(self,control,value):
                self.value=value
                if value==50:raise OSError('write failed after partial effect')
        binding=Binding();actuator=ThermalActuator(binding)
        with self.assertRaises(PermissionError):actuator.apply('power-cap',70,PermissionGate())
        gate=PermissionGate('S2',True,True,True,True,True)
        with self.assertRaises(OSError):actuator.apply('power-cap',50,gate)
        self.assertEqual(binding.value,100)
        actuator.apply('power-cap',70,gate);actuator.rollback();self.assertEqual(binding.value,100)

    def test_custom_sysfs_tree_is_fixture_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            zone=Path(directory)/'class/thermal/thermal_zone0';zone.mkdir(parents=True)
            (zone/'temp').write_text('40000')
            rows=LinuxThermalPowerProvider(directory).samples()
        self.assertTrue(rows)
        self.assertTrue(all(row.evidence=='callable-fixture' for row in rows))


if __name__=='__main__':unittest.main()

class SourceAndOracleRegressions(unittest.TestCase):
    def test_oracle_charges_required_source_cost(self):
        from thm.long_tail import EvidenceCandidate
        from thm.evaluation.ceiling import RetrievalCeilingReport
        rows=(EvidenceCandidate('gold',1,0,frozenset({'g'}),frozenset({'source'})),
              EvidenceCandidate('source',100,0))
        receipt=RetrievalCeilingReport('q',frozenset({'g'}),rows,('gold','source'),(),50).public()
        self.assertTrue(receipt['candidate_ceiling']['any_gold'])
        self.assertFalse(receipt['budget_oracle']['any_gold'])
        self.assertTrue(receipt['budget_oracle']['ceiling_valid'])

    def test_attached_event_channel_rejects_source_replacement(self):
        from thm.long_tail import Event,EventGraph,TimeInterval
        from thm.long_tail_retrieval import LongTailSearchIndex
        from thm.retrieval import Document,TokenCounter
        with tempfile.TemporaryDirectory() as directory:
            index=LongTailSearchIndex(Path(directory)/'index',TokenCounter('utf8_bytes'))
            try:
                index.replace_scope('s',[Document('d','s','session',0,'comet travels')])
                row=index.rows('s')[0]
                index.attach_events(EventGraph('s',[Event('e','s','d',row['hash'],TimeInterval.parse('2026-01-01'))]))
                result=index.search('s','event before 2026-02-01')
                self.assertEqual(result['selected'][0]['id'],'d')
                index.replace_scope('s',[Document('d','s','session',0,'replaced content')])
                with self.assertRaisesRegex(ValueError,'stale event'):
                    index.search('s','event before 2026-02-01')
            finally:index.close()

class NativeBoundRegressions(unittest.TestCase):
    def test_graph_output_allocation_is_bounded_before_framework_import(self):
        import numpy as np
        from thm.systems.apple import MPSGraphBinding
        graph=MPSGraphBinding(api=object())
        for left,right in ((np.ones((2000,1)),np.ones((1,2000))),
                           (np.empty((0,1)),np.ones((1,1)))):
            with self.assertRaisesRegex(ValueError,'bounded compatible'):
                graph.matmul(left,right)

    def test_numeric_sensor_rejects_oversized_payload(self):
        from thm.systems.thermal import read_number
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sensor';path.write_text('1'*129)
            self.assertIsNone(read_number(path))
