import copy
from dataclasses import replace
from datetime import date
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest

from thm.actuator import ActuatorPolicy, ResidencyActuator, ResidencyPlacementStore
from thm.physical.backends import BackendConfig, FAMILIES, FixtureTransport, MountedFilesystemTransport, StorageBackend
from thm.physical.contracts import TransferExtent
from thm.runtime.fabric.extensions import ExtensionConfig, ExtensionSession, FunctionBinding
from thm.runtime.fabric.registry import ProviderUnavailable


class ExtensionTests(unittest.TestCase):
    def session(self, **changes):
        cfg = ExtensionConfig('fixture', 'g1', hashlib.sha256(b'model').hexdigest(), 'sdk', '1', 'private-device',
                              evidence='fixture-validated', **changes)
        binding = FunctionBinding(operations=('transfer',), prepare=lambda x, c: bytes(x),
                                  compile=lambda a, c: a, load=lambda a, c: a,
                                  execute=lambda h, op, x: bytes(reversed(x)), close=lambda: None)
        session = ExtensionSession(cfg, binding)
        self.addCleanup(session.close)
        return session

    def test_complete_lifecycle_and_private_receipt(self):
        s = self.session()
        with self.assertRaises(ValueError):
            s.load()
        s.prepare(b'model'); s.compile(); s.load()
        self.assertEqual(s.execute('transfer', b'abc', generation='g1'), b'cba')
        r = s.receipt()
        self.assertNotIn('private-device', str(r))
        self.assertFalse(r['hardware_accepted'])
        s.close()
        self.assertEqual(s.receipt()['state'], 'closed')

    def test_source_and_generation_binding(self):
        s = self.session()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            s.prepare(b'wrong')
        s.prepare(b'model'); s.compile(); s.load()
        with self.assertRaises(ProviderUnavailable):
            s.execute('transfer', b'a', generation='g2')
        self.assertEqual(s.state, 'invalidated')

    def test_output_limit_quarantines_and_does_not_publish(self):
        s = self.session(max_output_bytes=1)
        s.prepare(b'model'); s.compile(); s.load()
        with self.assertRaises(MemoryError):
            s.execute('transfer', b'ab', generation='g1')
        self.assertEqual(s.state, 'quarantined')
        self.assertIsNone(s.handle)

    def test_close_execute_race_is_serial(self):
        s = self.session()
        s.prepare(b'model'); s.compile(); s.load()
        entered, release = threading.Event(), threading.Event()
        def call(h, op, x):
            entered.set(); release.wait(2); return x
        s.binding.execute = call
        worker = threading.Thread(target=lambda: s.execute('transfer', b'a', generation='g1'))
        worker.start(); self.assertTrue(entered.wait(2))
        closer = threading.Thread(target=s.close); closer.start()
        release.set(); worker.join(3); closer.join(3)
        self.assertFalse(worker.is_alive() or closer.is_alive())
        self.assertEqual(s.state, 'closed')


