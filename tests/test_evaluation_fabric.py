import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from thm.evaluation.adapters import ADAPTERS
from thm.evaluation.contracts import GroundTruth, Receipt, Result, Taxonomy, digest
from thm.evaluation.fixtures import FIXTURES
from thm.evaluation.metrics import summarize
from thm.evaluation.memory import AgentMemory, V2Memory
from thm.evaluation.runner import run


class FabricTests(unittest.TestCase):
    def test_all_native_fixtures_retrieve_without_gold_leak(self):
        for name, adapter in ADAPTERS.items():
            source = copy.deepcopy(FIXTURES[name])
            tasks = list(adapter.tasks(source))
            for task, gold in tasks:
                self.assertEqual(task.id, gold.task_id)
                self.assertFalse(any('ideal_answer' in d.text or 'rubric' in d.text for d in task.documents))
            with tempfile.TemporaryDirectory() as temp:
                receipt = run(adapter, source, Path(temp)/'run', provenance='deterministic-fixture')
            self.assertFalse(receipt['full_dataset_acceptance'])
            self.assertEqual(receipt['layers']['LLM-agent-outcome']['status'], 'not-run')
            if name in ('beam', 'memoryarena', 'longmemeval-v2'):
                self.assertIsNone(receipt['layers']['memory-dataplane']['metrics']['any_gold_hit_rate'])
            else:
                self.assertEqual(receipt['layers']['memory-dataplane']['metrics']['any_gold_hit_rate'], 1)

    def test_answers_and_rubrics_never_enter_index(self):
        for name in ADAPTERS:
            source = copy.deepcopy(FIXTURES[name])
            def poison(value):
                if isinstance(value, dict):
                    for k in value:
                        if k in ('answer', 'answers', 'ideal_answer', 'ideal_response', 'rubric'):
                            value[k] = ['GOLD_LEAK_SENTINEL'] if isinstance(value[k], list) else 'GOLD_LEAK_SENTINEL'
                        else:
                            poison(value[k])
                elif isinstance(value, list):
                    for v in value:
                        poison(v)
            # Keep native aligned answer count for MemoryArena.
            if name == 'memoryarena':
                source[0]['answers'] = ['GOLD_LEAK_SENTINEL'] * 2
            else:
                poison(source)
            for task, _ in ADAPTERS[name].tasks(source):
                self.assertNotIn('GOLD_LEAK_SENTINEL', '\n'.join(d.text for d in task.documents))

    def test_partial_and_no_gold_and_diagnostic_denominators(self):
        def row(gold):
            return Result('q', gold, ('a',), ('a',), ('a', 'b'), 10, 1, 1).public()
        rows = [row(GroundTruth('q', ('a','b'))), row(GroundTruth('q')),
                row(GroundTruth('q', ('a','missing'), resolved=False)),
                row(GroundTruth('q', ('a',), diagnostic_only=True))]
        metrics = summarize(rows)
        self.assertEqual(metrics['scorable'], 1)
        self.assertEqual(metrics['macro_evidence_recall'], .5)
        self.assertEqual(metrics['all_gold_hit_rate'], 0)
        self.assertEqual(metrics['parent_locator_coverage'], 1)

    def test_unaligned_lme_and_arena_fail(self):
        for name, field in [('longmemeval-s','haystack_session_ids'), ('memoryarena','answers')]:
            source = copy.deepcopy(FIXTURES[name]); source[0][field] = []
            with self.assertRaises(ValueError):
                list(ADAPTERS[name].tasks(source))

    def test_taxonomy_is_cartesian_not_hardware_to_tier(self):
        for tier in ('T0','T1','T2','T3'):
            for compute in ('cpu','cuda'):
                for storage in ('nvme','sata','unknown'):
                    self.assertEqual(asdict(Taxonomy(tier, compute, storage))['logical_tier'], tier)

    def test_v2_native_and_memoryarena_cross_session_interfaces(self):
        with tempfile.TemporaryDirectory() as temp:
            v2 = V2Memory(Path(temp)/'v2.db', 'v2')
            arena = AgentMemory(Path(temp)/'arena.db', 'arena')
            try:
                trajectory = FIXTURES['longmemeval-v2'][0]['trajectories'][0]
                v2.insert(trajectory); v2.insert(trajectory)
                self.assertEqual(len(v2.documents), 1)
                self.assertIn('cobalt', v2.query('observatory')[0]['value'])
                with self.assertRaises(ValueError):
                    v2.query('observatory', 'image.png')
                arena.add('observatory access code cobalt')
                self.assertIn('cobalt', arena.wrap_user_prompt('observatory access code'))
            finally:
                v2.close(); arena.close()

    def test_full_campaign_and_output_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            for kwargs in ({'mode':'full-research'}, {'full_research':True}):
                with self.assertRaises(ValueError):
                    run(ADAPTERS['locomo'], FIXTURES['locomo'], Path(temp)/'x', **kwargs)
            out = Path(temp)/'run'
            run(ADAPTERS['locomo'], FIXTURES['locomo'], out)
            with self.assertRaises(FileExistsError):
                run(ADAPTERS['locomo'], FIXTURES['locomo'], out)

    def test_cli_rejects_full_without_opt_in_and_long_acceptance(self):
        for flags in (['--mode','full-research'], ['--wall-seconds','3601']):
            result = subprocess.run([sys.executable,'-m','thm.evaluation','--output','unused',*flags], capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_smoke_is_explicitly_truncated(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = run(ADAPTERS['locomo'], FIXTURES['locomo'], Path(temp)/'run', mode='smoke')
        self.assertTrue(receipt['coverage']['truncated'])
        self.assertEqual(receipt['coverage']['executed_tasks'],2)
        sha = receipt.pop('receipt_sha256')
        self.assertEqual(sha,digest(receipt))

    def test_outcome_import_requires_exact_trace_and_nonfixture_source(self):
        import hashlib
        from thm.evaluation.outcomes import AgentOutcome, attach_outcomes
        with tempfile.TemporaryDirectory() as temp:
            receipt = run(ADAPTERS['longmemeval-s'], FIXTURES['longmemeval-s'], Path(temp)/'run')
        trace = b'original evaluator trace'
        outcome = AgentOutcome('fixture-lme', 'reader-1', 'judge-1', hashlib.sha256(trace).hexdigest(), 1, 1, .5)
        imported = attach_outcomes(receipt, [outcome], trace_bytes=trace)
        self.assertEqual(imported['layers']['LLM-agent-outcome']['generation_calls'], 1)
        self.assertFalse(imported['full_dataset_acceptance'])
        with self.assertRaises(ValueError):
            attach_outcomes(receipt, [outcome], trace_bytes=b'changed')
        with self.assertRaises(ValueError):
            attach_outcomes(receipt, [outcome, outcome], trace_bytes=trace)
        receipt['provenance'] = 'deterministic-fixture'
        receipt.pop('receipt_sha256')
        receipt['receipt_sha256'] = digest(receipt)
        with self.assertRaises(ValueError):
            attach_outcomes(receipt, [outcome], trace_bytes=trace)
