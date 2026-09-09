"""Strict-ranking regressions: provider output never certifies omitted source rows."""
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
    def test_admitted_resident_queries_use_complete_independent_reference(self):
        registry = builtin_registry(extensions=False); executor = ResidentExecutor(registry)
        values=matrix(); ids=list(range(1,len(values)+1)); query=[1.]+[0.]*7
        executor.admission=('g','p'); TracedMatrix.calls=[]
        try:
            rows,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=ids,
                matrix=values,queries=[query,query],top_k=5)
            self.assertEqual(rows[0][0],[1,2,3,4,5])
            self.assertTrue(receipt['strict_verified'])
            self.assertTrue(all(g['verification']=='reference-fallback' for g in receipt['ranking_guards']))
            self.assertTrue(all(g['reference_full_scans']==1 for g in receipt['ranking_guards']))
            self.assertEqual(TracedMatrix.calls,[500,500])
        finally:
            executor.close();registry.close()

    def test_provider_can_omit_true_top_row_without_fooling_guard(self):
        registry=builtin_registry(extensions=False); executor=ResidentExecutor(registry)
        values=matrix(64); ids=list(range(1,65)); executor.admission=('g','p'); TracedMatrix.calls=[]
        provider=registry.get('host.exact')
        original=provider.search
        try:
            # Internally sorted and numerically plausible, but row 1 is omitted.
            def broken(handle, query_vectors, top_k):
                result,receipt=original(handle,query_vectors,min(top_k+1,len(handle.ids)))
                bad=[]
                for ranked,scores in result:
                    bad.append((ranked[1:top_k+1],scores[1:top_k+1]))
                return bad,receipt
            provider.search=broken
            rows,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=ids,
                matrix=values,queries=[[1.]+[0.]*7],top_k=5)
            self.assertEqual(rows[0][0],[1,2,3,4,5])
            guard=receipt['ranking_guards'][0]
            self.assertFalse(guard['provider_matches_reference'])
            self.assertEqual(guard['verification'],'reference-fallback')
            self.assertEqual(TracedMatrix.calls,[64])
        finally:
            provider.search=original; executor.close(); registry.close()

    def test_ties_and_unverified_accumulation_still_use_reference(self):
        registry=builtin_registry(extensions=False);executor=ResidentExecutor(registry)
        values=matrix();values[1]=values[0];executor.admission=('g','p');TracedMatrix.calls=[]
        try:
            rows,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=list(range(500)),
                matrix=values,queries=[[1.]+[0.]*7],top_k=1)
            self.assertEqual(rows[0][0],[0])
            self.assertEqual(receipt['ranking_guards'][0]['reference_full_scans'],1)
            self.assertEqual(TracedMatrix.calls,[500])
            registry.get('host.exact').fp32_accumulation=lambda:False
            TracedMatrix.calls=[]
            _,receipt=executor.search(scope='s',generation='g',embedding_profile='p',ids=list(range(500)),
                matrix=values,queries=[[1.]+[0.]*7],top_k=5)
            self.assertFalse(receipt['ranking_guards'][0]['provider_matches_reference'])
            self.assertEqual(TracedMatrix.calls,[500])
        finally:
            executor.close();registry.close()

    def test_session_pinned_online_cohort_reports_reference_execution(self):
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
                self.assertEqual(TracedMatrix.calls,[500,500])
                for result in results:
                    self.assertEqual(result['runtime_receipt']['actual_batch'],2)
                    self.assertEqual(result['runtime_receipt']['actual_provider'],'reference')
                    self.assertTrue(result['runtime_receipt']['fallback'].startswith('index-guard:'))
                    guards=result['batch_receipt']['resident_receipt']['ranking_guards']
                    self.assertTrue(all(g['verification']=='reference-fallback' for g in guards))
            finally:
                service.close();index.close()


if __name__ == '__main__':
    unittest.main()
