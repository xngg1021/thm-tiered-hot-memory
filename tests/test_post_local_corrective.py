import copy
import dataclasses
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from thm.runtime.autotune import gate,numeric_guard,autotune,candidate_plan,retrieval_signature
from thm.runtime.testing import FakeEncoder
from thm.runtime.identity import manifest
from thm.runtime.hardware import HardwareProfile
from thm.runtime.micro import DOCUMENTS,QUERIES,CORPUS_SHA
from research.runtime.verify import acceptance_result


class CorrectiveTests(unittest.TestCase):
    def measured(self,source=None):
        e=FakeEncoder()
        if source:e.profile=dataclasses.replace(e.profile,backend='torch_fp32',source_manifest_sha256=source)
        d={'status':'ok','identity':e.identity(),'corpus_sha256':CORPUS_SHA,
           'document_vectors':e(DOCUMENTS),'query_vectors':e(QUERIES),
           'single_query_p95_ms':10.,'queries_per_second':10.,'docs_per_second':10.}
        d['retrieval_signature']=retrieval_signature(d)
        return d

    def test_numeric_noise_only(self):
        a=self.measured();b=copy.deepcopy(a)
        b['retrieval_signature'][0]['scores'][0]+=2e-7
        b['document_vectors'][0][0]+=2e-7
        r=gate(a,b)
        self.assertTrue(r['semantic_admission']);self.assertFalse(r['bitwise_parity'])
        self.assertTrue(r['structural_retrieval_parity'])

    def test_guard_boundaries(self):
        a=self.measured();tol=numeric_guard(a['identity']['dimension'])
        for fraction,accepted in ((.99,True),(1.01,False),(100,False)):
            b=copy.deepcopy(a);b['retrieval_signature'][0]['scores'][0]+=tol*fraction
            self.assertEqual(gate(a,b)['admitted'],accepted)

    def test_structure_always_strict(self):
        a=self.measured()
        for field in ('ranked_ids','selected_ids','packed_evidence','complete_evidence_ids'):
            b=copy.deepcopy(a);b['retrieval_signature'][0][field]=['different']
            b['retrieval_signature'][0]['scores'][0]+=2e-7
            self.assertFalse(gate(a,b)['admitted'])
        b=copy.deepcopy(a);b['retrieval_signature'][0]['budget_used']+=1
        self.assertFalse(gate(a,b)['admitted'])
        b=copy.deepcopy(a)
        for row in b['retrieval_signature']:del row['packed_evidence']
        self.assertFalse(gate(b,b)['admitted'])

    def test_reference_fallback_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'weights').write_bytes(b'x');source=manifest(d)['sha256'];a=self.measured(source);calls=[];plans=[];cache={}
            def runner(config,timeout):
                calls.append(config)
                return copy.deepcopy(a) if config['query_batch_size']==1 and config['document_batch_size']==64 else {'status':'failed'}
            r=autotune(d,'test',maximum=2,runner=runner,reference_session=cache,plan_callback=lambda p:plans.append(copy.deepcopy(p)))
            self.assertEqual(r['selection'],'reference-fallback');self.assertFalse(r['optimized_auto_safe'])
            self.assertTrue(plans[0]);self.assertNotIn('admission_reason',plans[0][1])
            n=len(calls);r=autotune(d,'test',maximum=2,runner=runner,reference_session=cache,baseline_only=True)
            self.assertEqual(len(calls),n);self.assertTrue(r['reference_reuse']['reused'])
            Path(d,'weights').write_bytes(b'y')
            r=autotune(d,'test',maximum=2,runner=runner,reference_session=cache,baseline_only=True)
            self.assertEqual(r['status'],'failed');self.assertGreater(len(calls),n)

    def test_failed_reference_and_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'weights').write_bytes(b'x')
            r=autotune(d,'test',runner=lambda *a:{'status':'failed'})
            self.assertEqual(r['reason'],'reference-unavailable')
            with self.assertRaises(TimeoutError):autotune(d,'test',deadline=0)

    def test_throughput_drift_label(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'weights').write_bytes(b'x');a=self.measured(manifest(d)['sha256'])
            def runner(config,timeout):
                b=copy.deepcopy(a)
                if config['query_batch_size']!=1:b['retrieval_signature'][0]['selected_ids']=['different']
                return b
            r=autotune(d,'test',maximum=1,runner=runner,policy='auto-throughput')
            self.assertEqual(r['semantic_gate'],'measured-drift');self.assertFalse(r['strict_semantic_parity'])
            self.assertIsNone(r['aggregate_quality_parity']);self.assertFalse(r['optimized_auto_safe'])

    def test_cap_prefix_and_diversity(self):
        h=HardwareProfile('x','y','z',process_available_cpus=36)
        backends=[('torch_fp32','cpu'),('torch_fp32','cuda')]
        a=candidate_plan(h,backends,'auto-safe',6);b=candidate_plan(h,backends,'auto-safe',12)
        self.assertEqual([x['config'] for x in a],[x['config'] for x in b])
        self.assertEqual({x['config']['device'] for x in a[1:3]},{'cpu','cuda'})
        self.assertEqual(sum(x['skip_reason'] is None for x in a),7)

    def test_correctness_without_acceleration(self):
        r=acceptance_result(['reference','auto-safe'],{'auto-safe':{'selection':'reference-fallback'}},[{'returncode':0}],[])
        self.assertTrue(r['correctness_acceptance']);self.assertFalse(r['optimized_auto_safe']);self.assertFalse(r['full_dataset_acceptance'])
        r=acceptance_result(['reference','auto-safe'],{'auto-safe':{}},[{'returncode':0}],[{'arm':'auto-safe','strict':False}])
        self.assertFalse(r['correctness_acceptance'])

    def test_safe_failure_stage(self):
        from thm.runtime.prepare import convert
        with patch('thm.runtime.prepare._convert',side_effect=ImportError('/private/user/model/password')):
            r=convert({'backend':'onnxruntime_fp32'})
        self.assertEqual(r['stage'],'model-load');self.assertEqual(r['error_code'],'dependency-missing')
        self.assertNotIn('/private',json.dumps(r));self.assertTrue(r['private_details_redacted'])

    def test_taxonomy_and_bounded_forensics(self):
        from research.runtime.parity_taxonomy import classify,taxonomy
        from research.runtime.diagnostics import score_deltas
        a={'selected_ids':['a','b'],'selected_ranked_ids':['a','b'],'packed_selections':[{'id':'a'},{'id':'b'}],'budget':10,'budget_used':8,'mode':'hybrid',
           'runtime_diagnostics':{'candidate_ids':['a','b'],'scores':[.1,.2]},'text':'private-text'}
        b=copy.deepcopy(a);b['selected_ranked_ids'].reverse();self.assertEqual(classify(a,b),'rank-only')
        b['packed_selections'].reverse();self.assertEqual(classify(a,b),'same-set-different-order')
        b['selected_ids']=['c'];self.assertEqual(classify(a,b),'selected-set-change')
        d=score_deltas({'rows':[a]},{'rows':[b]},maximum_candidates=1)
        self.assertNotIn('private-text',json.dumps(d));self.assertEqual(len(d['queries'][0]['scores']),1)
        self.assertIn('cutoff_position',d['queries'][0])
        self.assertEqual(taxonomy({'rows':[a]},{'rows':[b]})['rows_accounted'],1)

    def test_dispatch_requires_execution_line(self):
        from thm.runtime.dispatch_evidence import observe
        with tempfile.TemporaryDirectory() as root:
            p=Path(root,'log');p.write_text('onednn_verbose,info,cpu,isa:avx512_core_vnni')
            self.assertIsNone(observe(p,backend='torch',workload_sha256='a'*64)['observed_kernel_dispatch'])
            p.write_text('onednn_verbose,primitive,exec,cpu,matmul,brg:avx512_core_vnni,/private')
            r=observe(p,backend='torch',workload_sha256='a'*64)
            self.assertEqual(r['observed_kernel_dispatch'],['AVX512-VNNI']);self.assertNotIn('/private',json.dumps(r))

if __name__=='__main__':unittest.main()
