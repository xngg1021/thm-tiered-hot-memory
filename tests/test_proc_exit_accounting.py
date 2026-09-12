"""A denied procfs read is tolerable only after verified process exit."""
from pathlib import Path
import os
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from thm.runtime.fabric.resources import ChildBudget


class ProcExitAccountingTests(unittest.TestCase):
    def test_denied_io_rechecks_dead_state_and_live_denial_remains_error(self):
        for state in ('Z', 'X', 'S'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                process = root / '100'
                process.mkdir()
                stat = '100 (worker) S 1 100 100 0 0 0 0 0 0 0 10 5\n'
                (process / 'stat').write_text(stat)
                (process / 'status').write_text('VmRSS: 1 kB\n')
                original = Path.read_text
                def read(path, *args, **kwargs):
                    if path.name == 'io':
                        (process / 'stat').write_text(stat.replace(') S ', ') ' + state + ' '))
                        raise PermissionError('proc I/O became unavailable')
                    return original(path, *args, **kwargs)
                budget = ChildBudget.__new__(ChildBudget)
                budget.pgid = 100
                budget.process = SimpleNamespace(pid=100, wait=mock.Mock(side_effect=subprocess.TimeoutExpired('worker', .2)))
                with mock.patch.object(os, 'sysconf', return_value=100, create=True), \
                     mock.patch.object(os, 'getpgid', return_value=100, create=True), \
                     mock.patch.object(Path, 'read_text', read):
                    if state == 'S':
                        with self.assertRaises(PermissionError):
                            budget._linux_usage(root)
                    else:
                        self.assertIsNone(budget._linux_usage(root))


if __name__ == '__main__':
    unittest.main()
