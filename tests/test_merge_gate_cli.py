"""Release admission reads the same bounded regular descriptor it validates."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import verify_merge_gate as gate
from test_merge_gate import snapshot


class MergeGateCLIInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.path = self.root/'snapshot.json'
        self.path.write_text(json.dumps(snapshot()), encoding='utf-8')
        self.output = io.StringIO()

    def run_cli(self):
        with mock.patch.object(sys, 'argv', ['verify_merge_gate.py', str(self.path), '--expected-head', 'a'*40, '--expected-base', 'b'*40]), \
             contextlib.redirect_stdout(self.output):
            gate.main()

    def test_direct_clean_interpreter_execution_from_another_directory(self):
        result = subprocess.run([sys.executable, '-S', str(Path(gate.__file__).resolve()),
                                 str(self.path), '--expected-head', 'a'*40, '--expected-base', 'b'*40], cwd=self.root,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['expected_head_sha'], 'a'*40)
        self.assertEqual(receipt['schema'], 'thm-merge-gate/1')

    @unittest.skipUnless(os.name == 'posix', 'POSIX FIFO/symlink replacement')
    def test_replaced_snapshot_cannot_publish_admission(self):
        original_open = os.open
        for kind in ('fifo', 'symlink', 'oversized-regular'):
            with self.subTest(kind=kind):
                self.path.unlink(); self.path.write_text(json.dumps(snapshot()))
                def swap(path, flags, **kw):
                    if Path(path) == self.path:
                        self.path.unlink()
                        if kind == 'fifo': os.mkfifo(self.path)
                        elif kind == 'symlink': self.path.symlink_to('/dev/zero')
                        else:
                            with self.path.open('wb') as stream: stream.truncate(8*1024*1024+1)
                    return original_open(path, flags, **kw)
                with mock.patch('os.open', side_effect=swap):
                    with self.assertRaises((OSError, ValueError)): self.run_cli()
                self.assertEqual(self.output.getvalue(), '')

    def test_growth_is_bounded_and_descriptor_closes_without_admission(self):
        original_read = os.read; observed = []; descriptors = []
        def grow(fd, count):
            if not descriptors:
                descriptors.append(fd)
                with self.path.open('ab') as stream: stream.truncate(8*1024*1024+1)
            data = original_read(fd, count); observed.append(len(data)); return data
        with mock.patch('os.read', side_effect=grow):
            with self.assertRaises(ValueError): self.run_cli()
        self.assertTrue(descriptors)
        self.assertLessEqual(sum(observed), 8*1024*1024+1)
        self.assertEqual(self.output.getvalue(), '')
        with self.assertRaises(OSError): os.fstat(descriptors[0])


if __name__ == '__main__':
    unittest.main()
