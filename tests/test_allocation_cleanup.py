"""Allocation cleanup attempts every owner and preserves failed/deferred handles."""
import unittest
from thm.physical.allocation import AllocationPool, AllocationCleanupError


class AllocationCleanupTests(unittest.TestCase):
    def allocate(self, pool, release):
        return pool.allocate(representation_sha256='a'*64, generation='g', kind='device-vram',
                             device='fixture', size=8, owner='owner',
                             allocator=lambda size: (bytearray(size), release))

    def test_cleanup_attempts_all_callbacks_and_retries_only_failed_ownership(self):
        pool = AllocationPool(32); calls = []; retry = False
        def release(name):
            def callback():
                calls.append(name)
                if name in ('first', 'third') and not retry:
                    raise OSError('fixture release unavailable')
            return callback
        allocations = [self.allocate(pool, release(name)) for name in ('first', 'second', 'third')]
        with self.assertRaises(AllocationCleanupError) as error: pool.close()
        self.assertEqual(calls, ['first', 'second', 'third'])
        self.assertEqual(error.exception.failure_count, 2)
        self.assertEqual({key for key, _ in error.exception.failures},
                         {allocations[0].allocation_id, allocations[2].allocation_id})
        self.assertEqual(set(pool.allocations), {allocations[0].allocation_id, allocations[2].allocation_id})
        self.assertTrue(all(a.evicted for a in allocations))
        self.assertIsNone(allocations[1].data)
        self.assertIsNotNone(allocations[0].data)
        with self.assertRaises(ValueError):
            with pool.acquire(allocations[0].allocation_id, generation='g', owner='owner'): pass
        retry = True; pool.close(); pool.close()
        self.assertEqual(calls, ['first', 'second', 'third', 'first', 'third'])
        self.assertEqual(pool.allocations, {})

    def test_failed_earlier_release_still_evicts_an_inflight_later_allocation(self):
        pool = AllocationPool(16); released = []; retry = False
        def fail_once():
            if not retry: raise OSError('fixture release unavailable')
        failed = self.allocate(pool, fail_once)
        deferred = self.allocate(pool, lambda: released.append('deferred'))
        with pool.acquire(deferred.allocation_id, generation='g', owner='owner') as data:
            with self.assertRaises(AllocationCleanupError): pool.close()
            self.assertTrue(deferred.evicted)
            self.assertEqual(deferred.inflight, 1)
            self.assertEqual(released, [])
            self.assertEqual(len(data), 8)
        self.assertEqual(released, ['deferred'])
        self.assertEqual(set(pool.allocations), {failed.allocation_id})
        retry = True; pool.close()
        self.assertEqual(pool.allocations, {})


if __name__ == '__main__':
    unittest.main()
