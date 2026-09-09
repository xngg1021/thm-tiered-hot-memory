from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from thm.retrieval import SearchIndex,Document
from thm.runtime.testing import FakeEncoder
from thm.runtime.profiles import RuntimeProfile
from thm.runtime.scheduler import RuntimeScheduler
from thm.physical.segments import export
from thm.physical.execution import ExecutionPlanner

class ExecutionTests(unittest.TestCase):
    def test_explicit_plan_execute_and_stale(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);enc=FakeEncoder()
            with closing(SearchIndex(root/'i.sqlite')) as index:
                index.replace_scope('s',[Document('a','s','s',0,'alpha')]);index.embed('s',enc,enc.model_id,vector_storage='blob')
                export(index,'s',enc.profile,root)
                p=RuntimeProfile(enc.profile.id,'fixture',backend=enc.profile.backend,semantic_gate='strict',policy='auto-safe')
                with RuntimeScheduler(index,[p],{enc.profile.id:enc},verify_fresh=False) as scheduler:
                    planner=ExecutionPlanner(scheduler);plan=planner.plan('s')
                    result=planner.execute(plan,'s','alpha',mode='dense')
                    self.assertEqual(result['execution_plan']['representation'],'immutable-segment')
                    self.assertIsNone(result['execution_plan']['actual_fallback'])
                    index.replace_scope('s',[Document('b','s','s',0,'changed')])
                    with self.assertRaises(ValueError):planner.execute(plan,'s','alpha',mode='dense')
