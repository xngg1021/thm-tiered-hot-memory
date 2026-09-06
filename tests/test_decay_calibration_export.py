"""Privacy and semantics tests for real-use decay calibration export."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from scripts import thm as legacy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'decay_from_index', ROOT / 'research' / 'recall' / 'decay_from_index.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DecayCalibrationExportTests(unittest.TestCase):
    def make_fixture(self, root: Path):
        mem = root / 'memories'
        state = mem / '.thm'
        state.mkdir(parents=True)
        secret = 'database password is never-export-this-text'
        (mem / 'MEMORY.md').write_text(secret + '\n§\n', encoding='utf-8')
        (mem / 'USER.md').write_text('', encoding='utf-8')
        sh = legacy.source_hash('MEMORY.md', secret)
        index = {
            'version': 2,
            'revision': 1,
            'mem_dir': str(mem.resolve()),
            'entries': [{
                'id': 'e1', 'status': 'active', 'source_hash': sh,
                'pinned': False, 'cost_class': 'med',
                'events': [
                    {'event_id': 'h1', 'type': 'hit', 't': '2026-09-01'},
                    {'event_id': 'm1', 'type': 'display', 't': '2026-09-02'},
                    {'event_id': 'c1', 'type': 'confirm', 't': '2026-09-03', 'evidence': 'private-evidence'},
                ],
            }],
        }
        path = state / 'index.json'
        path.write_text(json.dumps(index), encoding='utf-8')
        return mem, path, secret

    def test_export_contains_only_explicit_hit_chronology_without_memory_text(self):
        with tempfile.TemporaryDirectory() as temp:
            mem, path, secret = self.make_fixture(Path(temp))
            result = module.export(path, mem, 'utf8_bytes')
            rendered = json.dumps(result)
            self.assertEqual(result['hit_event_count'], 1)
            self.assertEqual(result['events'], [{'id': 'e1', 't': '2026-09-01'}])
            self.assertFalse(result['contains_memory_text'])
            self.assertNotIn(secret, rendered)
            self.assertNotIn('private-evidence', rendered)
            self.assertGreater(result['entries'][0]['units'], 0)

    def test_explicit_mem_dir_must_match_index_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            mem, path, _ = self.make_fixture(Path(temp))
            with self.assertRaises(ValueError):
                module.export(path, mem.parent / 'other', 'utf8_bytes')


if __name__ == '__main__':
    unittest.main(verbosity=2)
