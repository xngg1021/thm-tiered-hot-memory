from dataclasses import replace
import unittest
from thm.physical.contracts import *
from thm.physical.planner import plan

class PlannerTests(unittest.TestCase):
    def test_constraints_and_stable_ties(self):
        a=StorageTarget('a',free_capacity=100,readonly=False,remote=False,adapter='local-filesystem')
        b=replace(a,target_id='b');intent=PlacementIntent(DataRole.VECTOR_SEGMENT,capacity_required=10)
        def profile(t):return StorageProfile(t.fingerprint,({'operation':'buffered-random','size':4096,'concurrency':1,'p95_ms':1.,'bytes_per_second':1000.},),1024,1.)
        result=plan(intent,[b,a],[profile(a),profile(b)])
        self.assertEqual(result['selected_target'],'a')
        for t in (replace(a,readonly=True),replace(a,remote=True),replace(a,free_capacity=0),replace(a,adapter='unavailable')):
            self.assertIsNone(plan(intent,[t],[profile(t)])['selected_target'])
        for change in ({'minimum_replicas':2},{'p95_latency_ms':.1},{'failure_domain':'x'},{'workload':'archive'}):
            self.assertIsNone(plan(replace(intent,**change),[a],[profile(a)])['selected_target'])
        self.assertIsNone(plan(intent,[a],[])['selected_target'])
