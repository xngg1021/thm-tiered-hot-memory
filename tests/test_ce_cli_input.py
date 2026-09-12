"""The CE CLI reads only bounded regular bytes from its checked descriptor."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from thm import economics_bridge as bridge


class BridgeCLIInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'input.json'
        self.output = self.root/'output.json'; self.evidence = '1'*64
        self.advice = bridge.EconomicAdvice('fixture', '2'*40, self.evidence, 0, 100, 20).public()
        self.source.write_text(json.dumps(self.advice), encoding='utf-8')

    def run_cli(self):
        argv = ['thm.economics_bridge', 'validate-advice', '--input', str(self.source),
                '--output', str(self.output), '--evidence-sha256', self.evidence]
        with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            bridge.main()

    def test_valid_advice_preserves_checksum_and_never_enables_mutation(self):
        self.run_cli()
        self.assertEqual(json.loads(self.output.read_text()), self.advice)

    @unittest.skipUnless(os.name == 'posix', 'POSIX FIFO/symlink replacement')
    def test_replacement_before_open_cannot_bypass_descriptor_validation(self):
        original_open = os.open
        for kind in ('fifo', 'symlink', 'oversized-regular'):
            with self.subTest(kind=kind):
                self.output.unlink(missing_ok=True)
                self.source.unlink(); self.source.write_text(json.dumps(self.advice))
                def swap(path, flags, **kw):
                    if Path(path) == self.source:
                        self.source.unlink()
                        if kind == 'fifo': os.mkfifo(self.source)
                        elif kind == 'symlink': self.source.symlink_to('/dev/zero')
                        else:
                            with self.source.open('wb') as stream: stream.truncate(8_000_001)
                    return original_open(path, flags, **kw)
                with mock.patch('os.open', side_effect=swap):
                    with self.assertRaises(SystemExit) as rejected: self.run_cli()
                self.assertEqual(rejected.exception.code, 2)
                self.assertFalse(self.output.exists())

    def test_growth_after_descriptor_check_stops_at_the_byte_limit(self):
        original_read = os.read; observed = []; grown = False
        def grow(fd, count):
            nonlocal grown
            if not grown:
                grown = True
                with self.source.open('ab') as stream: stream.truncate(8_000_001)
            data = original_read(fd, count); observed.append(len(data)); return data
        with mock.patch('os.read', side_effect=grow):
            with self.assertRaises(SystemExit) as rejected: self.run_cli()
        self.assertEqual(rejected.exception.code, 2)
        self.assertTrue(grown)
        self.assertLessEqual(sum(observed), 8_000_001)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
