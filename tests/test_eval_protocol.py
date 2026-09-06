import importlib.util
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('recall_benchmark',Path(__file__).resolve().parents[1]/'research/recall/benchmark.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
from thm.answer_eval import exact_f1, local_answer
from thm.retrieval import Document, SearchIndex


class EvaluationTests(unittest.TestCase):
    def test_evidence_list_semicolon_combination(self):
        refs,bad=bench.evidence_ids(['D1:3; D2:7','D1:3'])
        self.assertEqual(refs,{'D1:3','D2:7'});self.assertEqual(bad,[])

    def test_evidence_range_not_silently_guessed(self):
        self.assertTrue(bench.evidence_ids(['D1:3-5'])[1])

    def test_any_and_all_distinguished(self):
        row={'evidence_count':2,'fully_resolved':True,'hits':1,'candidate_hits':2,
             'selected_count':1,'budget_used':80,'total_ms':2,'query_embedding_ms':0}
        out=bench.aggregate([row]);self.assertEqual(out['any_gold_hit_rate'],1)
        self.assertEqual(out['all_gold_hit_rate'],0);self.assertEqual(out['macro_evidence_recall'],.5)

    def test_partial_gold_excluded_from_main_denominator(self):
        row={'evidence_count':2,'fully_resolved':False,'hits':1,'candidate_hits':1,
             'selected_count':1,'budget_used':80,'total_ms':2,'query_embedding_ms':0}
        self.assertEqual(bench.aggregate([row])['scorable'],0)

    def test_no_gold_not_counted_as_success(self):
        row={'evidence_count':0,'fully_resolved':True,'hits':0,'candidate_hits':0,
             'selected_count':0,'budget_used':0,'total_ms':2,'query_embedding_ms':0}
        self.assertIsNone(bench.aggregate([row])['any_gold_hit_rate'])

    def test_exact_metric_not_an_llm_judge(self):
        self.assertEqual(exact_f1('port 123','port 123')['token_f1'],1)
        self.assertFalse(exact_f1('port 123','port 456')['exact'])

    def test_remote_model_refused_without_network(self):
        for endpoint in ['https://example.org/v1/chat/completions','http://localhost:1234/chat','http://127.0.0.1@remote.example/chat']:
            with self.assertRaises(ValueError):local_answer(endpoint,'test','q','context')

    def test_provider_current_query_scope_and_status(self):
        # Contract test double only; live Hermes is a separate integration verification.
        module=types.ModuleType('agent.memory_provider')
        module.MemoryProvider=object
        module.RecallStatus=lambda **kwargs:kwargs
        with patch.dict(sys.modules,{'agent.memory_provider':module}):
            path=Path(__file__).resolve().parents[1]/'thm/hermes_plugin.py'
            s=importlib.util.spec_from_file_location('thm._adapter_test',path)
            provider_module=importlib.util.module_from_spec(s);s.loader.exec_module(provider_module)
            with tempfile.TemporaryDirectory() as root:
                db=Path(root)/'memories/.thm/recall.sqlite3'
                ix=SearchIndex(db);ix.replace_scope('scope',[Document('a','scope','s',0,'Storage port is 9123.')]);ix.close()
                provider=provider_module.THMProvider({'scope':'scope'})
                provider.initialize('session',hermes_home=root)
                self.assertIn('9123',provider.prefetch('storage port',session_id='session'))
                self.assertEqual(provider.recall_status()['count'],1)
                self.assertEqual(provider.prefetch('storage port',session_id='wrong'),'')
                self.assertIsNone(provider.recall_status())
                provider.on_session_switch('other')
                self.assertIn('9123',provider.prefetch('storage port',session_id='other'))
                provider.on_memory_write('add','memory','something')
                self.assertIsNone(provider.recall_status())
                provider.shutdown()


if __name__=='__main__': unittest.main()
