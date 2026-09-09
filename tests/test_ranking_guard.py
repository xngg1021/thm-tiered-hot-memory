"""Engineering proof: admitted stable queries do bounded row checks only."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import numpy as np
from thm.retrieval import SearchIndex
from thm.runtime.testing import FakeEncoder
from thm.runtime.fabric.registry import builtin_registry
from thm.runtime.fabric.service import ResidentExecutor, RuntimeService
from test_provider_fabric import documents


class TracedMatrix(np.ndarray):
    calls = []
    def __matmul__(self, other):
        type(self).calls.append(self.shape[0])
        return super().__matmul__(other)


def matrix(n=500):
    values = np.zeros((n,8),dtype=np.float32)
    values[:,0] = np.linspace(.95,-.9,n)
    values[:,1] = np.sqrt(1-values[:,0]**2)
    return values.view(TracedMatrix)


class RankingGuardTests(unittest.TestCase):
    def test_admitted_resident_queries_score_only_topk_plus_cutoff(self):
        registry = builtin_registry(extensions=False); executor = ResidentExecutor(registry)
        values=matrix(); ids=list(range(1,len(values)+1)); query=[1.]+[0.]*7
        executor.admission=('g','p'); TracedMatrix.calls=[]
        try:
            for _ in range(2):
                rows,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=ids,
                    matrix=values,queries=[query,query],top_k=5)
                self.assertEqual(rows[0][0],[1,2,3,4,5])
                self.assertTrue(receipt['strict_verified'])
                self.assertTrue(all(g['reference_full_scans']==0 for g in receipt['ranking_guards']))
            self.assertEqual(TracedMatrix.calls,[6,6,6,6])
            self.assertTrue(receipt['resident_hit'])
        finally:
            executor.close();registry.close()

    def test_ambiguous_cutoff_falls_back_to_stable_singleton_scan(self):
        registry=builtin_registry(extensions=False);executor=ResidentExecutor(registry)
        values=matrix();values[1]=values[0];executor.admission=('g','p');TracedMatrix.calls=[]
        try:
            rows,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=list(range(500)),
                matrix=values,queries=[[1.]+[0.]*7],top_k=1)
            self.assertEqual(rows[0][0],[0])
            self.assertEqual(receipt['ranking_guards'][0]['reference_full_scans'],1)
            self.assertEqual(TracedMatrix.calls,[2,500])
        finally:
            executor.close();registry.close()

    def test_unverified_accumulation_cannot_use_cutoff_certificate(self):
        registry=builtin_registry(extensions=False);executor=ResidentExecutor(registry)
        registry.get('host.exact').fp32_accumulation=lambda:False
        executor.admission=('g','p');TracedMatrix.calls=[]
        try:
            _,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=list(range(500)),
                matrix=matrix(),queries=[[1.]+[0.]*7],top_k=5)
            self.assertEqual(receipt['ranking_guards'][0]['fallback_reason'],'unverified-accumulation')
            self.assertEqual(TracedMatrix.calls,[500])
        finally:
            executor.close();registry.close()

    def test_session_pinned_online_cohort_does_not_rescan_full_reference(self):
        encoder=FakeEncoder();encoder.encode_many=lambda texts:[[1.]+[0.]*7 for _ in texts]
        with tempfile.TemporaryDirectory() as temp:
            index=SearchIndex(Path(temp)/'index.sqlite');index.replace_scope('scope',documents(500))
            index.embed('scope',encoder,encoder.model_id)
            service=RuntimeService(index,encoder=encoder,model_id=encoder.model_id,background=False)
            values=matrix();ids=[r['rowid'] for r in index.rows('scope')]
            settings={'mode':'dense','candidate_limit':5}
            key,_,_=service._key('scope','interactive',settings);candidate=service.candidates[0]
            service.store.put(key,candidate.id,{'p50':1,'p95':1,'startup':1},
                semantic_status='strict',material_gain='accepted',pareto=True)
            try:
                with mock.patch.object(index,'_dense_matrix',return_value=(ids,values)):
                    service.search('scope','warm',**settings)
                    batcher=next(iter(service.batchers.values()));TracedMatrix.calls=[]
                    with batcher.condition:
                        futures=[service.submit('scope',q,**settings) for q in ('query one','query two')]
                    results=[f.result(timeout=2) for f in futures]
                self.assertEqual(TracedMatrix.calls,[6,6])
                for result in results:
                    self.assertEqual(result['runtime_receipt']['actual_batch'],2)
                    guards=result['batch_receipt']['resident_receipt']['ranking_guards']
                    self.assertTrue(all(g['verification']=='admitted-cutoff' for g in guards))
            finally:
                service.close();index.close()
