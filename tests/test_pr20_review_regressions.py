"""Exact regressions for the final PR #20 Codex resource/identity findings."""
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import threading
import unittest
from unittest import mock

import numpy as np

from thm.runtime.fabric.explorer import BoundedShadowExplorer
from thm.runtime.fabric.models import WarmModelWorker
from thm.runtime.fabric.registry import builtin_registry
from thm.runtime.fabric.resources import ChildBudget
from thm.runtime.fabric.service import ResidentExecutor, RuntimeService


class ResidentSnapshotTests(unittest.TestCase):
    def test_same_generation_republished_vectors_do_not_reuse_stale_handle(self):
        registry = builtin_registry(extensions=False)
        executor = ResidentExecutor(registry)
        first = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        second = np.asarray([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
        kwargs = dict(scope='scope', generation='same-generation', embedding_profile='profile',
                      ids=[1, 2], queries=[[1.0, 0.0]], top_k=1)
        try:
            rows1, receipt1 = executor.search(matrix=first, **kwargs)
            rows2, receipt2 = executor.search(matrix=second, **kwargs)
            rows3, receipt3 = executor.search(matrix=second, **kwargs)
            self.assertEqual(rows1[0][0], [1])
            self.assertEqual(rows2[0][0], [2])
            self.assertEqual(rows3[0][0], [2])
            self.assertFalse(receipt1['resident_hit'])
            self.assertFalse(receipt2['resident_hit'])
            self.assertTrue(receipt3['resident_hit'])
            self.assertNotEqual(receipt1['vector_snapshot_revision'], receipt2['vector_snapshot_revision'])
            self.assertEqual(receipt2['vector_snapshot_revision'], receipt3['vector_snapshot_revision'])
        finally:
            executor.close(); registry.close()


class DiscoveryFreshnessTests(unittest.TestCase):
    def test_hnsw_discovery_binds_dependency_version(self):
        service = RuntimeService.__new__(RuntimeService)
        service.lock = threading.RLock(); service.closed = False
        service.discovery_cursor = 0; service.discovery_done = False; service.discovery = {}
        service.discovery_epoch = 'epoch'; service.policy = 'approximate-performance'
        service.candidates = []; service.models = mock.Mock()
        service.graph = SimpleNamespace(nodes=[], edges=[])
        service.registry = mock.Mock()
        service.registry.describe.return_value = {
            'versions': {'hnswlib': '0.8.0'}, 'options': (), 'vendor': 'generic'
        }
        RuntimeService._discovered(service, {'next_cursor': 1, 'done': False, 'providers': [{
            'provider': 'host.hnsw', 'availability': 'available', 'version': None,
            'driver_runtime': None, 'devices': ['cpu']
        }]})
        observed = service.discovery['host.hnsw']
        self.assertEqual(observed['version'], '0.8.0')
        self.assertEqual(observed['dependency_versions'], {'hnswlib': '0.8.0'})
        self.assertNotIn('freshness_epoch', observed)


class PreemptionTests(unittest.TestCase):
    def test_preempt_before_child_publication_is_sticky(self):
        explorer = BoundedShadowExplorer()
        pending = mock.Mock(); pending.is_alive.return_value = True
        explorer.thread = pending
        explorer.preempt()
        self.assertTrue(explorer.preempted)
        callbacks = []
        with mock.patch('thm.runtime.fabric.explorer.subprocess.Popen',
                        side_effect=AssertionError('preempted child must not launch')):
            explorer._run({'operation': 'probe'}, callbacks.append)
        self.assertEqual(callbacks[0]['status'], 'deferred')
        self.assertEqual(callbacks[0]['reason'], 'foreground-pressure')
        self.assertIsNone(explorer.process)


class ModelBudgetTests(unittest.TestCase):
    def test_successful_response_is_rechecked_before_acceptance(self):
        worker = WarmModelWorker({}, memory=1024, cpu=1, io=1024, wall=1)
        budget = mock.Mock()
        budget.check.side_effect = [None, RuntimeError('tree budget exceeded')]
        worker.budget = budget
        worker.responses.put({'status': 'ok', 'value': 1})
        try:
            with self.assertRaisesRegex(RuntimeError, 'tree budget exceeded'):
                worker._receive(1)
            self.assertEqual(budget.check.call_count, 2)
        finally:
            worker.workspace.cleanup()

    def test_successful_response_requires_lifetime_evidence_gate(self):
        worker = WarmModelWorker({}, memory=1024, cpu=1, io=1024, wall=1)
        budget = mock.Mock()
        worker.budget = budget
        lifetime = {'source': 'linux-getrusage-self-children+proc-self-io'}
        worker.responses.put({'status': 'ok', 'value': 1, '_resource_lifetime': lifetime})
        try:
            self.assertEqual(worker._receive(1), {'status': 'ok', 'value': 1})
            budget.check_lifetime.assert_called_once_with(lifetime)
        finally:
            worker.workspace.cleanup()


class LinuxTreeBudgetTests(unittest.TestCase):
    @staticmethod
    def _proc(root, pid, pgrp, rss_kib, utime, stime, read, written):
        target = root / str(pid); target.mkdir()
        target.joinpath('stat').write_text(
            f'{pid} (worker {pid}) S 1 {pgrp} {pgrp} 0 0 0 0 0 0 0 {utime} {stime}\n')
        target.joinpath('status').write_text(f'Name:\tworker\nVmRSS:\t{rss_kib} kB\n')
        target.joinpath('io').write_text(f'rchar: {read}\nwchar: {written}\n')

    @staticmethod
    def _budget():
        budget = ChildBudget.__new__(ChildBudget)
        budget.process = SimpleNamespace(pid=100, poll=lambda: None)
        budget.memory = 10**9; budget.cpu = 100; budget.io = 10**9
        budget.job = None; budget.last = {}; budget.pgid = 100
        return budget

    def test_linux_accounting_aggregates_helper_process_group(self):
        budget = self._budget()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._proc(root, 100, 100, 100, 10, 5, 10, 20)
            self._proc(root, 101, 100, 200, 20, 10, 30, 40)
            self._proc(root, 102, 999, 900, 90, 90, 900, 900)
            with mock.patch.object(os, 'sysconf', return_value=100, create=True):
                observed = budget._linux_usage(root, pgid=100)
        self.assertEqual(observed['processes'], 2)
        self.assertEqual(observed['ram_bytes'], 300 * 1024)
        self.assertAlmostEqual(observed['cpu_seconds'], .45)
        self.assertEqual(observed['bytes_read'], 40)
        self.assertEqual(observed['bytes_written'], 60)
        self.assertEqual(observed['resource_source'], 'procfs-process-group-live')

    def test_reaped_helper_activity_fails_closed_in_lifetime_gate(self):
        budget = self._budget()
        evidence = {
            'source': 'linux-getrusage-self-children+proc-self-io',
            'self_cpu_seconds': .2, 'self_maxrss_bytes': 1024,
            'self_bytes_read': 10, 'self_bytes_written': 20,
            'child_cpu_seconds': .01, 'child_maxrss_bytes': 2048,
            'child_block_reads': 0, 'child_block_writes': 0,
            'child_activity': True,
        }
        with mock.patch('thm.runtime.fabric.resources.sys.platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'reaped-helper'):
                budget.check_lifetime(evidence)
        self.assertTrue(budget.last['reaped_child_activity'])

    def test_missing_linux_lifetime_evidence_fails_closed(self):
        budget = self._budget()
        with mock.patch('thm.runtime.fabric.resources.sys.platform', 'linux'):
            with self.assertRaisesRegex(RuntimeError, 'lifetime resource evidence missing'):
                budget.check_lifetime(None)

    def test_leader_exit_between_proc_sample_and_poll_is_not_a_helper(self):
        budget = self._budget()
        budget.process = SimpleNamespace(pid=100, poll=lambda: 0)
        observed = {'ram_bytes': 1, 'cpu_seconds': 0, 'bytes_read': 0,
                    'bytes_written': 0, 'processes': 1}
        with mock.patch('sys.platform', 'linux'), mock.patch.object(
                budget, '_linux_usage', side_effect=[observed, None]) as scan:
            budget.check()
        self.assertEqual(scan.call_count, 2)

    def test_surviving_helper_after_leader_exit_fails_closed(self):
        budget = self._budget()
        budget.process = SimpleNamespace(pid=100, poll=lambda: 0)
        observed = {'ram_bytes': 1, 'cpu_seconds': 0, 'bytes_read': 0, 'bytes_written': 0,
                    'processes': 1, 'resource_source': 'procfs-process-group-live'}
        with mock.patch('thm.runtime.fabric.resources.sys.platform', 'linux'), \
             mock.patch.object(budget, '_linux_usage', return_value=observed):
            with self.assertRaisesRegex(RuntimeError, 'helper survived'):
                budget.check()


if __name__ == '__main__':
    unittest.main()
