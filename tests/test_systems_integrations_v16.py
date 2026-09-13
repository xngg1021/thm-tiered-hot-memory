from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import tempfile
import unittest
from unittest.mock import patch
from thm.systems.cli import smoke, reliability_smoke
from thm.evaluation.adapters import ADAPTERS
from thm.evaluation.fixtures import FIXTURES
from thm.evaluation.runner import run
from thm.systems.contracts import digest
from thm.systems.economics import export_systems_evidence, RuntimeMeasurement, RuntimeEconomicAdvice, import_systems_advice
from thm.economics_bridge import EconomicAdvice
from thm.systems.apple import apple_auto_admission, coreml_placement_receipt
from thm.systems.native import ProbeContract
from thm.reliability import recurrent_metrics
from thm.reliability.faults import publication_fault, worker_fault, byte_identity_fault
from thm.systems.artifacts import model_snapshot


class Integrations(unittest.TestCase):
    def test_actual_harness_systems_long_tail_evaluation_and_reliability(self):
        result=smoke()
        self.assertEqual(result['status'],'passed')
        self.assertFalse(result['systems_receipt']['source_memory_mutation'])
        self.assertIn('ceiling',result['candidate']['layers']['memory-dataplane']['rows'][0])

    def test_all_five_evaluation_adapters_accept_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            for name,adapter in ADAPTERS.items():
                with self.subTest(name=name):
                    receipt=run(adapter,FIXTURES[name],Path(directory)/name,mode='smoke',
                                provenance='deterministic-fixture',long_tail=True,ceiling=True)
                    self.assertIn('ceiling',receipt['layers']['memory-dataplane']['rows'][0])

    def test_ce_v2_same_task_denominator_and_no_byte_to_token_cast(self):
        with tempfile.TemporaryDirectory() as directory:
            result=run(ADAPTERS['locomo'],FIXTURES['locomo'],Path(directory)/'run',provenance='deterministic-fixture')
        ids=[r['task_id'] for r in result['layers']['memory-dataplane']['rows']]
        systems={'task_ids':ids,'source_commit':'a'*40,'topology_epoch':1,
                 'measurements':{'power':{'value':50,'unit':'watt','denominator':1,'evidence':'simulated',
                                          'aggregation':'mean','exposure_unit':None}}}
        systems['receipt_sha256']=digest(systems)
        m=RuntimeMeasurement(50,'watt',1,systems['receipt_sha256'],'simulated')
        receipt=export_systems_evidence(result,source_commit='a'*40,systems_receipt=systems,measurements={'power':m})
        for changed in ({'value':500},{'denominator':20},{'evidence':'hardware-observed'},{'aggregation':'sum'}):
            with self.assertRaisesRegex(ValueError,'not covered'):
                export_systems_evidence(result,source_commit='a'*40,systems_receipt=systems,
                                        measurements={'power':replace(m,**changed)})
        self.assertEqual(receipt['schema'],'thm-ce-evidence/2')
        self.assertIsNone(receipt['measurements']['packed_tokens']['value'])
        self.assertEqual(receipt['systems_measurements']['power']['evidence'],'simulated')
        wrong={**systems,'task_ids':['other']};wrong['receipt_sha256']=digest({k:v for k,v in wrong.items() if k!='receipt_sha256'})
        with self.assertRaises(ValueError):export_systems_evidence(result,source_commit='a'*40,systems_receipt=wrong)

    def test_ce_advice_is_epoch_bound_and_optional(self):
        memory=EconomicAdvice('scope','a'*40,'b'*64,100,1000,600)
        advice=RuntimeEconomicAdvice(memory,2,10,concurrency_constraint=2)
        self.assertEqual(import_systems_advice(advice.public(),expected_evidence_sha256='b'*64,topology_epoch=2,now=5),advice)
        with self.assertRaises(ValueError):
            import_systems_advice(advice.public(),expected_evidence_sha256='b'*64,topology_epoch=3,now=5)

    def test_model_snapshot_never_consumes_replaced_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'weights').write_bytes(b'original')
            with model_snapshot(root) as (snapshot,manifest):
                (root/'weights').write_bytes(b'replacement')
                self.assertEqual((snapshot/'weights').read_bytes(),b'original')
            self.assertFalse(snapshot.exists())

    def test_model_snapshot_rejects_load_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'weights').write_bytes(b'original')
            with self.assertRaises(ValueError):
                with model_snapshot(root) as (snapshot,manifest):
                    (snapshot/'weights').write_bytes(b'mutated')

    def test_publication_and_worker_fault_injection(self):
        for fault in ('short-write','disk-full'):
            self.assertTrue(publication_fault(fault)['recovered'])
        for fault in ('provider-crash','worker-hang'):
            self.assertTrue(worker_fault(fault)['recovered'])
        for fault in ('corruption','storage-disappearance'):
            self.assertTrue(byte_identity_fault(fault)['recovered'])

    def test_apple_auto_admission_requires_sustained_and_new_session(self):
        flags=dict(mps_available=True,semantic_parity=True,sustained_gain=True,memory_accepted=True,fresh=True,new_session=True)
        self.assertTrue(apple_auto_admission(**flags)['eligible'])
        for name in flags:
            self.assertFalse(apple_auto_admission(**{**flags,name:False})['eligible'])
        self.assertFalse(coreml_placement_receipt('CPU_AND_NE')['ANE_accepted'])

    def test_ebpf_etw_fixture_contract_is_not_native_evidence(self):
        class Binding:
            evidence='callable-fixture'
            def poll(self,timeout,capacity):return [{'kind':'scheduler','delay_ms':1}]
            def close(self):self.closed=True
        for name in ('ebpf','etw'):
            binding=Binding();probe=ProbeContract(binding,platform_name=name)
            self.assertEqual(probe.collect()['evidence'],'callable-fixture')
            probe.close();self.assertTrue(binding.closed)

    def test_recurrent_mtbf_requires_repair_process_and_enough_failures(self):
        self.assertIsNone(recurrent_metrics(uptime=100,failures=1,recoveries=[1])['MTBF'])
        result=recurrent_metrics(uptime=100,failures=5,recoveries=[1]*5)
        self.assertEqual(result['MTBF'],20);self.assertEqual(result['MTTR'],1)

    @unittest.skipUnless(platform.system()=='Darwin','Accelerate requires macOS; fixture checks remain separate')
    def test_native_accelerate_matrix_parity(self):
        import numpy as np
        from thm.systems.apple import AccelerateVector
        bridge=AccelerateVector()
        try:
            result=bridge.matmul([[1,2],[3,4]],[[1],[2]])
            np.testing.assert_allclose(result,[[5],[11]])
        finally:bridge.close()

    def test_mps_availability_smoke_reports_real_skip(self):
        try:import torch
        except ImportError:self.skipTest('torch not installed; no MPS execution claimed')
        if not torch.backends.mps.is_available():self.skipTest('MPS unavailable on this runner')
        import numpy as np
        a=torch.tensor([[1.,2.],[3.,4.]])
        actual=(a.to('mps')@a.to('mps')).cpu().numpy()
        np.testing.assert_allclose(actual,(a@a).numpy(),rtol=1e-5,atol=1e-5)


if __name__=='__main__':unittest.main()
