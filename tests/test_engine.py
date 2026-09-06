"""Tests of actual public-engine functions, isolated files and child processes."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/thm.py'
spec = importlib.util.spec_from_file_location('thm_under_test', SCRIPT)
thm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thm)
NOW = dt.date(2026, 9, 6)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.mem = self.root / 'profile' / 'memories'
        self.mem.mkdir(parents=True)
        for store in thm.STORES:
            (self.mem / store).write_text('', encoding='utf-8')
        self.engine = thm.Engine(self.mem, clock=lambda: NOW)

    def tearDown(self):
        self.tmp.cleanup()

    def seed(self, *texts, user=''):
        (self.mem / 'MEMORY.md').write_text('\n§\n'.join(texts), encoding='utf-8')
        (self.mem / 'USER.md').write_text(user, encoding='utf-8')
        self.engine.seed()
        return self.engine.load().data['entries']

    def row(self):
        return self.seed('alpha setting')[0]

    def cli(self, *args):
        env = os.environ.copy()
        env['THM_MEM_DIR'] = str(self.mem)
        env['THM_STATE_DIR'] = str(self.engine.state_dir)
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                              capture_output=True, text=True, timeout=20)

    def test_same_prefix_in_different_stores(self):
        prefix = 'x' * 24
        rows = self.seed(prefix + ' one', user=prefix + ' two')
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['source_hash'], rows[1]['source_hash'])

    def test_same_prefix_in_same_store(self):
        self.assertEqual(len(self.seed('x' * 24 + ' one', 'x' * 24 + ' two')), 2)

    def test_exact_same_text_in_distinct_stores(self):
        self.assertEqual(len(self.seed('same', user='same')), 2)

    def test_seed_idempotent_bytes(self):
        self.row(); before = thm.read_bytes(self.engine.index)
        self.assertEqual(self.engine.seed()['added'], 0)
        self.assertEqual(thm.read_bytes(self.engine.index), before)

    def test_store_parser_preserves_lines(self):
        p = self.mem / 'MEMORY.md'
        p.write_text('\nalpha\n\nbeta\n§\n\nlast\n', encoding='utf-8')
        self.assertEqual(thm.parse_store(p), [('alpha\n\nbeta', 2), ('last', 7)])

    def test_missing_store_not_empty_success(self):
        (self.mem / 'USER.md').unlink()
        with self.assertRaisesRegex(thm.ThmError, 'SOURCE_UNAVAILABLE'):
            self.engine.seed()
        self.assertFalse(self.engine.index.exists())

    def test_equal_similarity_audit_does_not_compare_dicts(self):
        text = 'shared words ' * 6
        self.seed(text + '1', text + '2', text + '3')
        out = self.engine.audit()
        self.assertEqual(len(out['duplicates']), 3)
        self.assertEqual(out['duplicates'], self.engine.audit()['duplicates'])

    def test_separate_memory_directories_default_separate_state(self):
        self.row()
        other_mem = self.root / 'other'
        other_mem.mkdir()
        for s in thm.STORES:
            (other_mem / s).write_text('', encoding='utf-8')
        other = thm.Engine(other_mem, clock=lambda: NOW)
        self.assertEqual(other.load().data['entries'], [])
        with self.assertRaisesRegex(thm.ThmError, 'ENTRY_NOT_FOUND'):
            other.feedback('hit', 'alpha')

    def test_explicit_shared_state_rejected(self):
        self.row()
        other = thm.Engine(self.root / 'different', self.engine.state_dir)
        with self.assertRaisesRegex(thm.ThmError, 'MEMORY_DIRECTORY_MISMATCH'):
            other.load()
        with self.assertRaisesRegex(thm.ThmError, 'MEMORY_DIRECTORY_MISMATCH'):
            other.manifest()

    def test_ambiguous_feedback_has_no_write(self):
        self.seed('alpha first', 'alpha second')
        before = thm.read_bytes(self.engine.index)
        with self.assertRaisesRegex(thm.ThmError, 'AMBIGUOUS_ENTRY'):
            self.engine.feedback('hit', 'alpha')
        self.assertEqual(thm.read_bytes(self.engine.index), before)

    def test_exact_id_feedback_selects_correct_record(self):
        rows = self.seed('alpha first', 'alpha second')
        self.engine.feedback('hit', rows[1]['id'])
        events = self.engine.load().data['entries']
        self.assertEqual([len(e['events']) for e in events], [1, 2])

    def test_full_text_fallback_beyond_summary(self):
        self.seed('x' * 70 + ' needle')
        self.assertEqual(self.engine.feedback('hit', 'needle')['status'], 'OK')

    def test_source_changed_rejects_old_confirmation(self):
        row = self.row()
        (self.mem / 'MEMORY.md').write_text('alpha changed', encoding='utf-8')
        with self.assertRaisesRegex(thm.ThmError, 'SOURCE_CHANGED'):
            self.engine.feedback('confirm', row['id'], evidence='user:synthetic')

    def test_source_orphan_is_reported_not_forgotten(self):
        self.row()
        (self.mem / 'MEMORY.md').write_text('', encoding='utf-8')
        self.assertEqual(self.engine.audit()['excluded'][0]['reason'], 'source_changed_or_removed')
        self.assertEqual(len(self.engine.load().data['entries']), 1)

    def test_invalid_date_rejected(self):
        for date in ['not-a-date', '2026-02-30', '20260906', None]:
            with self.assertRaises(thm.ThmError):
                thm.days_since(date, NOW)

    def test_future_event_rejected(self):
        with self.assertRaisesRegex(thm.ThmError, 'FUTURE_EVENT'):
            thm.activation({'events': [{'t': '9999-12-31', 'type': 'hit'}]}, NOW)

    def test_future_scheduled_review_allowed(self):
        self.row(); self.engine.validate(self.engine.load().data)

    def test_unknown_event_rejected(self):
        with self.assertRaisesRegex(thm.ThmError, 'UNKNOWN_EVENT'):
            thm.activation({'events': [{'t': NOW.isoformat(), 'type': 'typo'}]}, NOW)

    def test_movement_display_retrieval_do_not_increase_activity(self):
        for kind in ['promote', 'demote', 'display', 'retrieve']:
            self.assertEqual(thm.activation({'events': [{'t': NOW.isoformat(), 'type': kind}]}, NOW), 0)

    def test_legacy_unverified_confirm_not_evidence(self):
        event = {'t': NOW.isoformat(), 'type': 'confirm', 'legacy_unverified': True}
        self.assertEqual(thm.activation({'events': [event]}, NOW), 0)

    def test_confirmation_requires_evidence(self):
        row = self.row()
        with self.assertRaisesRegex(thm.ThmError, 'EVIDENCE_REQUIRED'):
            self.engine.feedback('confirm', row['id'])

    def test_retried_hit_is_idempotent(self):
        row = self.row()
        self.engine.feedback('hit', row['id'], 'same retry')
        before = thm.read_bytes(self.engine.index)
        self.assertEqual(self.engine.feedback('hit', row['id'], 'same retry')['status'], 'DUPLICATE')
        self.assertEqual(thm.read_bytes(self.engine.index), before)

    def test_distinct_explicit_hit_ids_count(self):
        row = self.row()
        self.engine.feedback('hit', row['id'], event_id='one')
        self.engine.feedback('hit', row['id'], event_id='two')
        self.assertEqual(len(self.engine.load().data['entries'][0]['events']), 3)

    def test_event_id_content_conflict(self):
        row = self.row()
        self.engine.feedback('hit', row['id'], 'one', 'same-id')
        with self.assertRaisesRegex(thm.ThmError, 'REUSED_WITH_DIFFERENT'):
            self.engine.feedback('hit', row['id'], 'two', 'same-id')

    def test_same_day_confirmation_does_not_jump_ladder(self):
        row = self.row()
        for i in range(3):
            self.engine.feedback('confirm', row['id'], event_id=str(i), evidence=f'user:check-{i}')
        stored = self.engine.load().data['entries'][0]
        self.assertEqual(stored['review_stage'], 1)
        self.assertEqual(stored['next_review'], '2026-09-13')
        self.assertEqual(len(stored['events']), 2)

    def test_expired_entry_not_confirmed_or_ranked(self):
        row = self.row(); snap = self.engine.load()
        snap.data['entries'][0]['valid_until'] = NOW.isoformat()
        self.engine.save(snap)
        with self.assertRaisesRegex(thm.ThmError, 'NOT_CURRENTLY_ELIGIBLE'):
            self.engine.feedback('confirm', row['id'], evidence='user:check')
        self.assertEqual(self.engine.audit()['ranking'], [])

    def test_deleted_record_seed_does_not_resurrect(self):
        self.row(); snap = self.engine.load()
        snap.data['entries'][0]['status'] = 'deleted'; self.engine.save(snap)
        self.engine.seed()
        self.assertEqual(self.engine.load().data['entries'][0]['status'], 'deleted')

    def old(self, *, pinned=False, cost='high'):
        row = self.row(); snap = self.engine.load(); e = snap.data['entries'][0]
        e.update(created='2023-01-01', pinned=pinned, cost_class=cost)
        e['events'][0]['t'] = '2023-01-01'; self.engine.save(snap)
        return row

    def test_new_high_cost_is_not_permanent(self):
        self.old()
        self.assertEqual(len(self.engine.audit()['demote']), 1)

    def test_explicit_pin_reported_accurately(self):
        self.old(pinned=True)
        out = self.engine.audit()
        self.assertEqual(out['demote'], [])
        self.assertEqual(len(out['pinned_low_activity']), 1)

    def test_explicit_unpin_enables_proposal(self):
        row = self.old(pinned=True)
        self.engine.pin(row['id'], False)
        self.assertEqual(len(self.engine.audit()['demote']), 1)

    def test_conflicting_snapshot_rejected(self):
        self.row(); a, b = self.engine.load(), self.engine.load()
        a.data['entries'][0]['summary'] = 'writer-a'; self.engine.save(a)
        b.data['entries'][0]['summary'] = 'writer-b'
        with self.assertRaisesRegex(thm.ThmError, 'INDEX_CONFLICT'):
            self.engine.save(b)
        self.assertEqual(self.engine.load().data['entries'][0]['summary'], 'writer-a')

    def test_write_failure_preserves_original(self):
        self.row(); before = thm.read_bytes(self.engine.index)
        snap = self.engine.load(); snap.data['entries'][0]['summary'] = 'changed'
        original_replace = thm.os.replace
        def fail_index(src, dst):
            if Path(dst) == self.engine.index:
                raise OSError('synthetic before replacement')
            return original_replace(src, dst)
        with patch.object(thm.os, 'replace', side_effect=fail_index):
            with self.assertRaises(OSError):
                self.engine.save(snap)
        self.assertEqual(thm.read_bytes(self.engine.index), before)
        self.engine.load()
        self.assertFalse(list(self.engine.state_dir.glob('.thm-tmp-*')))

    def test_serialization_failure_does_not_touch_original(self):
        self.row(); before = thm.read_bytes(self.engine.index)
        snap = self.engine.load(); snap.data['bad'] = float('nan')
        with self.assertRaises(thm.ThmError): self.engine.save(snap)
        self.assertEqual(thm.read_bytes(self.engine.index), before)

    def test_previous_index_backup(self):
        row = self.row(); before = thm.read_bytes(self.engine.index)
        self.engine.feedback('hit', row['id'])
        self.assertEqual(thm.read_bytes(self.engine.state_dir / 'index.previous.json'), before)

    def test_corrupt_index_not_treated_as_empty(self):
        self.row(); self.engine.index.write_bytes(b'{')
        with self.assertRaisesRegex(thm.ThmError, 'INVALID_INDEX_JSON'):
            self.engine.seed()
        self.assertEqual(self.engine.index.read_bytes(), b'{')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(thm.ThmError, 'DUPLICATE_JSON_KEY'):
            thm.decode(b'{"a":1,"a":2}')

    def legacy(self, unresolved=False):
        text = 'legacy alpha setting'
        self.seed(text)
        self.engine.index.unlink()
        e = {'id': 'e001', 'store': 'MEMORY.md', 'key': text[:24], 'summary': text[:60],
             'tier': 'T0', 'created': '2026-01-01', 'cost_class': 'high', 'review_stage': 0,
             'next_review': '2026-01-04', 'events': [{'type': 'create', 't': '2026-01-01'}],
             'unknown_extension': {'retained': True}}
        if unresolved: e['key'] = 'ambiguous old record'
        source = self.root / 'legacy.json'
        source.write_text(json.dumps({'version': 1, 'entries': [e]}), encoding='utf-8')
        return source

    def test_migration_preview_no_writes(self):
        path = self.legacy(); before = path.read_bytes()
        self.assertEqual(self.engine.migrate(path)['status'], 'PREVIEW')
        self.assertFalse(self.engine.index.exists())
        self.assertEqual(path.read_bytes(), before)

    def test_migration_preserves_source_unknown_fields_and_high_protection(self):
        path = self.legacy(); before = path.read_bytes()
        self.engine.migrate(path, apply=True)
        e = self.engine.load().data['entries'][0]
        self.assertTrue(e['pinned'])
        self.assertEqual(e['id'], 'e001')
        self.assertEqual(e['unknown_extension'], {'retained': True})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((self.engine.state_dir/'legacy-index.backup.json').read_bytes(), before)

    def test_unresolved_legacy_kept_inactive(self):
        path = self.legacy(unresolved=True)
        self.engine.migrate(path, apply=True)
        self.assertEqual(self.engine.load().data['entries'][0]['status'], 'unresolved_legacy')
        self.assertEqual(self.engine.audit()['ranking'], [])

    def test_migration_wont_overwrite_existing_target(self):
        path = self.legacy(); self.engine.migrate(path, apply=True)
        before = self.engine.index.read_bytes()
        with self.assertRaisesRegex(thm.ThmError, 'TARGET_EXISTS'):
            self.engine.migrate(path, apply=True)
        self.assertEqual(self.engine.index.read_bytes(), before)

    def test_tilde_expands(self):
        self.assertTrue(thm.normal_path('~/thm-test-path').is_absolute())
        self.assertNotIn('~', str(thm.normal_path('~/thm-test-path')))

    def test_config_relative_paths_and_exact_keys(self):
        conf = self.root / 'thm.conf'
        conf.write_text('mem_dir=memories\nstate_dir=private-state\n', encoding='utf-8')
        with patch.dict(os.environ, {}, clear=True):
            mem, state = thm.config_paths(conf=conf)
        self.assertEqual(mem, self.root/'memories')
        self.assertEqual(state, self.root/'private-state')
        conf.write_text('mem_directory=wrong\n', encoding='utf-8')
        with self.assertRaises(thm.ThmError): thm.config_paths(conf=conf)

    def test_hermes_home_honored(self):
        with patch.object(thm, 'BASE', self.root), patch.dict(os.environ, {'HERMES_HOME': str(self.root/'home')}, clear=True):
            # Missing default configuration is optional; an explicit path is strict.
            mem, state = thm.config_paths()
        self.assertEqual(mem, self.root/'home/memories')
        self.assertEqual(state, mem/'.thm')

    def test_cli_help_reads_no_config(self):
        result = self.cli('--config', str(self.root/'missing'))
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.engine.state_dir.exists())

    def test_cli_missing_argument_no_traceback(self):
        result = self.cli('hit')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)

    def test_cli_unknown_command_fails(self):
        self.assertEqual(self.cli('unknown-command').returncode, 2)

    def test_cli_missing_record_fails(self):
        self.assertEqual(self.cli('hit', 'absent').returncode, 1)

    def test_cli_invalid_store_cost_rejected(self):
        for args in [('register','../bad','x','med'), ('register','MEMORY.md','x','urgent')]:
            self.assertEqual(self.cli(*args).returncode, 2)

    def test_two_real_processes_do_not_lose_hits(self):
        row = self.row()
        code = ('import importlib.util,datetime,sys; '
                f's=importlib.util.spec_from_file_location("thm",{str(SCRIPT)!r}); '
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m); '
                f'e=m.Engine({str(self.mem)!r},clock=lambda:datetime.date(2026,9,6)); '
                f'e.feedback("hit",{row["id"]!r},event_id=sys.argv[1])')
        workers = [subprocess.Popen([sys.executable, '-c', code, str(i)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
        for p in workers:
            out, err = p.communicate(timeout=20)
            self.assertEqual(p.returncode, 0, err.decode())
        self.assertEqual(len(self.engine.load().data['entries'][0]['events']), 5)

    def test_killed_lock_holder_releases_os_lock(self):
        lock = self.engine.state_dir/'index.lock'
        code = ('import importlib.util,time; from pathlib import Path; '
                f's=importlib.util.spec_from_file_location("thm",{str(SCRIPT)!r}); '
                'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                f'\nwith m.index_lock(Path({str(lock)!r})):\n print("locked",flush=True)\n time.sleep(30)\n')
        p = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(p.stdout.readline().strip(), b'locked')
            p.kill(); p.communicate(timeout=10)
            with thm.index_lock(lock, timeout=1): pass
        finally:
            if p.poll() is None: p.kill()
            p.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
