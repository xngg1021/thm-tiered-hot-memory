"""Additional direct regressions for the 1.1 public CLI; synthetic data only."""
import datetime as dt
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/thm.py'
spec = importlib.util.spec_from_file_location('thm_chat_regression', SCRIPT)
thm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thm)
DAY = dt.date(2026, 9, 6)


class ChatRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.mem = self.root / 'memories'
        self.mem.mkdir()
        (self.mem / 'MEMORY.md').write_text('alpha entry', encoding='utf-8')
        (self.mem / 'USER.md').write_text('', encoding='utf-8')
        self.engine = thm.Engine(self.mem, clock=lambda: DAY)
        self.engine.seed()
        self.entry_id = self.engine.load().data['entries'][0]['id']

    def tearDown(self):
        self.tmp.cleanup()

    def test_summary_hit_cannot_hide_full_text_ambiguity(self):
        (self.mem / 'MEMORY.md').write_text('needle first\n§\n' + 'z' * 80 + ' needle second', encoding='utf-8')
        self.engine.seed()
        before = self.engine.index.read_bytes()
        with self.assertRaisesRegex(thm.ThmError, 'AMBIGUOUS_ENTRY'):
            self.engine.feedback('hit', 'needle', event_id='ambiguous')
        self.assertEqual(before, self.engine.index.read_bytes())

    def test_same_entry_summary_and_full_text_not_double_counted(self):
        self.assertEqual(self.engine.feedback('hit', 'alpha', event_id='unique')['status'], 'OK')

    def test_explicit_hit_retry_on_later_day_is_byte_identical(self):
        self.engine.feedback('hit', self.entry_id, 'used', 'stable-request')
        before = self.engine.index.read_bytes()
        self.engine.clock = lambda: DAY + dt.timedelta(days=1)
        out = self.engine.feedback('hit', self.entry_id, 'used', 'stable-request')
        self.assertEqual(out['status'], 'DUPLICATE')
        self.assertEqual(before, self.engine.index.read_bytes())

    def test_confirm_retry_later_day_does_not_advance_review(self):
        self.engine.feedback('confirm', self.entry_id, event_id='confirm-request', evidence='synthetic:source')
        before = self.engine.index.read_bytes()
        self.engine.clock = lambda: DAY + dt.timedelta(days=3)
        out = self.engine.feedback('confirm', self.entry_id, event_id='confirm-request', evidence='synthetic:source')
        self.assertEqual(out['status'], 'DUPLICATE')
        self.assertEqual(before, self.engine.index.read_bytes())

    def test_changed_payload_still_conflicts_on_later_day(self):
        self.engine.feedback('hit', self.entry_id, 'old', 'same')
        self.engine.clock = lambda: DAY + dt.timedelta(days=1)
        with self.assertRaisesRegex(thm.ThmError, 'REUSED_WITH_DIFFERENT'):
            self.engine.feedback('hit', self.entry_id, 'new', 'same')

    def test_acknowledged_old_event_does_not_reactivate_deleted_record(self):
        self.engine.feedback('hit', self.entry_id, event_id='already-written')
        snapshot = self.engine.load()
        snapshot.data['entries'][0]['status'] = 'deleted'
        self.engine.save(snapshot)
        before = self.engine.index.read_bytes()
        out = self.engine.feedback('hit', self.entry_id, event_id='already-written')
        self.assertEqual(out['status'], 'DUPLICATE')
        self.assertEqual(before, self.engine.index.read_bytes())
        with self.assertRaisesRegex(thm.ThmError, 'NOT_CURRENTLY_ELIGIBLE'):
            self.engine.feedback('hit', self.entry_id, event_id='new-request')

    def test_committed_event_retry_after_source_removed(self):
        self.engine.feedback('hit', self.entry_id, event_id='committed')
        (self.mem / 'MEMORY.md').unlink()
        before = self.engine.index.read_bytes()
        self.assertEqual(self.engine.feedback('hit', self.entry_id, event_id='committed')['status'], 'DUPLICATE')
        self.assertEqual(before, self.engine.index.read_bytes())
        with self.assertRaises(thm.ThmError):
            self.engine.feedback('hit', self.entry_id, event_id='new')

    def test_automatic_events_remain_day_scoped(self):
        self.engine.feedback('hit', self.entry_id, 'normal use')
        self.engine.clock = lambda: DAY + dt.timedelta(days=1)
        self.assertEqual(self.engine.feedback('hit', self.entry_id, 'normal use')['status'], 'OK')
        self.assertEqual(len(self.engine.load().data['entries'][0]['events']), 3)

    def test_unhashable_event_type_is_domain_error(self):
        with self.assertRaisesRegex(thm.ThmError, 'UNKNOWN_EVENT_TYPE'):
            thm.activation({'events': [{'type': [], 't': DAY.isoformat()}]}, DAY)

    def test_non_object_event_is_domain_error(self):
        with self.assertRaisesRegex(thm.ThmError, 'INVALID_EVENTS'):
            thm.activation({'events': [None]}, DAY)

    def test_non_text_event_id_is_domain_error(self):
        with self.assertRaisesRegex(thm.ThmError, 'INVALID_EVENT_ID'):
            thm.activation({'events': [{'type': 'hit', 't': DAY.isoformat(), 'event_id': ['bad']}]}, DAY)

    def test_invalid_feedback_types_do_not_write(self):
        before = self.engine.index.read_bytes()
        for kwargs in ({'event_id': []}, {'note': None}, {'evidence': []}):
            with self.subTest(kwargs=kwargs), self.assertRaises(thm.ThmError):
                self.engine.feedback('hit', self.entry_id, **kwargs)
        self.assertEqual(before, self.engine.index.read_bytes())

    def test_invalid_selector_is_domain_error(self):
        with self.assertRaises(thm.ThmError):
            self.engine.feedback('hit', ['not', 'text'])

    def test_explicit_memory_path_does_not_evaluate_unavailable_home(self):
        with patch.object(thm.Path, 'home', side_effect=RuntimeError('no home')):
            mem, _ = thm.config_paths(mem_dir=self.mem)
        self.assertEqual(mem, self.mem)

    def test_hermes_home_does_not_evaluate_path_home_default(self):
        with patch.object(thm.Path, 'home', side_effect=RuntimeError('no home')), patch.dict(
                os.environ, {'HERMES_HOME': str(self.root / 'home')}, clear=True):
            mem, _ = thm.config_paths()
        self.assertEqual(mem, self.root / 'home' / 'memories')

    def test_explicit_missing_config_fails(self):
        with self.assertRaisesRegex(thm.ThmError, 'CONFIG_UNAVAILABLE'):
            thm.config_paths(conf=self.root / 'missing.conf')

    def test_optional_default_config_can_be_missing(self):
        with patch.object(thm, 'BASE', self.root), patch.dict(os.environ, {'HERMES_HOME': str(self.root / 'home')}, clear=True):
            mem, _ = thm.config_paths()
        self.assertEqual(mem, self.root / 'home' / 'memories')

    def test_config_tilde_expands_before_read(self):
        (self.root / 'selected.conf').write_text('mem_dir=selected\n', encoding='utf-8')
        with patch.dict(os.environ, {'HOME': str(self.root), 'USERPROFILE': str(self.root)}, clear=True):
            mem, _ = thm.config_paths(conf='~/selected.conf')
        self.assertEqual(mem, self.root / 'selected')

    def test_cli_missing_config_errors_without_traceback(self):
        out = subprocess.run([sys.executable, str(SCRIPT), '--config', str(self.root / 'missing'), 'audit'],
                             capture_output=True, text=True, timeout=10)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn('CONFIG_UNAVAILABLE', out.stderr)
        self.assertNotIn('Traceback', out.stderr)

    def test_manifest_rejects_linked_directory(self):
        # Mock only the platform-dependent link probe; no elevated Windows privilege needed.
        with patch.object(Path, 'is_symlink', autospec=True,
                          side_effect=lambda p: p == self.engine.state_dir / 'warm'):
            with self.assertRaisesRegex(thm.ThmError, 'SYMLINK_WARM_DIRECTORY'):
                self.engine.manifest()

    def test_malformed_migration_events_do_not_crash_or_write(self):
        legacy = {'version': 1, 'entries': [{'id': 'e001', 'store': 'MEMORY.md', 'key': 'alpha entry',
                  'summary': 'alpha entry', 'tier': 'T0', 'cost_class': 'med', 'created': DAY.isoformat(),
                  'review_stage': 0, 'next_review': DAY.isoformat(), 'events': [None]}]}
        path = self.root / 'legacy.json'
        path.write_text(__import__('json').dumps(legacy), encoding='utf-8')
        target = thm.Engine(self.mem, self.root / 'new-state', clock=lambda: DAY)
        with self.assertRaisesRegex(thm.ThmError, 'INVALID_LEGACY_EVENTS'):
            target.migrate(path, apply=True)
        self.assertFalse(target.index.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
