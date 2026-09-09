import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from research.runtime.bounds import campaign, estimate, ReferenceArtifactKey, reuse

class BoundsTests(unittest.TestCase):
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
