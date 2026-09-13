import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from thm.long_tail_retrieval import LongTailSearchIndex
from thm.retrieval import Document, SearchIndex, TokenCounter
from thm.systems.concurrency import ElasticConcurrencyController, WorkItem
from thm.systems.runtime import AgentSystemsRuntime
from thm.systems.topology import TopologyEvent


class FinalAdmissionRegressions(unittest.TestCase):
    def test_hotplug_sparse_fallback_accepts_runtime_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            index=SearchIndex(Path(directory)/'index',TokenCounter('utf8_bytes'))
            index.replace_scope('s',[Document('d','s','session',0,'source evidence')])
            deadline=time.monotonic()+30
            def search(*args,**settings):
                self.assertEqual(settings['deadline'],deadline)
                runtime.event(TopologyEvent('reprobe','gpu',1))
                return {'stale':True}
            base=SimpleNamespace(index=index,lock=threading.RLock(),executors={},pinned={},search=search,close=index.close)
            runtime=AgentSystemsRuntime(base)
            try:
                result=runtime.search('s','source',deadline=deadline,budget=200)
                self.assertNotIn('stale',result)
                self.assertEqual(result['selected'][0]['id'],'d')
                self.assertEqual(result['systems_receipt']['fallback'],'topology-epoch-changed')
            finally:runtime.close()

    def test_nonadditive_ordering_is_chronological_and_exactly_counted(self):
        tokenizer=TokenCounter('utf8_bytes');tokenizer.encode=lambda text:list(text)
        for counter in (tokenizer,lambda text:len(text)):
            with tempfile.TemporaryDirectory() as directory:
                index=LongTailSearchIndex(Path(directory)/'index',counter)
                try:
                    index.replace_scope('s',[
                        Document('new','s','session',0,'new event',timestamp='2026-02-01'),
                        Document('old','s','session',1,'old event',timestamp='2026-01-01')])
                    rows=sorted(index.rows('s'),key=lambda row:row['timestamp'],reverse=True)
                    index.required_source_sets={'new':frozenset({'new','old'})}
                    context,selected,used=index._pack_candidates(rows,1000,'which was first?')
                    self.assertEqual([row['id'] for row in selected],['old','new'])
                    self.assertLess(context.index('old event'),context.index('new event'))
                    self.assertEqual(used,counter(context))
                    self.assertTrue(index.long_tail_receipt['dependencies_atomic'])
                finally:index.close()

    def test_batch_limit_spans_all_qos_queues(self):
        for limit in (1,2):
            ctrl=ElasticConcurrencyController(concurrency=8,worker_count=8,batch_size=limit)
            for qos in ('interactive','bulk','background'):
                ctrl.submit(WorkItem(qos,'p',qos,0,10),0)
            batch=ctrl.dispatch(1)
            self.assertEqual(len(batch),limit)
            self.assertEqual(ctrl.receipt()['active'],limit)
            self.assertEqual(sum(ctrl.receipt()['queue'].values()),3-limit)

    def test_background_share_uses_effective_worker_capacity(self):
        ctrl=ElasticConcurrencyController(concurrency=8,worker_count=2,batch_size=8)
        ctrl.submit(WorkItem('foreground','p','interactive',0,10),0)
        ctrl.dispatch(0)
        ctrl.submit(WorkItem('background','p','background',0,10),0)
        self.assertFalse(ctrl.dispatch(1))
        ctrl.complete('foreground',2)
        self.assertEqual(ctrl.dispatch(2)[0].identity,'background')


class EvidenceAdmissionRegressions(unittest.TestCase):
    def _git(self,root,*args):
        return subprocess.check_output(['git','-c','user.name=THM test','-c','user.email=thm-test@example.invalid',*args],
                                       cwd=root,text=True,stderr=subprocess.DEVNULL).strip()

    def _repository(self,root):
        self._git(root,'init','-b','main')
        (root/'reports').mkdir()
        (root/'reports/historical.json.gz').write_bytes(b'h'*129)
        self._git(root,'add','.');self._git(root,'commit','-m','historical evidence')
        base=self._git(root,'rev-parse','HEAD')
        self._git(root,'update-ref','refs/remotes/origin/main',base)
        return base

    def test_compressed_evidence_is_checked_without_rewriting_old_blobs(self):
        from scripts import check_evidence_storage as policy
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=self._repository(root)
            for suffix in ('json.gz','jsonl.zst','csv.bz2','tar.xz'):
                (root/('reports/new.'+suffix)).write_bytes(b'n'*129)
            self._git(root,'add','.');self._git(root,'commit','-m','new compressed artifacts')
            with patch.object(policy,'ROOT',root),patch.object(policy,'GIT_THRESHOLD',128):
                errors=policy.check(base)
            self.assertEqual(len(errors),4)
            self.assertFalse(any('historical' in error for error in errors))

    def test_entire_multicommit_change_uses_pr_push_or_new_branch_base(self):
        from scripts import check_evidence_storage as policy
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);base=self._repository(root)
            (root/'reports/new.json.gz').write_bytes(b'n'*129)
            self._git(root,'add','.');self._git(root,'commit','-m','oversized early commit')
            (root/'reports/later.json').write_text('{}')
            self._git(root,'add','.');self._git(root,'commit','-m','small final commit')
            with patch.object(policy,'ROOT',root),patch.object(policy,'GIT_THRESHOLD',128):
                for event,admission in (('pull_request',base),('push',base),('push','0'*40)):
                    with patch.dict(os.environ,THM_EVIDENCE_EVENT=event,THM_EVIDENCE_BASE=admission):
                        errors=policy.check()
                        self.assertEqual(len(errors),1)
                        self.assertIn('new.json.gz',errors[0])


