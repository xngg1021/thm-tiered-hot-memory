from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.physical.segments import export,current
from thm.physical.migration import begin,resume,STAGES

class MigrationTests(unittest.TestCase):
    def test_crash_recovery_at_every_stage(self):
        for stage in STAGES:
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as d:
                root=Path(d);src=root/'src';dst=root/'dst';src.mkdir();dst.mkdir();enc=FakeEncoder()
                with closing(SearchIndex(root/'i.sqlite')) as index:
                    index.replace_scope('s',[Document('a','s','turn',0,'alpha')]);index.embed('s',enc,enc.model_id,vector_storage='blob')
                    export(index,'s',enc.profile,src)
                    before=[tuple(r) for r in index.db.execute('SELECT * FROM docs')]
                    begin(index,'s',enc.profile,dst,root/'journal',retire_source=True)
                    def crash(at):
                        if at==stage:raise RuntimeError('injected crash')
                    with self.assertRaises(RuntimeError):resume(index,root/'journal',inject=crash)
                with closing(SearchIndex(root/'i.sqlite')) as index:
                    result=resume(index,root/'journal')
                    self.assertTrue(result['published']);self.assertEqual(list(src.glob('*.seg')),[])
                    self.assertEqual(before,[tuple(r) for r in index.db.execute('SELECT * FROM docs')])
                    self.assertEqual(resume(index,root/'journal')['stage'],'complete')
    def test_default_preserves_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dst=root/'dst';dst.mkdir();enc=FakeEncoder()
            with closing(SearchIndex(root/'i.sqlite')) as index:
                index.replace_scope('s',[Document('a','s','turn',0,'alpha')]);index.embed('s',enc,enc.model_id,vector_storage='blob')
                export(index,'s',enc.profile,root);begin(index,'s',enc.profile,dst,root/'journal')
                self.assertTrue(resume(index,root/'journal')['source_valid'])
