"""Synthetic regression suite; no real histories, network calls or gold-derived index."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from thm.retrieval import Document, SearchIndex, TokenCounter, normalize_vectors, terms
from thm.sources import locomo_documents, read_hermes
from thm.observations import scan, summarize, store_observations
from thm.policy import Policy, activity, kernel, plan, replay


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = SearchIndex(self.root/'recall.sqlite')

    def tearDown(self):
        self.index.close(); self.tmp.cleanup()

    def docs(self):
        return [Document('a','p','s',0,'The workspace uses the PostgreSQL database.','Alice'),
                Document('b','p','s',1,'It runs at port 5432.','Bob'),
                Document('c','p','s2',0,'The garden contains trees.','Alice')]

    def test_scope_isolation(self):
        self.index.replace_scope('p',self.docs())
        self.index.replace_scope('q',[Document('a','q','s',0,'Secret unrelated project uses PostgreSQL.')])
        out=self.index.search('p','PostgreSQL',budget=600)
        self.assertNotIn('Secret',out['context'])
        self.assertEqual(out['scope'],'p')

    def test_missing_scope_explicit_failure(self):
        with self.assertRaisesRegex(ValueError,'scope not indexed'): self.index.search('missing','q')

    def test_real_source_text_in_context(self):
        self.index.replace_scope('p',self.docs())
        out=self.index.search('p','PostgreSQL',budget=600)
        self.assertIn('PostgreSQL',out['context'])
        self.assertTrue(all(x['complete'] for x in out['selected']))

    def test_no_token_budget_overflow(self):
        self.index.replace_scope('p',self.docs())
        for budget in [0,1,50,100,300,600]:
            out=self.index.search('p','database garden port',budget=budget)
            self.assertLessEqual(len(out['context'].encode()),budget)
            self.assertEqual(out['budget_used'],len(out['context'].encode()))

    def test_oversized_first_does_not_abort_packing(self):
        docs=[Document('a','p','s',0,'database '*2000),Document('b','p','s',1,'database port 5432')]
        self.index.replace_scope('p',docs)
        out=self.index.search('p','database',budget=150)
        self.assertIn('b',[x['id'] for x in out['selected']])
        self.assertNotIn('a',[x['id'] for x in out['selected']])

    def test_cjk_bigrams(self):
        self.index.replace_scope('p',[Document('a','p','s',0,'请使用中文回答，并保留数字单位。')])
        out=self.index.search('p','中文回答',budget=600)
        self.assertEqual(out['selected'][0]['id'],'a')

    def test_negation_and_units_preserved(self):
        self.index.replace_scope('p',[Document('a','p','s',0,'Do not use 50 mg; the amount is 5 mg.')])
        self.assertIn('Do not use 50 mg',self.index.search('p','amount mg')['context'])

    def test_safe_fts_special_characters(self):
        self.index.replace_scope('p',self.docs())
        out=self.index.search('p','" OR NOT * PostgreSQL --')
        self.assertTrue(out['selected'])

    def test_replace_invalidates_removed_documents(self):
        self.index.replace_scope('p',self.docs())
        self.index.replace_scope('p',[])
        self.assertEqual(self.index.search('p','PostgreSQL')['selected'],[])

    def test_replace_idempotent(self):
        self.index.replace_scope('p',self.docs())
        self.assertFalse(self.index.replace_scope('p',self.docs())['changed'])

    def test_duplicate_ids_refused_no_partial_replace(self):
        self.index.replace_scope('p',self.docs())
        with self.assertRaises(ValueError): self.index.replace_scope('p',self.docs()*2)
        self.assertEqual(len(self.index.rows('p')),3)

    def test_neighbors_are_packed_as_actual_sources(self):
        self.index.replace_scope('p',self.docs())
        out=self.index.search('p','PostgreSQL',neighbor_turns=1,budget=600)
        self.assertIn('It runs at port 5432.',out['context'])
        self.assertIn('b',[x['id'] for x in out['selected']])

    def test_result_repeat_order(self):
        self.index.replace_scope('p',self.docs())
        a=self.index.search('p','port database'); b=self.index.search('p','port database')
        self.assertEqual(a['selected'],b['selected'])

    def test_dense_requires_explicit_model(self):
        self.index.replace_scope('p',self.docs())
        with self.assertRaises(ValueError): self.index.search('p','database',mode='hybrid')

    def test_embedding_validation(self):
        for value in [[],[[0,0]],[[float('nan'),1]],[[1],[1,2]]]:
            with self.assertRaises(ValueError): normalize_vectors(value,1)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional numpy unavailable')
    def test_dense_and_cache_use_real_path_with_synthetic_encoder(self):
        self.index.replace_scope('p',self.docs())
        calls=[]
        def encoder(texts):
            calls.append(list(texts))
            return [[1,0] if 'database' in t or 'storage' in t else [0,1] for t in texts]
        self.index.embed('p',encoder,'synthetic-fixed-v1')
        out=self.index.search('p','storage',mode='dense',budget=200,encoder=encoder,model_id='synthetic-fixed-v1')
        self.assertEqual(out['ranked_ids'][0],'a')
        self.assertFalse(out['query_embedding_cache_hit'])
        out=self.index.search('p','storage',mode='dense',budget=200,encoder=encoder,model_id='synthetic-fixed-v1')
        self.assertTrue(out['query_embedding_cache_hit'])
        self.assertEqual(len(calls),2)
        self.index.replace_scope('p',self.docs()[:1])
        with self.assertRaisesRegex(ValueError,'missing/stale'):
            self.index.search('p','storage',mode='dense',encoder=encoder,model_id='synthetic-fixed-v1')

    def test_qa_cannot_change_index(self):
        s={'sample_id':'p','conversation':{'speaker_a':'A','session_1':[{'dia_id':'D1:1','speaker':'A','text':'A plain source.'}]},
           'qa':[{'question':'q','answer':'secret','evidence':['D1:1']}], 'observation':{'secret':'label'}}
        a=list(locomo_documents(s)); s['qa']=[]; s['observation']={}
        self.assertEqual(a,list(locomo_documents(s)))
        self.assertNotIn('secret',a[0].text)


class PolicyTests(unittest.TestCase):
    def row(self):
        return {'id':'a','status':'active','pinned':False,'cost_class':'med',
                'events':[{'type':'hit','t':'2026-01-01','event_id':'1'}]}

    def test_halflife_calibrated(self):
        for name in ['power','exponential','bounded_power']:
            p=Policy(kernel=name,half_life=30)
            self.assertAlmostEqual(kernel(30,p),.5)

    def test_monotonic_curves(self):
        for name in ['legacy','power','exponential','mixture','bounded_power']:
            p=Policy(kernel=name)
            values=[kernel(t,p) for t in range(400)]
            self.assertTrue(all(a>=b for a,b in zip(values,values[1:])))

    def test_window_eliminates_unbounded_old_tail(self):
        self.assertEqual(activity(self.row(),date(2026,9,6),Policy()),0)
        self.assertGreater(activity(self.row(),date(2026,9,6),Policy(kernel='legacy')),0)

    def test_observations_zero_weight(self):
        row=self.row(); row['events'][0]['type']='mention_observed'
        self.assertEqual(activity(row,date(2026,1,1),Policy()),0)

    def test_duplicates_rejected(self):
        row=self.row(); row['events']*=2
        with self.assertRaises(ValueError): activity(row,date(2026,1,1),Policy())

    def test_daily_saturation(self):
        row=self.row(); row['events']=[dict(row['events'][0],event_id=str(i)) for i in range(10)]
        self.assertEqual(activity(row,date(2026,1,1),Policy()),2)

    def test_invalidity_before_score(self):
        row=self.row(); row['valid_until']='2026-01-01'; row['pinned']=True
        self.assertEqual(plan([row],date(2026,1,1),100,Policy(),lambda e:10)['selected'],[])

    def test_pin_over_budget_no_silent_drop(self):
        row=self.row(); row['pinned']=True
        self.assertEqual(plan([row],date(2026,1,1),1,Policy(),lambda e:10)['status'],'PINNED_OVER_BUDGET')

    def test_replay_scores_before_seeing_next_use(self):
        row=self.row(); row['events']=[]
        out=replay([{'id':'a','t':'2026-01-01'},{'id':'a','t':'2026-01-02'}],[row],Policy(),100,lambda e:10)
        self.assertEqual(out['residency_hits'],1)


class ObservationTests(unittest.TestCase):
    def records(self):
        return [{'id':'m1','session':'s1','role':'assistant','text':'Use port 9123 for the local endpoint.',
                 'timestamp':'2026-09-02T12:00:00+00:00','source':'cli'}]

    def anchors(self):
        return [{'id':'e1','version':'v1','aliases':['port 9123'],'valid_from':'2026-09-01T00:00:00+00:00'}]

    def run_scan(self,records=None,anchors=None):
        return scan(records or self.records(),anchors or self.anchors(),scope='test',now='2026-09-06T12:00:00+00:00')[0]

    def test_observation_not_hit(self):
        out=self.run_scan(); self.assertEqual(out[0]['weight'],0)
        self.assertEqual(out[0]['type'],'mention_observed'); self.assertEqual(out[0]['exposure'],'unknown')

    def test_quote_code_excluded(self):
        row=self.records()[0]; row['text']='> port 9123\n```\nport 9123\n```'
        self.assertEqual(self.run_scan([row]),[])

    def test_source_version_after_message_excluded(self):
        anchors=self.anchors(); anchors[0]['valid_from']='2026-09-04T00:00:00+00:00'
        self.assertEqual(self.run_scan(anchors=anchors),[])

    def test_other_role_excluded(self):
        row=self.records()[0]; row['role']='user'; self.assertEqual(self.run_scan([row]),[])

    def test_match_is_not_snapshot_proof(self):
        row=self.records()[0]; row['memory_versions']={'e1':'v1'}
        self.assertEqual(self.run_scan([row])[0]['exposure'],'snapshot_matched')
        self.assertEqual(self.run_scan([row])[0]['usefulness'],'unverified')

    def test_duplicate_branch_not_extra_evidence(self):
        a=self.records()[0]; b=dict(a,session='branch',id='m2')
        self.assertEqual(len(self.run_scan([a,b])),1)

    def test_distinct_days_and_sessions_required_for_review(self):
        a=self.records()[0]; b=dict(a,session='s2',id='m2',timestamp='2026-09-03T12:00:00+00:00')
        self.assertTrue(summarize(self.run_scan([a,b]))[0]['review_candidate'])

    def test_sidecar_idempotency(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'observations.db'; out=self.run_scan()
            self.assertEqual(store_observations(path,out),1)
            self.assertEqual(store_observations(path,out),0)
            self.assertFalse((Path(root)/'index.json').exists())


class SourceTests(unittest.TestCase):
    def test_real_sqlite_read_only_filters_and_full_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'state.db'; db=sqlite3.connect(path)
            db.executescript('''CREATE TABLE sessions(id TEXT,source TEXT,hidden INTEGER,profile_name TEXT);
              CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,
              active INTEGER,_compressed_summary INTEGER);
              INSERT INTO sessions VALUES('s','cli',0,'p');
              INSERT INTO messages VALUES(1,'s','assistant','real',1788600000,1,0);
              INSERT INTO messages VALUES(2,'s','assistant','inactive',1788600000,0,0);
              INSERT INTO messages VALUES(3,'s','assistant','summary',1788600000,1,1);''')
            db.commit(); db.close(); before=path.read_bytes()
            rows, meta=read_hermes(path,'p')
            self.assertEqual([r['text'] for r in rows],['real']); self.assertFalse(meta['partial'])
            self.assertEqual(path.read_bytes(),before)

    def test_missing_database_not_created(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'absent'
            with self.assertRaises(ValueError): read_hermes(path,'p')
            self.assertFalse(path.exists())

    def test_unknown_schema_not_empty_success(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'state.db'; sqlite3.connect(path).close()
            with self.assertRaises(ValueError): read_hermes(path,'p')


if __name__=='__main__': unittest.main()