class SequenceAndReplayRegressions(unittest.TestCase):
    def test_generic_ordering_expands_all_events_without_lexical_matches(self):
        from thm.long_tail import Event,EventGraph,TimeInterval
        for counter in (TokenCounter('utf8_bytes'),lambda text:len(text)):
            with tempfile.TemporaryDirectory() as directory:
                index=LongTailSearchIndex(Path(directory)/'index',counter)
                try:
                    index.replace_scope('s',[Document(key,'s','session',position,text,timestamp=date)
                        for position,(key,text,date) in enumerate([
                            ('c','cobalt wind','2026-03-01'),('a','alpine comet','2026-01-01'),('b','bronze river','2026-02-01')])])
                    rows=index.rows('s')
                    index.attach_events(EventGraph('s',[Event(row['id'],'s',row['id'],row['hash'],TimeInterval.parse(row['timestamp'])) for row in rows]))
                    for query in ('what was the order of events?','describe the sequence','顺序'):
                        result=index.search('s',query,budget=1000)
                        self.assertEqual([row['id'] for row in result['selected']],['a','b','c'])
                    self.assertEqual([row['id'] for row in index.search('s','which was first?')['selected']],['a'])
                    self.assertEqual([row['id'] for row in index.search('s','which was last?')['selected']],['c'])
                finally:index.close()

    def test_kv_reuse_waits_for_completed_producer_and_respects_user_scope(self):
        from thm.systems.simulator import AgentTaskTrace,AgentSystemsSimulator
        tasks=[AgentTaskTrace(key,user,'session',arrival,0,0,4,2,0,0,'prefix')
               for key,user,arrival in [('a','u',0),('b','u',0),('c','u',7),('d','other-user',10)]]
        rows=AgentSystemsSimulator(concurrency=2).replay(tasks,ablation=4)['rows']
        self.assertEqual([row['kv_action'] for row in rows],['recompute','recompute','reuse','recompute'])
        self.assertEqual(rows[1]['start'],0)
        self.assertEqual(rows[1]['finish'],6)
        self.assertEqual(rows[2]['prefix_available_at_start'],6)

    def test_mid_request_topology_change_extends_window_and_invalidates_prefix(self):
        from thm.systems.simulator import AgentTaskTrace,AgentSystemsSimulator
        tasks=[AgentTaskTrace('a','u','s',0,0,0,2,0,0,0,'prefix'),
               AgentTaskTrace('b','u','s',3,0,0,4,2,0,0,'prefix'),
               AgentTaskTrace('c','u','s',10,0,0,4,2,0,0,'prefix'),
               AgentTaskTrace('d','u','s',17,0,0,4,2,0,0,'prefix')]
        result=AgentSystemsSimulator(concurrency=2,topology_events=[{'time':4,'state':'lost'},{'time':7,'state':'online'}]).replay(tasks,ablation=4)
        rows=result['rows'];changed=rows[1]
        self.assertEqual(changed['kv_action'],'recompute')
        self.assertEqual(changed['finish'],9)
        self.assertEqual(changed['topology_events_during_task'],2)
        self.assertEqual(changed['topology_epoch_finish'],2)
        self.assertEqual(changed['fallback_count'],1)
        self.assertIsNone(changed['prefix_available_at_start'])
        self.assertEqual(rows[2]['kv_action'],'recompute')
        self.assertEqual(rows[3]['kv_action'],'reuse')
        self.assertEqual(result['fallback_count'],1)

    def test_thermal_scenario_scales_reported_prefill_and_tool_latency(self):
        from thm.systems.simulator import AgentTaskTrace,AgentSystemsSimulator
        task=AgentTaskTrace('t','u','s',0,1,1,2,1,3,1,'prefix')
        row=AgentSystemsSimulator(thermal_trace=[{'time':0,'service_multiplier':2}]).replay([task])['rows'][0]
        self.assertEqual(row['TTFT'],8)
        self.assertEqual(row['tool_exposed_latency'],6)
        self.assertEqual(row['task_completion_time'],18)


