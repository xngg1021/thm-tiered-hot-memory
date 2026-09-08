import dataclasses
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from thm.retrieval import SearchIndex,Document,TokenCounter
from thm.features import RetrievalFeatures,parse_query,AliasIndex
from thm.runtime.identity import EmbeddingProfile,manifest,bounded_int,validate_vectors
from thm.runtime.storage import pack,unpack,EmbeddingCache,migrate_legacy
from thm.runtime.hardware import cpulist,quota_limit,HardwareProfile,probe
from thm.runtime.profiles import RuntimeProfile,from_dict,fingerprint
from thm.runtime.testing import FakeEncoder
from thm.runtime.scheduler import RuntimeScheduler
from thm.runtime.autotune import candidates,gate
from thm.runtime.micro import DOCUMENTS,QUERIES,CORPUS_SHA
from thm.runtime.receipts import write_receipt,import_dispatch


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.index=SearchIndex(self.root/'index.sqlite')
        self.docs=[Document(str(i),'s','session',i,'source alpha beta '+str(i),speaker='Alice',timestamp='2024-01-01',source='file:public') for i in range(6)]
        self.index.replace_scope('s',self.docs)
    def tearDown(self):self.index.close();self.tmp.cleanup()
    def profile(self,enc,policy='auto-safe',**kw):
        return RuntimeProfile(enc.profile.id,fingerprint(probe(),enc.profile.source_manifest_sha256,embedding_profile=enc.profile.id),backend=enc.profile.backend,device=enc.profile.device,policy=policy,semantic_gate='strict',**kw)
    def test_core_imports_no_optional_stack_or_keys(self):
        code="""
import sys, socket, tempfile
class Block:
 def find_spec(self, fullname, *args):
  if fullname.split('.')[0] in ('torch','numpy','sentence_transformers','openai','anthropic'): raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
socket.socket.connect=lambda *a: (_ for _ in ()).throw(AssertionError('network'))
from thm.retrieval import SearchIndex,Document
from thm.runtime.hardware import probe
from thm.mcp_legacy_server import THMLegacyMCPServer
from thm.harness import HarnessConfig
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
 db=Path(tmp)/'i.sqlite';i=SearchIndex(db);i.replace_scope('s',[Document('1','s','x',0,'hello deterministic memory')])
 assert i.search('s','hello',mode='literal')['selected']
 assert i.search('s','hello',mode='sparse')['selected']
 assert not i.search('s','hello')['answer_generated']
 i.close()
 probe()
 assert not any(x in sys.modules for x in ('torch','numpy','sentence_transformers'))
"""
        # Import the actual stdio server via CLI below; no optional SDK required.
        code=code.replace('from thm.mcp_legacy_server import THMLegacyMCPServer\n','import thm.mcp_legacy_server\n')
        env={k:v for k,v in os.environ.items() if not k.endswith(('API_KEY','TOKEN'))}
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,env=env)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_doctor_without_model(self):
        out=subprocess.run([sys.executable,'-m','thm','runtime','doctor'],capture_output=True,text=True,check=True)
        value=json.loads(out.stdout);self.assertTrue(value['core_only_available']);self.assertEqual(value['generation_calls'],0)
        self.assertIsNone(value['hardware']['observed_kernel_dispatch'])
    def test_batch_validation(self):
        for value in (True,False,0,-1,257,1.5):
            with self.assertRaises(ValueError):self.index.embed('s',FakeEncoder(),'test-only',document_batch_size=value)
            with self.assertRaises(ValueError):self.index.search_many('s',['x'],query_batch_size=value)
    def test_hardware_parsing_and_quota(self):
        self.assertEqual(cpulist('0-2,7'),[0,1,2,7]);self.assertEqual(quota_limit('50000 100000'),.5)
        self.assertIsNone(quota_limit('max 100000'));self.assertIsNone(quota_limit('garbage'))
        for x in ('4-2','-1','2-9999999'):
            with self.assertRaises(ValueError):cpulist(x)
        self.assertIsNone(HardwareProfile('unknown','unknown','unknown').physical_cores_if_known)
    def test_candidate_bound_uses_process_allocation(self):
        h=HardwareProfile('x86_64','Linux','x',installed_logical_cpus=128,process_available_cpus=2,physical_cores_if_known=64)
        c=candidates(h,[('torch_fp32','cpu'),('torch_fp32','cuda')],maximum=7)
        self.assertLessEqual(len(c),7);self.assertTrue(all(x['threads']==1 for x in c))
        self.assertEqual({x['device'] for x in c},{'cpu','cuda'})
    def test_profile_identity_and_freshness(self):
        a=FakeEncoder();b=FakeEncoder(device='cuda');self.assertNotEqual(a.profile.id,b.profile.id)
        p=self.profile(a);self.assertEqual(from_dict(p.identity()),p)
        with self.assertRaises(ValueError):p.require_fresh('0'*64)
        for kw in ({'threads':True},{'threads':-1},{'precision':'int8'},{'query_batch_size':0}):
            with self.assertRaises(ValueError):self.profile(a,**kw)
        h=probe();left=fingerprint(h,'a'*64);h.process_available_cpus=(h.process_available_cpus or 1)+1
        self.assertNotEqual(left,fingerprint(h,'a'*64))
    def test_manifest_content_bound_and_symlink_refusal(self):
        root=self.root/'model';root.mkdir();(root/'weights').write_bytes(b'abc');a=manifest(root)['sha256']
        (root/'weights').write_bytes(b'abd');self.assertNotEqual(a,manifest(root)['sha256'])
        if os.name!='nt':
            (root/'link').symlink_to(root/'weights')
            with self.assertRaises(ValueError):manifest(root)
    def test_blob_roundtrip_corruption(self):
        v=FakeEncoder().encode_one('x');blob=pack(v);r=unpack(blob,8)
        self.assertLess(max(abs(a-b) for a,b in zip(v,r)),1e-7)
        for b,d in ((blob[:-1],8),(blob,7),(b'\0'*32,8)):
            with self.assertRaises(ValueError):unpack(b,d)
        for v in ([float('nan')],[float('inf')],[True]):
            with self.assertRaises(ValueError):pack(v)
    def test_document_batch_reaches_encoder(self):
        enc=FakeEncoder(document_batch_size=2);receipt=self.index.embed('s',enc,enc.model_id)
        self.assertEqual([len(x) for x in enc.calls],[2,2,2]);self.assertEqual(receipt['document_batch_size'],2)
    def test_profiles_coexist_without_mixing(self):
        a=FakeEncoder();b=FakeEncoder(device='cuda');self.index.embed('s',a,a.model_id)
        with self.assertRaises(ValueError):self.index.search('s','alpha',mode='dense',encoder=b,model_id=b.model_id)
        self.index.embed('s',b,b.model_id,vector_storage='blob')
        for enc in (a,b):self.assertTrue(self.index.search('s','alpha',mode='dense',encoder=enc,model_id=enc.model_id)['selected'])
        self.assertEqual(self.index.db.execute('SELECT COUNT(*) FROM vector_generations').fetchone()[0],2)
    def test_blob_corruption_fail_closed(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id,vector_storage='blob')
        with self.index.db:self.index.db.execute("UPDATE vectors_v2 SET vector=x'00' WHERE id='0'")
        with self.assertRaises(ValueError):self.index.search('s','alpha',mode='dense',encoder=e,model_id=e.model_id)
    def test_legacy_migration_preserves_json(self):
        enc=FakeEncoder()
        class Legacy:
            model_id='test-only'
            def __call__(self,t):return enc(t)
        self.index.embed('s',Legacy(),'test-only');old=list(self.index.db.execute('SELECT * FROM vectors'))
        generation=self.index.db.execute("SELECT generation FROM scopes WHERE scope='s'").fetchone()[0]
        receipt=migrate_legacy(self.index,'s','test-only',enc.profile,generation)
        self.assertTrue(receipt['legacy_preserved']);self.assertEqual(old,list(self.index.db.execute('SELECT * FROM vectors')))
        with self.assertRaises(ValueError):migrate_legacy(self.index,'s','test-only',enc.profile,generation)
        self.assertTrue(self.index.search('s','alpha',mode='dense',encoder=enc,model_id=enc.model_id)['selected'])
    def test_exact_cache_cross_scope_only_compute(self):
        enc=FakeEncoder();cache=EmbeddingCache(self.root/'cache.sqlite')
        try:
            a=cache.encode(enc,['Alice: hello','Alice: hello']);self.assertEqual(len(enc.calls[0]),1)
            self.assertEqual(a,cache.encode(enc,['Alice: hello','Alice: hello']))
            cache.encode(enc,['Bob: hello','Alice: hello ']);self.assertEqual(len(enc.calls),2)
            other=FakeEncoder(device='cuda');cache.encode(other,['Alice: hello']);self.assertEqual(len(other.calls),1)
            self.index.embed('s',enc,enc.model_id,embedding_cache=cache)
            otherdocs=[dataclasses.replace(d,scope='private') for d in self.docs];self.index.replace_scope('private',otherdocs)
            before=len(enc.calls);self.index.embed('private',enc,enc.model_id,embedding_cache=cache);self.assertEqual(before,len(enc.calls))
            self.assertEqual(self.index.search('s','alpha',encoder=enc,model_id=enc.model_id,mode='hybrid')['scope'],'s')
            self.assertEqual([r[1] for r in cache.db.execute('PRAGMA table_info(embedding_cache)')],['profile','input_sha','input_bytes','dimension','vector'])
        finally:cache.close()
    def test_generation_change_during_embedding_no_partial_publish(self):
        entered=threading.Event();release=threading.Event();enc=FakeEncoder();original=enc.encode_many
        def blocked(texts):entered.set();release.wait(5);return original(texts)
        enc.encode_many=blocked;errors=[]
        def worker():
            try:self.index.embed('s',enc,enc.model_id)
            except Exception as e:errors.append(e)
        thread=threading.Thread(target=worker);thread.start();self.assertTrue(entered.wait(5))
        self.index.replace_scope('s',[dataclasses.replace(self.docs[0],text='changed')]);release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(len(errors),1)
        self.assertEqual(self.index.db.execute('SELECT COUNT(*) FROM vectors_v2').fetchone()[0],0)
        self.assertFalse(self.index.db.in_transaction)
    def test_search_many_matches_sequential(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id);queries=['alpha','beta','source 2','alpha']
        singles=[self.index.search('s',q,mode='hybrid',encoder=e,model_id=e.model_id) for q in queries]
        batch=self.index.search_many('s',queries,mode='hybrid',encoder=e,model_id=e.model_id,query_batch_size=3)
        for a,b in zip(singles,batch):
            for key in ('context','ranked_ids','budget_used','selected'):self.assertEqual(a[key],b[key])
        self.assertEqual(batch[0]['batch_receipt']['operation'],'GEMM');self.assertFalse(self.index.db.in_transaction)
    def test_two_readers_and_readonly_blob(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id,vector_storage='blob');readonly=SearchIndex(self.root/'index.sqlite',readonly=True)
        errors=[]
        def work(index):
            try:
                for _ in range(5):index.search('s','alpha',mode='hybrid',encoder=e,model_id=e.model_id)
            except Exception as exc:errors.append(exc)
        threads=[threading.Thread(target=work,args=(i,)) for i in (self.index,readonly)]
        for t in threads:t.start()
        for t in threads:t.join()
        readonly.close();self.assertEqual(errors,[])
    def test_overlap_parity_and_worker_cleanup(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        a=self.index.search('s','query',mode='hybrid',encoder=e,model_id=e.model_id);self.index._clear_caches()
        b=self.index.search_overlap('s','query',mode='hybrid',encoder=e,model_id=e.model_id)
        self.assertEqual(a['context'],b['context']);self.assertIsNone(self.index._query_future)
        self.assertFalse(any(t.name.startswith('thm-encoder') for t in threading.enumerate()))
    def test_scheduler_failure_and_sparse_receipt(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id);p=self.profile(e);e.kind='out-of-memory'
        with RuntimeScheduler(self.index,[p],{e.profile.id:e},fallback_to_sparse=True) as scheduler:
            r=scheduler.search('s','alpha',mode='hybrid');self.assertEqual(r['mode'],'sparse')
            self.assertEqual(r['runtime_receipt']['fallback_mode'],'fallback-to-sparse');self.assertIsNone(r['runtime_receipt']['actual_profile'])
    def test_reference_scheduler_fails_closed(self):
        from dataclasses import replace
        e=FakeEncoder('fails');e.profile=replace(e.profile,backend='torch_fp32');p=self.profile(e,'reference')
        with RuntimeScheduler(self.index,[p],{e.profile.id:e},policy='reference') as scheduler:
            with self.assertRaises(ValueError):scheduler.search('s','alpha',mode='hybrid')
    def test_scheduler_pinning_and_shutdown(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id);p=self.profile(e)
        scheduler=RuntimeScheduler(self.index,[p],{e.profile.id:e});future=scheduler.submit('s','alpha',mode='hybrid')
        self.assertEqual(future.result()['runtime_receipt']['actual_profile'],p.id)
        with self.assertRaises(ValueError):scheduler.search('s','alpha',requested_profile='unknown')
        scheduler.close()
        with self.assertRaises(RuntimeError):scheduler.search('s','alpha')
        self.assertFalse(any(t.name.startswith('thm-runtime') for t in threading.enumerate()))
    def test_gate_compares_retrieval_not_only_speed(self):
        e=FakeEncoder();data={'status':'ok','identity':e.identity(),'corpus_sha256':CORPUS_SHA,'document_vectors':e(DOCUMENTS),'query_vectors':e(QUERIES)}
        self.assertTrue(gate(data,data)['admitted'])
        drift=json.loads(json.dumps(data));drift['query_vectors']=list(reversed(drift['query_vectors']))
        self.assertFalse(gate(data,drift)['admitted'])
        self.assertFalse(gate(data,{'status':'failed'})['admitted'])
    def test_receipt_exclusive_and_dispatch_not_inferred(self):
        p=self.root/'r.json';write_receipt(p,{'observed_kernel_dispatch':None})
        with self.assertRaises(FileExistsError):write_receipt(p,{})
        with self.assertRaises(ValueError):import_dispatch(p,'ep1-x')
    def test_features_default_and_legacy_entity(self):
        base=self.index.search('s','Alice alpha');explicit=self.index.search('s','Alice alpha',features=RetrievalFeatures())
        self.assertEqual(base['context'],explicit['context'])
        old=self.index.search('s','Alice alpha',entity_projection=True);new=self.index.search('s','Alice alpha',features=RetrievalFeatures(entity=True))
        self.assertEqual(old['context'],new['context'])
    def test_alias_is_scoped_locator_and_no_write(self):
        config=RetrievalFeatures(explicit_alias=True,aliases=(('工程师','Alice'),))
        before=self.index.db.total_changes;r=self.index.search('s','工程师',features=config)
        self.assertTrue(r['selected']);self.assertEqual(before,self.index.db.total_changes)
        with self.assertRaises(ValueError):RetrievalFeatures(explicit_alias=1)
    def test_query_parser_fails_soft(self):
        self.assertIsNone(parse_query('ordinary unstructured text').kind)
        self.assertEqual(parse_query('Alice AND Bob').conjunction,'AND')
        self.assertEqual(parse_query('when before 2024-99-88').dates,())
        self.assertEqual(parse_query('latest XNG-42').identifiers,('XNG-42',))
    def test_temporal_is_query_conditioned(self):
        docs=[Document('old','t','s',0,'alpha launch',timestamp='2020-01-01'),Document('new','t','s',1,'alpha launch',timestamp='2024-01-01')]
        self.index.replace_scope('t',docs)
        first=self.index.search('t','first alpha launch',features=RetrievalFeatures(temporal=True))
        latest=self.index.search('t','latest alpha launch',features=RetrievalFeatures(temporal=True))
        self.assertEqual(first['ranked_ids'][0],'old');self.assertEqual(latest['ranked_ids'][0],'new')
    def test_segments_never_inherit_complete_credit(self):
        text='irrelevant filler '*100+'. alpha specific evidence. '+'other filler '*100
        self.index.replace_scope('seg',[Document('parent','seg','x',0,text)])
        r=self.index.search('seg','alpha',budget=180,features=RetrievalFeatures(segment=True))
        self.assertTrue(r['selected']);self.assertFalse(r['selected'][0]['complete']);self.assertEqual(r['complete_evidence_ids'],[])
        seg=r['selected'][0];self.assertEqual(text[seg['span_start']:seg['span_end']],seg['text']);self.assertLessEqual(r['budget_used'],180)
    def test_association_bounded_and_nonmutating(self):
        from thm.features import expand
        rows=self.index.rows('s');before=self.index.db.total_changes
        out,edges=expand(rows[:1],rows,RetrievalFeatures(association=True,max_hops=2,max_neighbors=2))
        self.assertLessEqual(len(edges),2);self.assertEqual(before,self.index.db.total_changes)
        self.assertTrue(all(e['relation'] in ('same-explicit-speaker','same-source','session-adjacency','explicit-identifier-reference') for e in edges))

if __name__=='__main__':unittest.main()

class RuntimeIntegrationTests(unittest.TestCase):
    def test_local_verification_plan_reserves_namespace(self):
        from argparse import Namespace
        from research.runtime.verify import execute
        with tempfile.TemporaryDirectory() as temp:
            args=Namespace(model_path='local-model',model_id='local',locomo_dataset='locomo',lme_dataset='lme',output_dir=str(Path(temp)/'new'),plan_only=True,include_approximate=True,retrieval_ab=True,max_candidates=12)
            p=execute(args);self.assertEqual(p['document_batch_candidates'],[16,32,64,128,256])
            with self.assertRaises(FileExistsError):execute(args)
    def test_census_uses_actual_speaker_prefixed_input(self):
        from research.runtime.census import census
        data=[{'haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'hello'}]]} for _ in range(2)]
        result=census(data);self.assertEqual(result['duplicate_count'],1)
        self.assertEqual(result['bytes_avoided'],len('user: user: hello'.encode()))
        self.assertIsNone(result['speedup'])
    def test_core_research_execution_and_feature_ab(self):
        from research.recall.benchmark import run
        from thm.runtime.research import ExecutionConfig
        data=[{'sample_id':'a','conversation':{'session_1':[{'dia_id':'D1:1','speaker':'Alice','text':'alpha launch'}]},'qa':[{'question':'alpha','category':4,'evidence':['D1:1']}]}]
        ref=run(data,TokenCounter(),['sparse'],[600],execution_config=ExecutionConfig())
        opt=run(data,TokenCounter(),['sparse'],[600],execution_config=ExecutionConfig(policy='auto-throughput',features=RetrievalFeatures(query_grammar=True)))
        self.assertEqual(ref['rows'][0]['selected_ids'],opt['rows'][0]['selected_ids']);self.assertEqual(ref['runtime']['generation_calls'],0)
        with self.assertRaises(ValueError):ExecutionConfig(features=RetrievalFeatures(entity=True))
    def test_lme_core_execution_preserves_instance_idf(self):
        from research.recall.lme_retrieval import run
        from thm.runtime.research import ExecutionConfig
        data=[{'question_id':q,'question':'hello','haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'hello world'}]],'answer_session_ids':['s']} for q in ('a','b')]
        r=run(data,TokenCounter(),['sparse'],[600],execution_config=ExecutionConfig())
        self.assertEqual(r['idf_scope'],'one_database_per_instance');self.assertEqual(len(r['rows']),2)
    def test_profile_invalidation_is_effective(self):
        from thm.runtime.cli import main
        from thm.runtime.profiles import load_profile
        import contextlib,io
        e=FakeEncoder();p=RuntimeProfile(e.profile.id,'a'*64,policy='reference',semantic_gate='reference')
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'profile.json';write_receipt(source,p.identity());output=Path(temp)/'invalidation.json'
            with contextlib.redirect_stdout(io.StringIO()):code=main(['invalidate-profile','--profile',str(source),'--output',str(output)])
            self.assertEqual(code,0)
            with self.assertRaises(ValueError):load_profile(source)
            self.assertEqual(json.loads(source.read_text()),json.loads(json.dumps(p.identity())))
    def test_autotune_fake_runner_selects_admitted_and_survives_failure(self):
        from thm.runtime.autotune import autotune
        e=FakeEncoder()
        def runner(config,timeout):
            if config['device']=='cuda':return {'status':'failed','error_type':'MemoryError'}
            # Binary unit vectors keep this winner-selection fixture exactly invariant across GEMV/GEMM.
            vectors=lambda texts:[[float(j==i%8) for j in range(8)] for i,_ in enumerate(texts)]
            return {'status':'ok','identity':e.identity(),'corpus_sha256':CORPUS_SHA,'document_vectors':vectors(DOCUMENTS),'query_vectors':vectors(QUERIES),
                'single_query_p95_ms':10/config['threads'],'queries_per_second':config['query_batch_size']*10,'docs_per_second':100}
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'weights').write_bytes(b'fixture')
            e.profile=dataclasses.replace(e.profile,backend='torch_fp32',source_manifest_sha256=manifest(temp)['sha256'])
            r=autotune(temp,'test-only',backends=[('torch_fp32','cpu'),('torch_fp32','cuda')],maximum=4,runner=runner)
            self.assertEqual(r['status'],'calibrated');self.assertEqual(r['runtime_profile']['device'],'cpu')
            self.assertTrue(any(t['result']['status']=='failed' for t in r['trials']))
    def test_no_reference_thread_or_batch_autoselection(self):
        h=HardwareProfile('x','y','z',process_available_cpus=32)
        c=candidates(h,[('torch_fp32','cpu')],policy='reference')
        self.assertEqual(len(c),1);self.assertEqual(c[0]['query_batch_size'],1)
        with self.assertRaises(ValueError):candidates(h,[('torch_fp32','cpu'),('torch_fp32','cuda')],policy='reference')
    def test_backend_validates_before_optional_import(self):
        from thm.runtime.backends import LocalEncoder
        for batch in (False,0,257):
            with self.assertRaises(ValueError):LocalEncoder('missing','m',document_batch_size=batch)
        with self.assertRaises(ValueError):LocalEncoder('missing','m',threads=2)
    def test_temporal_adversarial_unrelated_recent_date(self):
        from thm.features import reorder,timestamp
        rows=[{'text':'unrelated material','timestamp':'2025-01-01'},{'text':'alpha launch','timestamp':'8 May, 2020'}]
        self.assertEqual(reorder(rows,'first alpha launch',RetrievalFeatures(temporal=True))[0]['text'],'alpha launch')
        self.assertEqual(timestamp('8 May, 2020').month,5);self.assertEqual(parse_query('before May 2024').dates,('2024-05-01',))


class ScoreDiagnosticsTests(unittest.TestCase):
    def test_measured_delta_and_unknown_are_separate(self):
        from research.runtime.diagnostics import score_deltas
        row={'scope':'s','question_index':0,'split':'held_out','mode':'dense','budget':600,'category':4,'budget_used':100,'selected_ids':['a'],
             'runtime_diagnostics':{'candidate_ids':['a','b'],'scores':[.51,.50]}}
        other=json.loads(json.dumps(row));other['selected_ids']=['b'];other['runtime_diagnostics']['scores']=[.49,.52]
        r=score_deltas({'rows':[row]},{'rows':[other]})
        self.assertEqual(r['mismatching_queries'],1);self.assertAlmostEqual(r['queries'][0]['scores'][0]['score_delta'],-.02)
        other.pop('runtime_diagnostics');r=score_deltas({'rows':[row]},{'rows':[other]})
        self.assertEqual(r['queries'][0]['status'],'missing-score-evidence')
        self.assertIsNone(r['queries'][0]['scores'][0]['score_delta'])

class RuntimeReviewRegressionTests(unittest.TestCase):
    setUp=RuntimeTests.setUp
    tearDown=RuntimeTests.tearDown
    profile=RuntimeTests.profile
    def test_scalar_scheduler_executes_selected_scorer(self):
        import numpy as np
        e=FakeEncoder();self.index.embed('s',e,e.model_id);p=self.profile(e,scorer='torch_cpu')
        def measured(d,q,name):
            self.assertEqual(name,'torch_cpu')
            return np.asarray(d,dtype=np.float32) @ np.asarray(q,dtype=np.float32).T,{'transfer':0.0,'dense_scoring':1.0}
        with patch('thm.runtime.scorers.score',side_effect=measured) as scorer:
            with RuntimeScheduler(self.index,[p],{e.profile.id:e}) as scheduler:
                result=scheduler.search('s','alpha',mode='hybrid',diagnostics=True)
                self.assertEqual(result['runtime_diagnostics']['scorer'],'torch_cpu');self.assertEqual(scorer.call_count,1)
    def test_reference_rejects_other_policy_and_stays_sequential(self):
        e=FakeEncoder();p=self.profile(e,query_batch_size=8)
        with self.assertRaises(ValueError):RuntimeScheduler(self.index,[p],{e.profile.id:e},policy='reference')
        from dataclasses import replace
        e.profile=replace(e.profile,backend='torch_fp32')
        self.index.embed('s',e,e.model_id);reference=self.profile(e,'reference')
        with RuntimeScheduler(self.index,[reference],{e.profile.id:e},policy='reference') as scheduler:
            with patch.object(self.index,'search_many',side_effect=AssertionError('reference must be scalar')):
                result=scheduler.search_many('s',['alpha','beta'],mode='hybrid')
            self.assertEqual(len(result),2)
    def test_batched_diagnostics_match_limited_candidates(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        result=self.index.search_many('s',['alpha','beta'],mode='dense',encoder=e,model_id=e.model_id,candidate_limit=2)
        for row in result:
            d=row['runtime_diagnostics'];self.assertEqual(len(d['candidate_ids']),2);self.assertEqual(len(d['scores']),2)
            self.assertEqual(d['candidate_ids'],row['ranked_ids'])
    def test_overlap_cannot_override_calibrated_profile(self):
        from thm.runtime.research import ExecutionConfig,Execution
        e=FakeEncoder();p=self.profile(e)
        path=self.root/'runtime.json';write_receipt(path,p.identity())
        config=ExecutionConfig(policy='auto-safe',backend=p.backend,overlap=True,runtime_profile_file=str(path))
        with patch('thm.runtime.isolated.IsolatedEncoder',side_effect=AssertionError('must reject before load')):
            with self.assertRaisesRegex(ValueError,'execution settings'):Execution(config,'local-model','test-only')
    def test_prepared_backend_status_checks_both_manifests(self):
        from thm.runtime.cli import main
        from thm.runtime.identity import digest
        import contextlib,io
        root=self.root/'derived';root.mkdir();(root/'model.onnx').write_bytes(b'local fixture')
        derived=manifest(root)['sha256'];source='a'*64
        prep={'backend':'onnxruntime_fp32','precision':'fp32','source_manifest_sha256':source,'derived_manifest_sha256':derived,
              'transformation':'test-export','model_file':'model.onnx','converter_versions':{'test':'1'}}
        write_receipt(root/'thm-preparation.json',prep)
        transform=digest({k:prep[k] for k in ('backend','precision','source_manifest_sha256','transformation','model_file','converter_versions')})
        e=EmbeddingProfile(source,'onnxruntime_fp32','1','fp32',8,transformation=transform,derived_manifest_sha256=derived)
        p=RuntimeProfile(e.id,fingerprint(probe(),source,derived,e.id),backend=e.backend,policy='auto-safe',semantic_gate='strict')
        profile=self.root/'tune.json';write_receipt(profile,{'runtime_profile':p.identity(),'trials':[{'result':{'identity':e.identity()}}]})
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=main(['status','--profile',str(profile),'--model-path',str(root)])
        self.assertEqual(code,0);self.assertEqual(json.loads(output.getvalue())['profile_freshness'],'fresh')
        (root/'model.onnx').write_bytes(b'changed')
        with contextlib.redirect_stderr(io.StringIO()):code=main(['status','--profile',str(profile),'--model-path',str(root)])
        self.assertEqual(code,1)

    def test_auto_safe_rejects_uncalibrated_features_before_execution(self):
        from thm.runtime.research import ExecutionConfig
        e=FakeEncoder();p=self.profile(e)
        with RuntimeScheduler(self.index,[p],{e.profile.id:e}) as scheduler:
            for kwargs in ({'features':{'temporal':True}},{'entity_projection':True}):
                with self.assertRaisesRegex(ValueError,'uncalibrated'):scheduler.search('s','alpha',**kwargs)
        with self.assertRaisesRegex(ValueError,'uncalibrated'):ExecutionConfig(policy='auto-safe',features=RetrievalFeatures(segment=True))
    def test_batch_candidate_mapping_reads_scope_once(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        with patch.object(self.index,'rows',wraps=self.index.rows) as rows:
            self.index.search_many('s',['alpha','beta','gamma'],mode='dense',encoder=e,model_id=e.model_id,query_batch_size=2)
        self.assertEqual(rows.call_count,1)
    def test_both_runner_summaries_include_amortized_batch_work(self):
        from research.recall.benchmark import run as locomo
        from research.recall.lme_retrieval import run as lme
        original=SearchIndex.search
        def timed(index,*args,**kwargs):
            out=original(index,*args,**kwargs);out['timing_ms']['total']=2.0;out['timing_ms']['amortized_total']=17.0
            out['timing_kind']='post-batch-search';out['batch_receipt']={'embedding_ms':30.0};return out
        datasets=[(locomo,[{'sample_id':'a','conversation':{'session_1':[{'dia_id':'D1:1','speaker':'Alice','text':'alpha'}]},'qa':[{'question':'alpha','category':4,'evidence':['D1:1']}]}]),
          (lme,[{'question_id':'a','question':'alpha','haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'alpha'}]],'answer_session_ids':['s']}])]
        with patch.object(SearchIndex,'search',timed):
            for runner,data in datasets:
                result=runner(data,TokenCounter(),['sparse'],[600]);row=result['rows'][0]
                self.assertEqual(row['total_ms'],17.0);self.assertEqual(row['timing_breakdown_ms']['total'],2.0)
                self.assertEqual(row['batch_receipt']['embedding_ms'],30.0)

    def test_preencoded_lme_query_cost_is_charged_once(self):
        from thm.runtime.research import ExecutionConfig,Execution
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        execution=Execution(ExecutionConfig(policy='auto-throughput'),None,e.model_id);execution.encoder=e
        execution.preencode(['alpha']);execution.precompute_costs['alpha']=12.0
        first=execution.search_many(self.index,'s',['alpha'],mode='dense')[0]
        second=execution.search_many(self.index,'s',['alpha'],mode='dense')[0]
        self.assertEqual(first['timing_ms']['amortized_total'],first['timing_ms']['total']+12.0)
        self.assertNotIn('query_preembedding_amortized',second['timing_ms']);execution.close()
    def test_batched_queries_encode_only_exact_profile_cache_misses(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id);e.calls.clear()
        args={'mode':'dense','encoder':e,'model_id':e.model_id,'query_batch_size':2}
        self.index.search_many('s',['alpha','alpha','beta'],**args)
        self.assertEqual(e.calls,[['alpha'],['beta']]);e.calls.clear()
        results=self.index.search_many('s',['beta','alpha'],**args)
        self.assertEqual(e.calls,[]);self.assertTrue(all(r['query_embedding_cache_hit'] for r in results))
        self.index.search_many('s',['alpha','gamma'],**args);self.assertEqual(e.calls,[['gamma']])
    def test_overlap_does_not_submit_cached_query_encoding(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        self.index.search('s','alpha',mode='hybrid',encoder=e,model_id=e.model_id);e.calls.clear()
        with patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('cached vector must not start worker')):
            out=self.index.search_overlap('s','alpha',mode='hybrid',encoder=e,model_id=e.model_id)
        self.assertEqual(e.calls,[]);self.assertIn(out['overlap']['skipped'],('query-vector-cache-hit','result-cache-hit'))
    def test_batched_preencoding_is_reused_and_cost_preserved(self):
        from thm.runtime.research import ExecutionConfig,Execution
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        execution=Execution(ExecutionConfig(policy='auto-throughput',query_batch_size=2),None,e.model_id);execution.encoder=e
        execution.preencode(['alpha','beta']);e.calls.clear();execution.precompute_costs={'alpha':12.,'beta':13.}
        rows=execution.search_many(self.index,'s',['alpha','beta'],mode='dense')
        self.assertEqual(e.calls,[])
        for row,cost in zip(rows,[12.,13.]):
            self.assertEqual(row['batch_receipt']['encoded_queries'],0)
            self.assertGreaterEqual(row['timing_ms']['amortized_total'],row['timing_ms']['total']+cost)
            self.assertEqual(row['batch_receipt']['query_preembedding_amortized_ms'],cost)
        execution.close()
    def test_interactive_measurement_includes_actual_scorer(self):
        from thm.runtime.worker import measure
        from thm.runtime.scorers import score
        clock=[0.0]
        def now():clock[0]+=.001;return clock[0]
        def slow_scorer(d,q,name):
            clock[0]+=.1;return score(d,q,'numpy_reference')
        config={'model_path':'test','model_id':'test-only','backend':'test-only','device':'cpu','threads':1,'document_batch_size':4,'query_batch_size':2,'scorer':'torch_cuda'}
        with patch('thm.runtime.worker.configure'),patch('thm.runtime.backends.create',return_value=FakeEncoder()),patch('thm.runtime.worker.time.perf_counter',side_effect=now),patch('thm.runtime.scorers.score',side_effect=slow_scorer),patch('thm.runtime.autotune.retrieval_signature',return_value=[]):
            result=measure(config)
        self.assertGreater(result['single_query_p95_ms'],100.)
        self.assertLess(result['single_query_embedding_p50_ms'],10.)
        self.assertEqual(result['single_query_metric'],'encoder-plus-selected-scorer-including-transfer')

    def test_preencoding_rejects_invalid_vectors_before_cache(self):
        from thm.runtime.research import ExecutionConfig,Execution
        for vectors in ([[float('nan')]*8],[[0.]*8],[[2.]*8],[[1.]],[]):
            e=FakeEncoder();execution=Execution(ExecutionConfig(policy='auto-throughput'),None,e.model_id);execution.encoder=e
            with patch.object(e,'encode_many',return_value=vectors):
                with self.assertRaises(ValueError):execution.preencode(['alpha'])
            self.assertEqual(execution.precomputed,{});self.assertEqual(execution.precompute_costs,{})
            execution.close()
    def test_isolated_wire_preserves_unicode_with_ascii_locale(self):
        from thm.runtime.isolated import IsolatedEncoder
        from types import SimpleNamespace
        import io,threading
        raw=io.BytesIO();stream=io.TextIOWrapper(raw,encoding='ascii')
        encoder=IsolatedEncoder.__new__(IsolatedEncoder);encoder.lock=threading.RLock()
        encoder.process=SimpleNamespace(poll=lambda:None,stdin=stream);encoder.worker_wall_ms=0;encoder.worker_cpu_ms=0
        encoder._receive=lambda:{'vectors':[[1.]]}
        texts=['中文查询','日本語 café 😀']
        self.assertEqual(encoder.encode_many(texts),[[1.]])
        self.assertEqual(json.loads(raw.getvalue().decode('ascii'))['texts'],texts);stream.close()

    def test_auto_safe_requires_profile_before_optional_encoder_start(self):
        from thm.runtime.research import ExecutionConfig,Execution
        with patch('thm.runtime.isolated.IsolatedEncoder',side_effect=AssertionError('must fail before startup')):
            for model in (None,'local-model'):
                with self.assertRaisesRegex(ValueError,'calibrated runtime profile'):Execution(ExecutionConfig(policy='auto-safe'),model,'test')
    def test_verification_requires_every_requested_calibration_winner(self):
        from research.runtime import verify
        from types import SimpleNamespace
        profile={'backend':'torch_fp32','device':'cpu','document_batch_size':64,'query_batch_size':1,'threads':1,'scorer':'numpy_reference'}
        def process(command,**kwargs):
            if command[:2]==['git','rev-parse']:return SimpleNamespace(stdout='a'*40,returncode=0)
            if command[:2]==['git','status']:return SimpleNamespace(stdout='',returncode=0)
            Path(command[command.index('--output')+1]).write_text(json.dumps({'rows':[],'builds':[],'summaries':{}}))
            return SimpleNamespace(returncode=0)
        cases=[({'auto-safe'},False),({'auto-throughput'},False),({'auto-safe','auto-throughput'},False),({'approximate-performance'},True),(set(),False)]
        for number,(failed,approximate) in enumerate(cases):
            args=SimpleNamespace(output_dir=str(self.root/('verify-'+str(number))),model_path='local',model_id='test',locomo_dataset='locomo',lme_dataset='lme',include_approximate=approximate,plan_only=False,retrieval_ab=False,max_candidates=2)
            def tune(*a,**kw):return {'status':'failed','reason':'no-candidate-passed'} if kw['policy'] in failed else {'status':'calibrated','runtime_profile':profile}
            with patch.object(verify,'load_dataset',return_value=[]),patch.object(verify,'manifest',return_value={'sha256':'a'*64}),patch.object(verify,'backend_probe',return_value=[]),patch.object(verify,'available',return_value={}),patch.object(verify,'census',return_value={}),patch.object(verify,'TokenCounter',return_value=TokenCounter()),patch.object(verify,'autotune',side_effect=tune),patch.object(verify.subprocess,'run',side_effect=process),patch('research.recall.hardware_parity.compare',return_value={'strict_semantic_equivalent':True,'aggregate_semantic_metrics_equivalent':True}):
                result=verify.execute(args)
            self.assertEqual(set(result['missing_required_winners']),failed)
            self.assertEqual(result['status'],'incomplete-local-run' if failed else 'measured-needs-acceptance')
            self.assertTrue(all(r['returncode']==0 for r in result['executions']))
            self.assertTrue((Path(args.output_dir)/'comparison.json').is_file())

    def test_conversion_ignores_existing_source_backend_variants(self):
        from thm.runtime.prepare import convert
        from types import SimpleNamespace
        source=self.root/'source-variants';source.mkdir()
        for name in ('model.onnx','optimized.onnx','openvino_model.xml','quantized.xml'):(source/name).write_bytes(b'old variant')
        before=manifest(source)['sha256'];seen=[]
        class Model:
            def __init__(model,path,**kwargs):
                self.assertNotEqual(Path(path),source);self.assertTrue((Path(path)/'optimized.onnx').is_file())
                self.assertTrue(kwargs['model_kwargs']['export']);model.family=kwargs['backend'];seen.append(path)
            def save_pretrained(model,path):
                root=Path(path);self.assertFalse(root.exists());target=root/model.family;target.mkdir(parents=True)
                (target/('model.onnx' if model.family=='onnx' else 'openvino_model.xml')).write_bytes(b'fresh conversion')
        ov=SimpleNamespace(Core=lambda:SimpleNamespace(read_model=lambda path:Path(path).read_bytes()),save_model=lambda model,path,**kw:Path(path).write_bytes(model))
        with patch.dict(sys.modules,{'sentence_transformers':SimpleNamespace(SentenceTransformer=Model),'openvino':ov}):
            for backend,family,file in [('onnxruntime_fp32','onnx','model.onnx'),('openvino_fp32','openvino','openvino_model.xml')]:
                out=self.root/backend;result=convert({'model_path':str(source),'staging':str(out),'backend':backend,'source_manifest_sha256':before})
                self.assertEqual(result['model_file'],family+'/'+file);self.assertEqual(result['status'],'prepared')
                self.assertFalse((out/'optimized.onnx').exists());self.assertEqual((out/family/file).read_bytes(),b'fresh conversion')
        self.assertEqual(manifest(source)['sha256'],before);self.assertTrue(all(not Path(path).exists() for path in seen))

    def test_reference_profile_rejects_non_torch_backend(self):
        for backend in ('onnxruntime_fp32','openvino_fp32','test-only'):
            with self.assertRaises(ValueError):RuntimeProfile('ep','fingerprint',backend=backend,policy='reference',semantic_gate='reference')
    def test_batch_latency_includes_ranking_and_row_overhead(self):
        import numpy as np
        e=FakeEncoder();self.index.embed('s',e,e.model_id);clock=[0.0];original=np.argsort
        def now():clock[0]+=.001;return clock[0]
        def rank(*a,**kw):clock[0]+=.1;return original(*a,**kw)
        with patch('thm.retrieval.time.perf_counter',side_effect=now),patch('numpy.argsort',side_effect=rank):
            rows=self.index.search_many('s',['alpha','beta'],mode='dense',encoder=e,model_id=e.model_id)
        for row in rows:
            timing=row['timing_ms'];self.assertGreaterEqual(timing['dense_ranking'],100.)
            self.assertGreaterEqual(timing['amortized_total'],timing['total']+timing['dense_ranking'])
    def test_segment_context_is_nonempty_without_complete_evidence_credit(self):
        from research.recall.benchmark import run as locomo
        from research.recall.lme_retrieval import run as lme
        from thm.runtime.research import ExecutionConfig
        config=ExecutionConfig(policy='auto-throughput',features=RetrievalFeatures(segment=True))
        datasets=[(locomo,[{'sample_id':'a','conversation':{'session_1':[{'dia_id':'D1:1','speaker':'Alice','text':'alpha launch details. '+'unrelated filler '*2000}]},'qa':[{'question':'alpha','category':4,'evidence':['D1:1']}]}]),
          (lme,[{'question_id':'a','question':'alpha','haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'alpha launch details. '+'unrelated filler '*2000}]],'answer_session_ids':['s']}])]
        for runner,data in datasets:
            result=runner(data,TokenCounter(),['sparse'],[600],execution_config=config);row=result['rows'][0]
            self.assertGreater(row['packed_selected_count'],0);self.assertEqual(row['complete_selected_count'],0)
            from research.recall.hardware_parity import strict_row_coverage_errors
            self.assertEqual(strict_row_coverage_errors(result),{})
            bad=json.loads(json.dumps(result));bad['rows'][0]['packed_selected_count']+=1
            self.assertIn('inconsistent:packed_selection_identity',strict_row_coverage_errors(bad))
            self.assertEqual(row['selected_count'],len(row['selected_ids']))
            self.assertEqual(row['packed_selected_count'],len(row['packed_selections']))
            from research.recall.benchmark import aggregate
            from research.recall.lme_retrieval import aggregate as summarize
            summary=aggregate([row]) if runner is locomo else summarize([row])
            self.assertEqual(summary['empty_context_rate'],0.0)
            self.assertEqual(row['hits'],0);self.assertTrue(row['parent_locator_ids'])

    def test_lexical_only_lme_does_not_preencode_questions(self):
        from research.recall.lme_retrieval import run
        from thm.runtime.research import ExecutionConfig,Execution
        data=[{'question_id':'a','question':'query only','haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'query source'}]],'answer_session_ids':['s']}]
        with patch('thm.runtime.isolated.IsolatedEncoder',return_value=FakeEncoder()),patch.object(Execution,'preencode',side_effect=AssertionError('lexical queries must not encode')):
            result=run(data,TokenCounter(),['literal','sparse'],[600],model_path='local',model_id='test-only',execution_config=ExecutionConfig(policy='auto-throughput'))
        self.assertEqual(result['runtime']['query_preembedding_ms'],0)
    def test_both_mcp_bridges_preserve_segment_identity(self):
        from thm.harness import HarnessConfig
        from thm.mcp_legacy_server import LegacyMCPServer,RECALL_OUTPUT_SCHEMA
        from types import SimpleNamespace
        import atexit
        text='alpha launch details. '+'unrelated filler '*2000
        self.index.replace_scope('s',[Document('parent','s','session',0,text,source='local')])
        config=HarnessConfig(db=str(self.root/'index.sqlite'),scope='s',budget=300,features=RetrievalFeatures(segment=True))
        legacy=LegacyMCPServer(config)
        try:old=legacy._call_tool('thm_recall',{'query':'alpha'})['structuredContent']
        finally:legacy.close()
        class Server:
            def __init__(server,*args):server.tools={}
            def tool(server):
                def register(fn):server.tools[fn.__name__]=fn;return fn
                return register
        from typing import TypedDict
        with patch.dict(sys.modules,{'mcp.server':SimpleNamespace(MCPServer=Server),'typing_extensions':SimpleNamespace(TypedDict=TypedDict)}):
            from thm.mcp_server import build_server
            server,adapter=build_server(config)
            try:new=server.tools['thm_recall']('alpha')
            finally:adapter.close();atexit.unregister(adapter.close)
        self.assertEqual(old['sources'],new['sources']);row=new['sources'][0]
        self.assertFalse(row['complete']);self.assertEqual(row['parent_id'],'parent');self.assertEqual(row['locator_kind'],'segment-v2')
        self.assertIn(text[row['span_start']:row['span_end']],new['context'])
        schema=RECALL_OUTPUT_SCHEMA['properties']['sources']['items']
        self.assertEqual(set(row),set(schema['required']))

    def test_scheduler_rejects_execution_settings_that_share_embedding_identity(self):
        e=FakeEncoder()
        for settings in ({'threads':2},{'document_batch_size':32},{'query_batch_size':8},{'affinity':(0,)}):
            p=self.profile(e,**settings)
            with self.assertRaisesRegex(ValueError,'execution settings mismatch'):RuntimeScheduler(self.index,[p],{e.profile.id:e})
        e.runtime_identity=None
        with self.assertRaisesRegex(ValueError,'identity unavailable'):RuntimeScheduler(self.index,[self.profile(e)],{e.profile.id:e})
    def test_query_iterables_are_consumed_only_to_the_overflow_sentinel(self):
        e=FakeEncoder();p=self.profile(e)
        def source():
            for i in range(4097):yield 'alpha'
            raise AssertionError('must not consume beyond bound')
        with self.assertRaises(ValueError):self.index.search_many('s',source())
        with RuntimeScheduler(self.index,[p],{e.profile.id:e}) as scheduler:
            with self.assertRaises(ValueError):scheduler.search_many('s',source())
    def test_zero_budget_batch_and_overlap_do_no_semantic_work(self):
        e=FakeEncoder('fails')
        with patch.object(self.index,'_dense_matrix',side_effect=AssertionError('no dense setup')):
            for mode in ('dense','hybrid'):
                rows=self.index.search_many('s',['alpha','beta'],mode=mode,budget=0)
                self.assertTrue(all(r['empty_reason']=='zero_budget' and not r['semantic_encoder_used'] for r in rows))
                row=self.index.search_overlap('s','alpha',mode=mode,budget=0,encoder=e,model_id=e.model_id)
                self.assertFalse(row['semantic_encoder_used'])
        self.assertEqual(e.calls,[])

    def test_batch_overlap_runs_fts_while_encoder_is_waiting(self):
        from thm.runtime.research import Execution,ExecutionConfig
        started=threading.Event();lexical=threading.Event();caller=threading.get_ident()
        class Encoder(FakeEncoder):
            blocking=False
            def __call__(encoder,texts):
                if encoder.blocking:
                    started.set()
                    if not lexical.wait(2):raise AssertionError('lexical work did not overlap encoding')
                return super().__call__(texts)
        e=Encoder();self.index.embed('s',e,e.model_id)
        reference=self.index.search_many('s',['alpha','beta'],mode='hybrid',encoder=e,model_id=e.model_id)
        self.index._cache.clear();e.blocking=True;original=self.index._lexical_channels
        def prepare(*args):
            self.assertEqual(threading.get_ident(),caller);self.assertTrue(started.wait(2));lexical.set();return original(*args)
        execution=Execution(ExecutionConfig(policy='auto-throughput',query_batch_size=2,overlap=True),None,e.model_id);execution.encoder=e
        with patch.object(self.index,'_lexical_channels',side_effect=prepare):rows=execution.search_many(self.index,'s',['alpha','beta'],mode='hybrid')
        self.assertEqual([r['ranked_ids'] for r in rows],[r['ranked_ids'] for r in reference])
        self.assertTrue(all(r['batch_receipt']['overlap_active'] for r in rows));self.assertIsNone(self.index._batch_lexical)
        with patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('cached batch must not encode')):
            cached=execution.search_many(self.index,'s',['alpha','beta'],mode='hybrid')
        self.assertTrue(all(not r['overlap']['active'] for r in cached));execution.close()
    def test_scheduler_passes_calibrated_overlap_to_batch_api(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id);p=self.profile(e,overlap=True)
        with RuntimeScheduler(self.index,[p],{e.profile.id:e}) as scheduler:
            with patch.object(self.index,'search_many',wraps=self.index.search_many) as call:
                rows=scheduler.search_many('s',['alpha','beta'],mode='hybrid')
            self.assertTrue(call.call_args.kwargs['overlap']);self.assertTrue(all(r['batch_receipt']['overlap_active'] for r in rows))

    def test_overlap_skips_cached_result_after_query_vector_eviction(self):
        e=FakeEncoder();self.index.embed('s',e,e.model_id)
        kwargs={'mode':'hybrid','encoder':e,'model_id':e.model_id}
        first=self.index.search('s','alpha',**kwargs)
        self.index.search_many('s',['distinct '+str(i) for i in range(256)],query_batch_size=256,**kwargs)
        self.assertNotIn((e.profile.id,'alpha'),self.index._cache);e.calls.clear()
        with patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('cached result must not encode')):
            result=self.index.search_overlap('s','alpha',**kwargs)
        self.assertTrue(result['result_cache_hit']);self.assertEqual(result['overlap']['skipped'],'result-cache-hit')
        self.assertEqual(result['selected'],first['selected']);self.assertEqual(e.calls,[])

    def test_strict_gate_rejects_score_drift_and_signature_truncation(self):
        from thm.runtime.autotune import retrieval_signature
        e=FakeEncoder();measured={'status':'ok','identity':e.identity(),'corpus_sha256':CORPUS_SHA,'document_vectors':e(DOCUMENTS),'query_vectors':e(QUERIES)}
        measured['retrieval_signature']=retrieval_signature(measured)
        candidate=json.loads(json.dumps(measured));candidate['retrieval_signature'][0]['scores'][0]+=.001
        result=gate(measured,candidate);self.assertFalse(result['admitted']);self.assertEqual(result['score_absolute_tolerance'],0.0)
        self.assertGreater(result['max_score_abs_diff'],0)
        candidate['retrieval_signature'].pop();self.assertEqual(gate(measured,candidate)['reason'],'invalid-signature-length')
    def test_lexical_runners_never_embed_documents(self):
        from research.recall.benchmark import run as locomo
        from research.recall.lme_retrieval import run as lme
        from thm.runtime.research import ExecutionConfig
        datasets=[(locomo,[{'sample_id':'a','conversation':{'session_1':[{'dia_id':'D1:1','speaker':'Alice','text':'alpha'}]},'qa':[{'question':'alpha','category':4,'evidence':['D1:1']}]}]),
          (lme,[{'question_id':'a','question':'alpha','haystack_session_ids':['s'],'haystack_sessions':[[{'role':'user','content':'alpha'}]],'answer_session_ids':['s']}])]
        for runner,data in datasets:
            e=FakeEncoder('fails')
            with patch('thm.runtime.isolated.IsolatedEncoder',return_value=e):
                result=runner(data,TokenCounter(),['literal','sparse'],[600],model_path='local',model_id=e.model_id,execution_config=ExecutionConfig(policy='auto-throughput'))
            self.assertEqual(e.calls,[]);self.assertTrue(all('embedding' not in b for b in result['builds']))
    def test_invalid_batch_and_overlap_options_fail_before_semantic_work(self):
        e=FakeEncoder('fails')
        for options in ({'budget':-1},{'neighbor_turns':3},{'features':{'segment':'yes'}},{'diagnostics':1},{'candidate_limit':0}):
            with patch.object(self.index,'_dense_matrix',side_effect=AssertionError('validation must precede matrix load')),patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('validation must precede worker')):
                with self.assertRaises(ValueError):self.index.search_many('s',['alpha'],mode='hybrid',encoder=e,model_id=e.model_id,overlap=True,**options)
                with self.assertRaises(ValueError):self.index.search_overlap('s','alpha',mode='hybrid',encoder=e,model_id=e.model_id,**options)
        self.assertEqual(e.calls,[])

    def test_score_deltas_retains_numeric_drift_with_identical_selection(self):
        from research.runtime.diagnostics import score_deltas
        row={'conversation_id':'a','qa_index':0,'mode':'hybrid','budget':600,'selected_ids':['a'],'selected_ranked_ids':['a'],'budget_used':5,
             'runtime_diagnostics':{'candidate_ids':['a','b'],'scores':[.51,.50]}}
        other=json.loads(json.dumps(row));other['runtime_diagnostics']['scores']=[.52,.49]
        report=score_deltas({'rows':[row]},{'rows':[other]})
        self.assertEqual(report['mismatching_queries'],1)
        self.assertAlmostEqual(report['queries'][0]['scores'][0]['score_delta'],.01)
        self.assertEqual(report['queries'][0]['reference_selected'],report['queries'][0]['candidate_selected'])
        self.assertEqual(score_deltas({'rows':[row]},{'rows':[row]})['mismatching_queries'],0)
        other['runtime_diagnostics']['candidate_ids']=['b','a'];other['runtime_diagnostics']['scores']=[.50,.51]
        aligned=score_deltas({'rows':[row]},{'rows':[other]})
        self.assertEqual([entry['score_delta'] for entry in aligned['queries'][0]['scores']],[0,0])