class StorageTests(unittest.TestCase):
    def test_every_family_executes_transaction_extent_recovery(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                b = StorageBackend(BackendConfig(family, 'private-target', 'g'), FixtureTransport())
                key = b.write(b'abcdef', generation='g')
                self.assertEqual(b.read(TransferExtent(key, 1, 3), generation='g'), b'bcd')
                self.assertTrue(b.recover(key, generation='g')['verified'])
                self.assertEqual(b.receipt()['evidence'], 'fixture-validated')
                self.assertNotIn('private-target', str(b.receipt()))
                b.close()

    def test_commit_failure_remains_indeterminate_without_write_credit(self):
        t = FixtureTransport(); t.fail_at = 'commit'
        b = StorageBackend(BackendConfig('spdk', 'target', 'g'), t)
        self.addCleanup(b.close)
        with self.assertRaises(OSError):
            b.write(b'payload', generation='g')
        self.assertFalse(b.verify(hashlib.sha256(b'payload').hexdigest()))
        self.assertEqual(b.bytes_written, 0)
        self.assertEqual(b.journal[-1]['state'], 'indeterminate-commit')

    def test_corruption_and_generation_fail_closed(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            b = StorageBackend(BackendConfig('cxl-type3', 'target', 'g'), MountedFilesystemTransport(tmp))
            cleanup.callback(b.close)
            key = hashlib.sha256(b'abc').hexdigest()
            (Path(tmp) / (key + '.seg')).write_bytes(b'abc')
            with self.assertRaises(ValueError):
                b.read(TransferExtent(key, 0, 1), generation='old')
            (Path(tmp) / (key + '.seg')).write_bytes(b'xyz')
            with self.assertRaises(ValueError):
                b.read(TransferExtent(key, 0, 1), generation='g')
            self.assertEqual(b.state, 'quarantined')

    def test_mounted_transport_reopen_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = StorageBackend(BackendConfig('nfs', 'mounted', 'g'), MountedFilesystemTransport(tmp))
            self.addCleanup(b.close)
            import sys
            if sys.platform == 'darwin':
                # Stock Python lacks Apple's file-leases entitlement. Exercise
                # the required fail-closed capability gate without publishing.
                with self.assertRaises(OSError):b.write(b'abcdef',generation='g')
                self.assertEqual(b.bytes_written,0)
                self.assertFalse(any(Path(tmp).iterdir()))
                return
            key = b.write(b'abcdef', generation='g'); b.close()
            b = StorageBackend(BackendConfig('nfs', 'mounted', 'g'), MountedFilesystemTransport(tmp))
            self.assertEqual(b.read(TransferExtent(key, 2, 2), generation='g'), b'cd')
            self.assertEqual(b.bytes_read, 6)
            self.assertEqual(b.bytes_requested, 2)
            b.close()


class ActuatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = ResidencyPlacementStore(Path(self.temp.name)/'placement.db'); self.addCleanup(self.store.close)
        self.rows = [{'id': 'a', 'tier': 'T1', 'status': 'active', 'pinned': False, 'events': [], 'source_hash': 'a'*64}]
        self.store.initialize(self.rows, generation='g')
        self.current = True
        self.actuator = ResidencyActuator(self.store, source_is_current=lambda e: self.current,
                                          today=lambda: date(2026, 9, 12), clock=lambda: 100)
        self.shadow = {'status': 'OK', 'tasks_observed': 20, 'admit': ['a'], 'evict': [], 'budget': 20,
                       'rows': [{'item_id': 'a', 'net_token_value_horizon': 100, 'resident_units': 10,
                                 'observed_need_events': 5, 'stale_resident_failures': 0}]}

    def plan(self):
        return self.actuator.propose(self.shadow, context_pressure=.5, prefetch_waste=.1)

    def test_default_dry_run_then_exact_approval_and_rollback(self):
        p = self.plan(); self.assertTrue(p['approved_to_execute'])
        self.assertFalse(self.actuator.execute(p, self.shadow)['changes_applied'])
        self.assertEqual(self.store.snapshot()['entries'], self.rows)
        self.actuator.execute(p, self.shadow, mode='approval', approved_plan_id=p['plan_id'])
        self.assertEqual(self.store.snapshot()['entries'][0]['tier'], 'T0')
        self.assertEqual(self.store.snapshot()['entries'][0]['events'], [])
        self.assertEqual(len(self.store.audit()), 1)
        self.store.rollback(p['plan_id'])
        self.assertEqual(self.store.audit()[-1]['status'], 'rolled-back')
        self.assertEqual(self.store.snapshot()['entries'], self.rows)
        with self.assertRaises(ValueError):
            self.store.rollback(p['plan_id'])

    def test_automatic_disabled_and_forged_plan_rejected(self):
        p = self.plan()
        with self.assertRaises(PermissionError):
            self.actuator.execute(p, self.shadow, mode='automatic')
        bad = copy.deepcopy(p); bad['moves']['a'] = 'T3'
        with self.assertRaisesRegex(ValueError, 'tampered'):
            self.actuator.execute(bad, self.shadow)

    def test_source_changes_and_insufficient_demand_block(self):
        p = self.plan(); self.current = False
        with self.assertRaises(ValueError):
            self.actuator.execute(p, self.shadow, mode='approval', approved_plan_id=p['plan_id'])
        self.current = True; self.shadow['rows'][0]['observed_need_events'] = 1
        self.assertFalse(self.plan()['approved_to_execute'])

    def test_explicit_automatic_requires_bound_task_evidence(self):
        self.actuator.policy = ActuatorPolicy(automatic_mutation=True)
        p = self.plan()
        e = {'policy_sha256': p['policy_sha256'], 'generation': 'g', 'status': 'task-outcome-accepted'}
        self.actuator.execute(p, self.shadow, mode='automatic', accepted_evidence=e)
        self.assertEqual(self.store.snapshot()['entries'][0]['tier'], 'T0')


if __name__ == '__main__':
    unittest.main()