class EpochAndTemporalBoundaryRegressions(unittest.TestCase):
    def test_start_epoch_waits_for_atomic_fabric_and_base_update(self):
        advanced=threading.Event();release=threading.Event();called=threading.Event()
        errors=[];results=[]
        class Base:
            topology_epoch=0
            def __setattr__(self,name,value):
                if name=='topology_epoch' and threading.current_thread().name=='epoch-event':
                    advanced.set()
                    if not release.wait(2):raise TimeoutError('test release missing')
                object.__setattr__(self,name,value)
            def search(self,*args,**kwargs):
                called.set();return {'base_epoch':self.topology_epoch}
            def close(self):pass
        runtime=AgentSystemsRuntime(Base())
        def capture(action):
            try:action()
            except BaseException as error:errors.append(error)
        event=threading.Thread(name='epoch-event',target=lambda:capture(lambda:runtime.event(TopologyEvent('reprobe','gpu',1))))
        search=threading.Thread(target=lambda:capture(lambda:results.append(runtime.search('s','query'))))
        try:
            event.start();self.assertTrue(advanced.wait(1))
            search.start();self.assertFalse(called.wait(.05))
        finally:
            release.set();event.join(2)
            if search.ident is not None:search.join(2)
            runtime.close()
        self.assertFalse(errors)
        self.assertFalse(event.is_alive() or search.is_alive())
        self.assertEqual(results[0]['base_epoch'],1)
        self.assertEqual(results[0]['systems_receipt']['topology_epoch'],1)
        self.assertIsNone(results[0]['systems_receipt']['fallback'])

    def test_ordering_uses_event_dates_instead_of_publication_dates(self):
        from thm.long_tail import Event,EventGraph,TimeInterval
        tokenizer=TokenCounter('utf8_bytes');tokenizer.encode=lambda text:list(text)
        for counter in (TokenCounter('utf8_bytes'),tokenizer,lambda text:len(text)):
            with tempfile.TemporaryDirectory() as directory:
                index=LongTailSearchIndex(Path(directory)/'index',counter)
                try:
                    index.replace_scope('s',[Document('january','s','session',0,'alpine comet',timestamp='2026-03-01'),
                        Document('february','s','session',1,'bronze river',timestamp='2026-01-01')])
                    rows={row['id']:row for row in index.rows('s')}
                    index.attach_events(EventGraph('s',[Event(key,'s',key,rows[key]['hash'],TimeInterval.parse(date))
                        for key,date in [('january','2026-01-01'),('february','2026-02-01')]]))
                    result=index.search('s','describe the sequence',budget=1000)
                    self.assertEqual([row['id'] for row in result['selected']],['january','february'])
                    self.assertEqual(result['long_tail']['ordering_basis'],'event-interval')
                    self.assertEqual(result['long_tail']['ordering_granularity'],'complete-source-block')
                finally:index.close()

    def test_two_sided_temporal_queries_intersect_strict_bounds(self):
        from thm.long_tail import Event,EventGraph,TimeInterval
        with tempfile.TemporaryDirectory() as directory:
            index=LongTailSearchIndex(Path(directory)/'index',TokenCounter('utf8_bytes'))
            try:
                dates=['2025-12-31','2026-01-01','2026-02-01','2026-03-01','2026-04-01']
                index.replace_scope('s',[Document(str(i),'s','session',i,'alpine comet') for i in range(len(dates))])
                rows={row['id']:row for row in index.rows('s')}
                index.attach_events(EventGraph('s',[Event(str(i),'s',str(i),rows[str(i)]['hash'],TimeInterval.parse(date))
                    for i,date in enumerate(dates)]))
                for query in ('events after 2026-01-01 and before 2026-03-01',
                              'events before 2026-03-01 and after 2026-01-01',
                              '2026-01-01之后，2026-03-01之前'):
                    result=index.search('s',query,budget=1000)
                    self.assertEqual([row['id'] for row in result['selected']],['2'])
                for query,expected in [('2026-03-01之前',{'0','1','2'}),('2026-01-01之后',{'2','3','4'})]:
                    result=index.search('s',query,budget=1000)
                    self.assertEqual({row['id'] for row in result['selected']},expected)
                with self.assertRaisesRegex(ValueError,'two-sided'):
                    index.search('s','after 2026-03-01 and before 2026-01-01')
            finally:index.close()


if __name__=='__main__':unittest.main()
