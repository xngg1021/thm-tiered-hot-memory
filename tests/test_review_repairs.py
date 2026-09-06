"""Regression tests of published modules, using synthetic inputs only."""
import copy
import datetime as dt
import importlib.util
import json
import math
import sqlite3
from pathlib import Path
import tempfile
import concurrent.futures
import unittest
from unittest.mock import patch

from thm.retrieval import Document, SearchIndex, normalize_vectors, TokenCounter
from thm.sources import read_hermes
from thm.observations import scan, visible_text, store_observations
from thm.policy import Policy, plan, activity

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review_benchmark', ROOT/'research/recall/benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class RetrievalRepairs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'recall.sqlite'
        self.index = SearchIndex(self.path)
        self.docs = [Document('a', 's', 'chat', 0, 'alpha apple', source='file:a'),
                     Document('b', 's', 'chat', 1, 'alpha pear', source='file:b')]
        self.index.replace_scope('s', self.docs)

    def tearDown(self):
        self.index.close()
        self.tmp.cleanup()

    def test_extreme_finite_vectors_normalize(self):
        for scale in (1e308, 1e-300):
            got = normalize_vectors([[scale, scale]], 1)[0]
            self.assertAlmostEqual(math.hypot(*got), 1.0)
            self.assertAlmostEqual(got[0], 2**-.5)

    def test_invalid_counter_does_not_bypass_budget(self):
        for bad in (-1, float('nan'), True, 0):
            self.index.counter = lambda text, bad=bad: bad
            with self.assertRaises(ValueError):
                self.index.search('s', 'alpha', budget=600)

    def test_boolean_candidate_count_refused(self):
        with self.assertRaises(ValueError):
            self.index.search('s', 'alpha', candidate_limit=True)

    def test_boolean_neighbor_count_refused(self):
        with self.assertRaises(ValueError):
            self.index.search('s', 'alpha', neighbor_turns=True)

    def test_duplicate_position_refused_without_change(self):
        before = self.index.rows('s')
        with self.assertRaises(ValueError):
            self.index.replace_scope('s', [self.docs[0], Document('z', 's', 'chat', 0, 'wrong')])
        self.assertEqual(before, self.index.rows('s'))

    def test_readonly_never_creates_database(self):
        missing = self.path.parent/'missing.sqlite'
        with self.assertRaises((ValueError, OSError, sqlite3.Error)):
            SearchIndex(missing, readonly=True)
        self.assertFalse(missing.exists())

    def test_readonly_rejects_updates(self):
        reader = SearchIndex(self.path, readonly=True)
        try:
            self.assertTrue(reader.search('s', 'alpha')['selected'])
            with self.assertRaises(ValueError):
                reader.replace_scope('s', [])
        finally:
            reader.close()

    def test_unrelated_sqlite_not_modified(self):
        path = self.path.parent/'native.sqlite'
        db = sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, content TEXT)')
            db.commit()
        finally:
            db.close()
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            SearchIndex(path)
        self.assertEqual(before, path.read_bytes())

    def test_embed_unknown_scope_refused(self):
        with self.assertRaises(ValueError):
            self.index.embed('missing', lambda texts: [[1, 0]]*len(texts), 'm')

    def test_embedding_generation_change_refused(self):
        def encoder(texts):
            other = SearchIndex(self.path)
            try:
                other.replace_scope('s', [Document('c', 's', 'chat', 0, 'new')])
            finally:
                other.close()
            return [[1, 0] for _ in texts]
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.index.embed('s', encoder, 'm')
        self.assertEqual(self.index.db.execute('SELECT COUNT(*) FROM vectors').fetchone()[0], 0)

    def test_zero_budget_does_not_encode(self):
        calls = []
        def encoder(texts):
            calls.append(texts)
            return [[1, 0] for _ in texts]
        out = self.index.search('s', 'alpha', budget=0, mode='dense', encoder=encoder, model_id='m')
        self.assertEqual(calls, [])
        self.assertFalse(out['selected'])
        self.assertFalse(out['semantic_encoder_used'])

    def test_candidate_rows_are_batched(self):
        self.index.replace_scope('s', [Document(str(i), 's', 'chat', i, f'alpha {i}') for i in range(80)])
        sql = []
        self.index.db.set_trace_callback(sql.append)
        self.index.search('s', 'alpha', budget=600)
        row_queries = [q for q in sql if q.startswith('SELECT * FROM docs WHERE rowid=')]
        self.assertEqual(row_queries, [])

    def test_pack_does_not_keep_recounting_rejected_same_length(self):
        self.index.replace_scope('s', [Document(str(i), 's', 'chat', i, 'alpha '+'z'*500) for i in range(60)])
        calls = []
        original = TokenCounter.__call__
        def measured(counter, text):
            calls.append(text)
            return original(counter, text)
        with patch.object(TokenCounter, '__call__', measured):
            out = self.index.search('s', 'alpha', budget=600)
        self.assertLessEqual(out['budget_used'], 600)
        self.assertLess(len(calls), 15)

    def test_counter_subclass_cannot_bypass_budget(self):
        class DoubleBytes(TokenCounter):
            def __call__(self, text): return 2 * len(text.encode('utf-8'))
        self.index.counter = DoubleBytes()
        out = self.index.search('s', 'alpha', budget=180)
        self.assertEqual(out['budget_used'], 2 * len(out['context'].encode('utf-8')))
        self.assertLessEqual(out['budget_used'], 180)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional numpy unavailable')
    def test_foreign_writes_invalidate_dense_cache(self):
        enc = lambda texts: [[1, 0] if 'apple' in t or t == 'query' else [0, 1] for t in texts]
        self.index.embed('s', enc, 'm')
        self.assertEqual(self.index.search('s','query',mode='dense',encoder=enc,model_id='m')['ranked_ids'][0], 'a')
        db = sqlite3.connect(self.path)
        try:
            db.execute("UPDATE vectors SET vector='[0,1]' WHERE id='a'")
            db.execute("UPDATE vectors SET vector='[1,0]' WHERE id='b'")
            db.commit()
        finally:
            db.close()
        self.assertEqual(self.index.search('s','query',mode='dense',encoder=enc,model_id='m')['ranked_ids'][0], 'b')

    def test_result_cache_returns_independent_objects(self):
        first = self.index.search('s', 'alpha')
        self.assertFalse(first['result_cache_hit'])
        first['selected'][0]['text'] = 'poisoned-caller-copy'
        again = self.index.search('s', 'alpha')
        self.assertTrue(again['result_cache_hit'])
        self.assertNotIn('poisoned-caller-copy', str(again))

    def test_external_replace_invalidates_result_cache(self):
        self.index.search('s', 'alpha')
        other = SearchIndex(self.path)
        try:
            other.replace_scope('s', [Document('new', 's', 'chat', 0, 'alpha new')])
        finally:
            other.close()
        out = self.index.search('s', 'alpha')
        self.assertFalse(out['result_cache_hit'])
        self.assertEqual([x['id'] for x in out['selected']], ['new'])

    def test_mutations_and_lookups_share_instance_lock(self):
        def work(i):
            if i % 2:
                self.index.search('s', 'alpha')
            else:
                self.index.replace_scope('s', self.docs)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(24)))
        self.assertEqual(len(self.index.rows('s')), 2)

    def test_cache_is_bounded(self):
        for i in range(80):
            self.index.search('s', 'alpha '+str(i))
        self.assertLessEqual(len(self.index._results), 64)

    def test_no_cached_bypass_for_invalid_boolean(self):
        self.index.search('s', 'alpha', candidate_limit=1)
        with self.assertRaises(ValueError):
            self.index.search('s', 'alpha', candidate_limit=True)

    def test_model_identity_mismatch_rejected(self):
        class Encoder:
            model_id='actual'
            def __call__(self, texts): return [[1, 0] for _ in texts]
        with self.assertRaises(ValueError):
            self.index.embed('s', Encoder(), 'different')

    def test_native_byte_packing_matches_manual_accounting(self):
        for size in (1, 20, 100, 600):
            out = self.index.search('s', 'alpha', budget=size)
            self.assertEqual(out['budget_used'], len(out['context'].encode('utf-8')))
            self.assertLessEqual(out['budget_used'], size)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional numpy unavailable')
    def test_empty_dense_scope_does_not_claim_model_success(self):
        self.index.replace_scope('s', [])
        with self.assertRaises(ValueError):
            self.index.search('s', 'alpha', mode='dense', encoder=lambda t:[[1,0]], model_id='m')


