"""Allocation admission and publication remain atomic across cleanup failures."""
from dataclasses import replace
import unittest
from unittest import mock

import numpy as np
from thm.runtime.fabric.contracts import IndexIdentity
from thm.runtime.fabric.indexes import ExactHost
from thm.runtime.fabric.multidevice import MultiDeviceIndex


class MultiDeviceAdmissionTests(unittest.TestCase):
    def test_capacity_precedes_normalization_for_array_and_sequence(self):
        identity = IndexIdentity('s', 'g', 'ep', 'multi', '1', 'cfg')
        for matrix in (np.ones((2, 2), dtype=np.float64), [[1, 2], [3, 4]]):
            provider = mock.Mock()
            index = MultiDeviceIndex([provider], budgets=[1])
            with mock.patch.object(np, 'asarray', side_effect=AssertionError('normalized before admission')):
                with self.assertRaises(MemoryError):
                    index.build(matrix, ['a', 'b'], identity)
            provider.build.assert_not_called()
            index.close()

    def test_retirement_failure_does_not_reject_published_generation(self):
        index = MultiDeviceIndex([ExactHost(), ExactHost()], budgets=[32, 32])
        identity = IndexIdentity('s', 'g', 'ep', 'multi', '1', 'cfg')
        index.build([[1, 0], [0, 1]], ['a', 'b'], identity)
        old = [handle for _, handle in index.shards]
        old[0].close_callback = mock.Mock(side_effect=RuntimeError('retirement failed'))
        old[1].close_callback = mock.Mock()
        index.build([[0, 1], [1, 0]], ['a', 'b'], replace(identity, generation='new'))
        old[0].close_callback.assert_called_once()
        old[1].close_callback.assert_called_once()
        rows, receipt = index.search([[1, 0]], 1, generation='new')
        self.assertEqual(rows[0][0], ['b'])
        self.assertEqual(receipt['retirement_errors'], [{'stage': 'retire', 'error': 'RuntimeError'}])
        index.close()


if __name__ == '__main__':
    unittest.main()
