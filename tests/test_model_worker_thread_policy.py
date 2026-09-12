"""Real encoder construction keeps thread control inside the owned model worker."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from thm.runtime.fabric import model_worker
from thm.runtime.identity import EmbeddingProfile, manifest


class ModelWorkerThreadPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'; self.source.mkdir()
        (self.source/'weights').write_bytes(b'local fixture')
        self.profile = EmbeddingProfile(manifest(self.source)['sha256'], 'torch_fp32', 'fixture', 'fp32', 3)
        self.task = {'model_source': str(self.source), 'model_id': 'fixture',
                     'reference_profile': asdict(self.profile), 'reference_threads': 4}
        self.model = mock.Mock(); self.model.get_sentence_embedding_dimension.return_value = 3
        self.factory = mock.Mock(return_value=self.model)
        self.torch = types.SimpleNamespace(set_num_threads=mock.Mock())
        modules = {'torch': self.torch,
                   'sentence_transformers': types.SimpleNamespace(SentenceTransformer=self.factory),
                   'onnxruntime': types.SimpleNamespace(SessionOptions=types.SimpleNamespace,
                                                        get_available_providers=lambda: ['CPUExecutionProvider'])}
        patches = [mock.patch.dict(sys.modules, modules), mock.patch.object(sys, 'platform', 'darwin'),
                   mock.patch('thm.runtime.backends.versions', return_value={
                       'torch': 'fixture', 'onnxruntime': 'fixture', 'openvino': 'fixture'}),
                   mock.patch('subprocess.Popen', side_effect=AssertionError('nested worker launched'))]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)

    def test_darwin_baseline_constructs_before_candidate_preparation(self):
        class CandidateReached(Exception):
            pass
        source, replica = mock.Mock(), mock.Mock()
        source.db.execute.return_value.fetchone.return_value = ('generation',)
        task = {**self.task, 'workspace': str(self.root), 'db': 'fixture.sqlite',
                'counter': 'utf8_bytes', 'scope': 'scope', 'generation': 'generation'}
        with mock.patch('thm.retrieval.SearchIndex', side_effect=[source, replica]), \
             mock.patch.object(model_worker, 'prepare_encoder', side_effect=CandidateReached):
            with self.assertRaises(CandidateReached):
                model_worker.run(task, mock.Mock())
        self.factory.assert_called_once()
        self.torch.set_num_threads.assert_called_once_with(4)
        source.close.assert_called_once(); replica.close.assert_called_once()

    def test_darwin_ort_and_openvino_candidates_keep_explicit_thread_options(self):
        for provider_name, class_name in [('onnxruntime.cpu', 'OrtInference'),
                                           ('intel.openvino.cpu', 'OpenVINOInference')]:
            with self.subTest(provider=provider_name):
                workspace = self.root/class_name; workspace.mkdir()
                provider = type(class_name, (), {})()
                provider.spec = types.SimpleNamespace(options={'ep': 'CPUExecutionProvider', 'device': 'CPU'})
                registry = mock.Mock(); registry.get.return_value = provider
                def convert(config):
                    target = Path(config['staging']); target.mkdir()
                    (target/'model').write_bytes(b'compiled fixture')
                    receipt = {'status': 'prepared', 'backend': config['backend'], 'precision': 'fp32',
                               'source_manifest_sha256': config['source_manifest_sha256'],
                               'derived_manifest_sha256': manifest(target)['sha256'],
                               'transformation': 'fixture', 'model_file': 'model', 'converter_versions': {}}
                    (target/'thm-preparation.json').write_text(json.dumps(receipt))
                    return receipt
                with mock.patch('thm.runtime.fabric.registry.builtin_registry', return_value=registry), \
                     mock.patch('thm.runtime.prepare.convert', side_effect=convert):
                    encoder = model_worker.prepare_encoder({**self.task, 'inference_provider': provider_name}, workspace)
                self.assertEqual(encoder.runtime_identity()['threads'], 1)
                options = self.factory.call_args.kwargs['model_kwargs']
                if class_name == 'OrtInference':
                    self.assertEqual(options['session_options'].intra_op_num_threads, 1)
                else:
                    self.assertEqual(options['ov_config']['INFERENCE_NUM_THREADS'], 1)
                encoder.close(); self.assertIsNone(encoder.model)
                registry.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
