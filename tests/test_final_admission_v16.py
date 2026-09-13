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


if __name__=='__main__':unittest.main()
