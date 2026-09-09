"""Bounded model lifecycle tests using explicit local fixtures, no vendor claims."""
from dataclasses import asdict, replace
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from thm.retrieval import SearchIndex, TokenCounter
from thm.runtime.identity import manifest
from thm.runtime.testing import FakeEncoder
from thm.runtime.fabric.models import WarmModelWorker
from thm.runtime.fabric.service import RuntimeService
from thm.runtime.fabric.shadow_worker import signature
from test_provider_fabric import documents


class ModelFabricTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.bundle = self.root/'source'; self.bundle.mkdir()
        (self.bundle/'weights').write_bytes(b'tiny immutable test model')
        self.encoder = FakeEncoder()
        self.encoder.profile = replace(self.encoder.profile,backend='torch_fp32',
                                       source_manifest_sha256=manifest(self.bundle)['sha256'])
        self.encoder.local_model_source = str(self.bundle)
        self.index = SearchIndex(self.root/'source.sqlite',TokenCounter()); self.addCleanup(self.index.close)
        self.index.replace_scope('scope',documents()); self.index.embed('scope',self.encoder,self.encoder.model_id)

    def clone_encoder(self, backend):
        encoder = FakeEncoder(); encoder.profile = replace(self.encoder.profile,backend=backend)
        return encoder

    def model_proof(self, service, key, generation):
        reference = self.index.search('scope','Beijing',encoder=self.encoder,model_id=self.encoder.model_id,mode='dense',diagnostics=True)
        profile = replace(self.encoder.profile,backend='fixture-native',device='cuda').identity()
        proof = {'generation':generation,'reference':signature(reference),'result':signature(reference),
            'baseline':[10]*5,'candidate':[1]*5,'cpu_samples':{'baseline':[.01]*5,'candidate':[.001]*5},
            'startup_ms':2,'embedding_profile':profile,'vram_bytes':100}
        worker = mock.Mock(); worker.preempted = False; worker.prepare.return_value = proof
        worker.memory = 1024; worker.budget.last = {'ram_bytes':100}
        worker.task = {'generation':generation}
        worker.search.return_value = {'results':[reference],'cpu_seconds':.002,'embedding_profile':profile}
        description = service.registry.describe('nvidia.inference')
        service.models.add('nvidia.inference',description,{'availability':'available'})
        return worker, profile, reference

    def test_private_reindex_keeps_source_authority_and_serves_new_profile(self):
        from thm.runtime.fabric.model_worker import run
        target = self.root/'private'; target.mkdir()
        generation = self.index.db.execute('SELECT generation FROM scopes').fetchone()[0]
        task = {'db':str(self.index.path),'counter':'utf8_bytes','scope':'scope','generation':generation,
                'workspace':str(target),'model_source':str(self.bundle),'model_id':self.encoder.model_id,
                'reference_profile':asdict(self.encoder.profile),'query':'Beijing','settings':{'mode':'dense'},
                'inference_provider':'fixture'}
        import json
        replies = []
        with mock.patch('thm.runtime.backends.create',side_effect=lambda *a,**k:self.clone_encoder('torch_fp32')), \
             mock.patch('thm.runtime.fabric.model_worker.prepare_encoder',side_effect=lambda *a:self.clone_encoder('fixture-device')), \
             mock.patch.dict(sys.modules,{'torch':types.SimpleNamespace(set_num_threads=lambda n:None)}), \
             mock.patch('sys.stdin',io.StringIO(json.dumps({'queries':['Beijing'],'generation':generation})+'\n')):
            run(task,replies.append)
        self.assertEqual(replies[0]['status'],'ready')
        self.assertEqual(replies[0]['reference'],replies[0]['result'])
        self.assertEqual(len(replies[0]['candidate']),5)
        self.assertNotEqual(replies[0]['embedding_profile']['embedding_profile_id'],self.encoder.profile.id)
        self.assertEqual(replies[1]['results'][0]['generation'],generation)
        stored = self.index.db.execute('SELECT profile FROM embedding_profiles').fetchall()
        self.assertEqual([r[0] for r in stored],[self.encoder.profile.id])
        self.assertEqual(manifest(self.bundle)['sha256'],self.encoder.profile.source_manifest_sha256)

    def test_explicit_approximate_admission_waits_for_session_and_returns_actual_identity(self):
        service = RuntimeService(self.index,encoder=self.encoder,model_id=self.encoder.model_id,
                                 policy='approximate-performance',background=False)
        try:
            key,generation,_ = service._key('scope','interactive',{'mode':'dense'})
            worker, profile, reference = self.model_proof(service,key,generation)
            with mock.patch('thm.runtime.fabric.models.WarmModelWorker',return_value=worker):
                self.assertTrue(service.models.maybe_start(key,{'generation':generation}))
                service.models.thread.join(timeout=2)
            self.assertIsNotNone(service.models.ready)
            self.assertIsNone(service.models.select(key))
            service.new_session()
            result = service.search('scope','Beijing',mode='dense')
            self.assertEqual(result['runtime_receipt']['inference_provider'],'nvidia.inference')
            self.assertEqual(result['runtime_receipt']['embedding_profile'],profile['embedding_profile_id'])
            self.assertEqual(result['runtime_receipt']['authority_embedding_profile'],self.encoder.profile.id)
            self.assertEqual(result['runtime_receipt']['semantic_class'],'observed-request')
            self.assertEqual(result['execution_plan']['source_representation'],'private-profile-replica')
            worker.search.side_effect = RuntimeError('fixture device loss')
            result = service.search('scope','Beijing next',mode='dense')
            self.assertEqual(result['runtime_receipt']['actual_provider'],'reference')
            self.assertEqual(result['execution_plan']['inference_provider'],'reference')
            self.assertTrue(result['runtime_receipt']['fallback'].startswith('provider-failed'))
            self.assertIsNone(service.models.active)
        finally:
            service.close()

    def test_auto_safe_records_but_does_not_promote_observed_request_model_evidence(self):
        service = RuntimeService(self.index,encoder=self.encoder,model_id=self.encoder.model_id,background=False)
        try:
            key,generation,_ = service._key('scope','interactive',{'mode':'dense'})
            worker, _, _ = self.model_proof(service,key,generation)
            with mock.patch('thm.runtime.fabric.models.WarmModelWorker',return_value=worker):
                self.assertTrue(service.models.maybe_start(key,{'generation':generation}))
                service.models.thread.join(timeout=2)
            self.assertIsNone(service.models.ready)
            self.assertEqual(service.models.last['status'],'measured-only')
            self.assertFalse(service.models.last['automatic_activation_allowed'])
            observations = service.store.observations(key)
            self.assertEqual(observations[0]['semantic_status'],'observed-request')
            service.new_session()
            self.assertIsNone(service.models.select(key))
            worker.search.assert_not_called()
        finally:
            service.close()

    def test_auto_throughput_also_keeps_observed_request_model_evidence_nonactivating(self):
        service = RuntimeService(self.index,encoder=self.encoder,model_id=self.encoder.model_id,
                                 policy='auto-throughput',background=False)
        try:
            key,generation,_ = service._key('scope','interactive',{'mode':'dense'})
            worker, _, _ = self.model_proof(service,key,generation)
            with mock.patch('thm.runtime.fabric.models.WarmModelWorker',return_value=worker):
                self.assertTrue(service.models.maybe_start(key,{'generation':generation}))
                service.models.thread.join(timeout=2)
            self.assertIsNone(service.models.ready)
            self.assertFalse(service.models.last['automatic_activation_allowed'])
        finally:
            service.close()

    def test_real_worker_failure_closes_process_and_private_workspace(self):
        worker = WarmModelWorker({'db':'missing-index'},memory=256*1024**2,cpu=2,io=16*1024**2,wall=5)
        workspace = Path(worker.workspace.name)
        try:
            with self.assertRaises(RuntimeError):
                worker.prepare()
        finally:
            worker.close()
        self.assertIsNotNone(worker.process.poll())
        self.assertFalse(workspace.exists())


if __name__ == '__main__':
    unittest.main()