class ObservationRepairs(unittest.TestCase):
    now = '2026-09-06T12:00:00+00:00'
    def record(self, text):
        return {'id':'m','session':'s','role':'assistant','source':'cli',
                'timestamp':'2026-09-05T12:00:00+00:00','text':text}
    def anchor(self):
        return {'id':'a','version':'v1','aliases':['alpha','bravo'],'min_anchors':2}

    def test_later_anchor_occurrence_can_form_window(self):
        rows, meta = scan([self.record('alpha '+'x '*200+'bravo alpha')], [self.anchor()], scope='s', now=self.now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['weight'], 0.0)

    def test_unclosed_fence_not_scanned_as_prose(self):
        self.assertNotIn('alpha', visible_text('outside\n```\nalpha bravo'))

    def test_anchor_validation_on_empty_input(self):
        with self.assertRaises(ValueError):
            scan([], [{'id':'a','version':'v','aliases':[[]]}], scope='s', now=self.now)

    def test_casefold_duplicate_not_two_independent_anchors(self):
        spec = {'id':'a','version':'v','aliases':['Alpha','alpha'],'min_anchors':2,'case_insensitive':True}
        with self.assertRaises(ValueError):
            scan([self.record('alpha')], [spec], scope='s', now=self.now)

    def test_case_insensitive_review_source_excluded(self):
        r = self.record('alpha bravo');r['source']='REVIEW'
        self.assertEqual(scan([r],[self.anchor()],scope='s',now=self.now)[0], [])

    def test_canonical_timestamp_deduplication(self):
        a = self.record('alpha bravo'); b = dict(a, id='copy', session='branch', timestamp='2026-09-05T12:00:00Z')
        self.assertEqual(len(scan([a,b],[self.anchor()],scope='s',now=self.now)[0]),1)

    def test_no_hit_or_confirmation_fabrication(self):
        records = [self.record('alpha bravo')]; anchors=[self.anchor()]
        originals = copy.deepcopy((records, anchors))
        observations, _ = scan(records, anchors, scope='s', now=self.now)
        self.assertEqual((records, anchors), originals)
        self.assertEqual(observations[0]['type'], 'mention_observed')
        self.assertEqual(observations[0]['exposure'], 'unknown')

    def test_tilde_fences_are_not_prose(self):
        self.assertEqual(visible_text('outside\n~~~python\nalpha bravo\n~~~\nafter'), 'outside\nafter')

    def test_large_observation_batch_is_marked_partial(self):
        rows, meta = scan([self.record('alpha bravo')], [self.anchor()], scope='s', now=self.now, max_bytes=1)
        self.assertTrue(meta['partial'])
        self.assertFalse(rows)

    def test_many_repetitions_are_bounded_and_disclosed(self):
        _, meta = scan([self.record(('alpha '*400)+'bravo')], [self.anchor()], scope='s', now=self.now)
        self.assertTrue(meta['partial'])
        self.assertTrue(meta['occurrence_limit_reached'])

    def test_output_cannot_be_a_source_database(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/'state.db'
            db = sqlite3.connect(path)
            try:
                db.execute('CREATE TABLE messages(id INTEGER)')
                db.commit()
            finally:
                db.close()
            before = path.read_bytes()
            rows, _ = scan([self.record('alpha bravo')], [self.anchor()], scope='s', now=self.now)
            with self.assertRaises(ValueError):
                store_observations(path, rows)
            self.assertEqual(before, path.read_bytes())

    def test_sidecar_rejects_fabricated_hit(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/'observations.db'
            with self.assertRaises(ValueError):
                store_observations(path, [{'event_id':'e','type':'hit','weight':2.0}])
            self.assertFalse(path.exists())


class SourceRepairs(unittest.TestCase):
    def make(self, root):
        p = Path(root)/'state.db'
        db = sqlite3.connect(p)
        try:
            db.executescript('''CREATE TABLE sessions(id TEXT, source TEXT, hidden INTEGER, profile_name TEXT);
              CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, content TEXT,
                timestamp REAL, active INTEGER, _compressed_summary INTEGER);
              INSERT INTO sessions VALUES('a','cron',0,'p');
              INSERT INTO sessions VALUES('b','cli',0,'p');
              INSERT INTO messages VALUES(1,'a','assistant','background',1,1,0);
              INSERT INTO messages VALUES(2,'a','assistant','background',2,1,0);
              INSERT INTO messages VALUES(3,'b','assistant','wanted',3,1,0);''')
            db.commit()
        finally:
            db.close()
        return p
    def test_background_rows_do_not_consume_output_limit(self):
        with tempfile.TemporaryDirectory() as t:
            p = self.make(t);before=p.read_bytes()
            rows, meta = read_hermes(p,'s',max_rows=1)
            self.assertEqual([r['text'] for r in rows], ['wanted'])
            self.assertFalse(meta['partial'])
            self.assertEqual(before, p.read_bytes())
    def test_invalid_read_limits_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = self.make(t)
            for kwargs in ({'max_rows':-1}, {'max_rows':True}, {'timeout':float('nan')}, {'timeout':0}):
                with self.assertRaises(ValueError):
                    read_hermes(p, 's', **kwargs)


class PolicyAndEvaluationRepairs(unittest.TestCase):
    def test_boolean_curve_parameter_rejected(self):
        with self.assertRaises(ValueError):
            Policy(half_life=True)
    def test_duplicate_plan_ids_rejected(self):
        e={'id':'a','status':'active','events':[],'pinned':True}
        with self.assertRaises(ValueError):
            plan([e,dict(e)],dt.date(2026,9,6),600,Policy(),lambda e:10)
    def test_string_pin_rejected(self):
        with self.assertRaises(ValueError):
            plan([{'id':'a','status':'active','events':[],'pinned':'false'}],dt.date(2026,9,6),600,Policy(),lambda e:10)
    def test_category_names_follow_locomo(self):
        self.assertEqual(benchmark.CATEGORY[1], 'multi_hop')
        self.assertEqual(benchmark.CATEGORY[4], 'single_hop')
    def test_eval_duplicate_conversation_rejected(self):
        sample={'sample_id':'s','conversation':{'session_1':[{'dia_id':'D1:1','text':'alpha'}]},'qa':[]}
        class Counter:
            name='utf8_bytes'
            def __call__(self,text):return len(text.encode())
        with self.assertRaises(ValueError):
            benchmark.run([sample,sample],Counter(),['sparse'],[600])

    def test_non_string_confirmation_is_not_evidence(self):
        entry = {'events':[{'type':'confirm','event_id':'e','t':'2026-09-06','evidence':42}]}
        with self.assertRaises(ValueError):
            activity(entry, dt.date(2026,9,6), Policy())

    def test_compact_dates_not_silently_accepted(self):
        entry = {'events':[{'type':'hit','event_id':'e','t':'20260906'}]}
        with self.assertRaises(ValueError):
            activity(entry, dt.date(2026,9,6), Policy())

    def test_malformed_event_list_rejected(self):
        with self.assertRaises(ValueError):
            activity({'events':None}, dt.date(2026,9,6), Policy())

    def test_ranking_metrics_are_emitted_on_actual_run(self):
        sample={'sample_id':'s','conversation':{'session_1':[{'dia_id':'D1:1','text':'alpha'}]},
                'qa':[{'category':4,'question':'alpha','evidence':['D1:1']}]}
        out = benchmark.run([sample],TokenCounter(),['sparse'],[600])
        agg=out['summaries']['sparse@600']['main_categories_1_to_4']
        self.assertEqual(agg['mrr'],1.0)
        self.assertEqual(agg['ndcg'],1.0)
        self.assertIsNotNone(agg['latency_ms']['p99'])
        self.assertEqual(out['idf_scope'],'one_database_per_conversation')

    def test_rank_metrics_not_invented_for_legacy_rows(self):
        row={'evidence_count':1,'fully_resolved':True,'hits':1,'candidate_hits':1,
             'selected_count':1,'budget_used':10,'total_ms':1,'query_embedding_ms':0}
        agg=benchmark.aggregate([row])
        self.assertIsNone(agg['mrr'])
        self.assertIsNone(agg['ndcg'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
