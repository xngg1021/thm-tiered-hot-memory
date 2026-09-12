"""Procfs observations must use the caller's PID namespace."""
from pathlib import Path
import unittest
from unittest import mock

from thm.runtime.fabric.resources import ChildBudget, ProcessGroupAccountingUnavailable


class ProcNamespaceIdentityTests(unittest.TestCase):
    def test_namespace_mismatch_defers_before_enumerating_other_processes(self):
        budget=ChildBudget.__new__(ChildBudget)
        with mock.patch('os.getpid',return_value=5), \
             mock.patch.object(Path,'read_text',return_value='90000 (worker) S'), \
             mock.patch.object(Path,'iterdir',side_effect=AssertionError('mixed namespaces scanned')):
            with self.assertRaisesRegex(ProcessGroupAccountingUnavailable,'namespace mismatch'):
                budget._linux_usage()


if __name__ == '__main__':
    unittest.main()
