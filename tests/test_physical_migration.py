from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.physical.segments import export,current
from thm.physical.migration import begin,resume,STAGES

class MigrationTests(unittest.TestCase):
    def test_exclusive_roots_reject_other_indexes_with_identical_objects(self):
        from thm.physical.segments import load
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';shared=root/'shared';src.mkdir();shared.mkdir();enc=FakeEncoder()
            with closing(SearchIndex(root/'a.sqlite')) as a,closing(SearchIndex(root/'b.sqlite')) as b:
                for index,folder in ((a,src),(b,shared)):
                    index.replace_scope('s',[Document('a','s','turn',0,'alpha')]);index.embed('s',enc,enc.model_id)
                    export(index,'s',enc.profile,folder)
                first=current(a,'s',enc.profile.id);second=current(b,'s',enc.profile.id)
                self.assertEqual(first['object_sha256'],second['object_sha256'])
                with self.assertRaisesRegex(ValueError,'different index'):
                    begin(a,'s',enc.profile,shared,root/'journal',retire_source=True)
                with self.assertRaisesRegex(ValueError,'different index'):
                    export(a,'s',enc.profile,shared)
                self.assertFalse((root/'journal').exists())
                self.assertEqual(current(b,'s',enc.profile.id),second)
                self.assertIsNotNone(load(b,'s',enc.profile,second['generation']))
                # A copied/rewritten database cannot acquire publication rights
                # simply by copying another index's placement manifest.
                import json
                a.db.execute('UPDATE physical_placements SET manifest=?',(json.dumps(second),))
                a.db.commit()
                with self.assertRaisesRegex(ValueError,'different index'):
                    load(a,'s',enc.profile,second['generation'])

    def test_legacy_shared_root_allows_copy_but_refuses_retirement(self):
        import json
        from thm.physical.segments import OWNER_FILE,SCHEMA,load
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);shared=root/'shared';dst=root/'dst';shared.mkdir();dst.mkdir();enc=FakeEncoder()
            with closing(SearchIndex(root/'a.sqlite')) as a,closing(SearchIndex(root/'b.sqlite')) as b:
                for index in (a,b):
                    index.replace_scope('s',[Document('a','s','turn',0,'alpha')]);index.embed('s',enc,enc.model_id)
                export(a,'s',enc.profile,shared)
                manifest=current(a,'s',enc.profile.id)
                # Simulate pre-ownership shared publications from the old format.
                (shared/OWNER_FILE).unlink()
                b.db.execute(SCHEMA)
                b.db.execute('INSERT INTO physical_placements VALUES(?,?,?,?)',('s',enc.profile.id,manifest['generation'],json.dumps(manifest)))
                b.db.commit()
                with self.assertRaisesRegex(ValueError,'ownership unverified'):
                    begin(b,'s',enc.profile,dst,root/'retire',retire_source=True)
                with self.assertRaisesRegex(ValueError,'fresh exclusive'):
                    export(b,'s',enc.profile,shared)
                begin(b,'s',enc.profile,dst,root/'copy')
                self.assertTrue(resume(b,root/'copy')['source_valid'])
                self.assertIsNotNone(load(a,'s',enc.profile,manifest['generation']))
                self.assertIsNotNone(load(b,'s',enc.profile,manifest['generation']))

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
