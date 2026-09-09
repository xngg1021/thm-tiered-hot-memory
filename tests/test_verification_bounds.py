import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from research.runtime.bounds import campaign, estimate, ReferenceArtifactKey, reuse

class BoundsTests(unittest.TestCase):
    def test_semantic_manifest_transitive_closure_and_exclusions(self):
        import shutil
        from research.runtime.bounds import semantic_identity
        from research.runtime.reference_dependencies import semantic_manifest
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for folder in ('thm','research'):
                shutil.copytree(source/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__','*.json','*.jsonl','.cache'))
            manifest=semantic_manifest(root)
            required={'thm/sources.py','research/recall/scoring.py','thm/sqlite_guard.py',
                      'thm/runtime/isolated.py','thm/runtime/worker.py','thm/runtime/scorers.py',
                      'thm/runtime/profiles.py','thm/runtime/backends/__init__.py',
                      'thm/retrieval.py','thm/features.py','thm/entities.py'}
            self.assertTrue(required<=manifest.keys())
            self.assertEqual(list(manifest),sorted(manifest))
            original=semantic_identity(root)
            key=ReferenceArtifactKey('d','m',{}, {}, original, {})
            for name in manifest:
                with self.subTest(semantic=name):
                    path=root/name;before=path.read_bytes()
                    path.write_bytes(before+b'\n# semantic mutation\n')
                    self.assertNotEqual(dataclasses.replace(key,semantic_implementation=semantic_identity(root)).id,key.id)
                    path.write_bytes(before)
            for name in ('docs/README.md','thm/physical/probe.py','thm/physical/benchmark.py',
                         'thm/physical/planner.py','thm/runtime/scheduler.py'):
                with self.subTest(nonsemantic=name):
                    self.assertNotIn(name,manifest)
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text('# unrelated change\n')
                    self.assertEqual(semantic_identity(root),original)
            # Future semantic dependencies must be followed, including relative
            # from-package imports and their package initializers.
            path=root/'thm/sources.py'
            path.write_bytes(path.read_bytes()+b'\nfrom . import future_semantics\n')
            future=root/'thm/future_semantics.py';future.write_text('VALUE = 1\n')
            changed=semantic_identity(root)
            self.assertIn('thm/future_semantics.py',semantic_manifest(root))
            future.write_text('VALUE = 2\n')
            self.assertNotEqual(semantic_identity(root),changed)
            path.write_bytes(path.read_bytes()+b'\nimport thm.missing_semantics\n')
            with self.assertRaisesRegex(ValueError,'unresolved reference dependency'):
                semantic_identity(root)

    def test_counter_package_identity_invalidates_reuse(self):
        from unittest.mock import patch
        from research.runtime.bounds import counter_identity
        with patch('importlib.metadata.version',return_value='1'):
            key=ReferenceArtifactKey('d','m',{}, {}, 's',counter_identity('cl100k_base'))
        with patch('importlib.metadata.version',return_value='2'):
            self.assertNotEqual(key.id,dataclasses.replace(key,counter_identity=counter_identity('cl100k_base')).id)

    def test_modes(self):
        self.assertEqual(campaign()['lme_limit'],5)
        self.assertEqual(campaign('smoke')['lme_limit'],2)
        for kw in ({'mode':'full-research'},{'full_campaign':True},{'retrieval_ab':True}):
            with self.assertRaises(ValueError):campaign(**kw)
        self.assertIsNone(campaign(full_campaign=True,acknowledge=True)['lme_limit'])
        self.assertFalse(estimate(150,5,500,4,3600)['within_budget'])
    def test_reuse(self):
        key=ReferenceArtifactKey('d','m',{'profile':'p'},{'policy':'reference'},'s',{'counter':'c'})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ref.json';p.write_text('{}')
            p.with_suffix('.reference.json').write_text(json.dumps({'key':dataclasses.asdict(key),'key_id':key.id,
                'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'returncode':0,'provenance':{'git_head':'x'}}))
            self.assertTrue(reuse(p,key)[1]['reused'])
            with self.assertRaises(ValueError):reuse(p,dataclasses.replace(key,semantic_implementation='new'))
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):reuse(p,key)
    def test_whole_process_budget_and_existing_namespace(self):
        import sys
        from research.runtime.bounds import bounded_process
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'run'
            self.assertEqual(bounded_process([sys.executable,'-c','import time;time.sleep(5)'],.1,root),124)
            self.assertFalse(json.loads((root/'interrupted.json').read_text())['full_dataset_acceptance'])
            before=list(root.iterdir())
            with self.assertRaises(FileExistsError):bounded_process([sys.executable,'-c','pass'],1,root)
            self.assertEqual(before,list(root.iterdir()))
    def test_nonfinite_budget_refused(self):
        for seconds in (float('inf'),float('nan'),-1,0):
            with self.assertRaises(ValueError):campaign(wall_seconds=seconds)
