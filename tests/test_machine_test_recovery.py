from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BRIDGE = load_module("thm_ce_bridge_test", "research/economics/thm_ce_bridge.py")
PARITY = load_module("hardware_parity_test", "research/recall/hardware_parity.py")
RUN_SUITE = load_module("run_suite_test", "research/economics/run_suite.py")


class FakePricing:
    p_in = 0.66
    p_cache = 0.022

    def effective_input_rate(self, rho, prompt_tokens=0.0):
        return (1.0 - rho) * self.p_in + rho * self.p_cache


def row(scope, budget, used, hits, *, resolved=True, q=0):
    return {
        "scope": scope,
        "question_index": q,
        "split": "held_out",
        "mode": "hybrid",
        "budget": budget,
        "category": 4,
        "evidence_count": 1,
        "resolved_count": 1 if resolved else 0,
        "fully_resolved": resolved,
        "hits": hits,
        "candidate_hits": hits,
        "selected_count": 1,
        "selected_ids": [f"{scope}:{q}"],
        "selected_ranked_ids": [f"{scope}:{q}"],
        "reciprocal_rank": 1.0 if hits else 0.0,
        "candidate_reciprocal_rank": 1.0 if hits else 0.0,
        "ndcg": 1.0 if hits else 0.0,
        "budget_used": used,
        "malformed_evidence": False,
    }


class EconomicsBridgeTests(unittest.TestCase):
    def test_load_pricing_class_supports_dataclass_module(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "model.py").write_text(
                "from dataclasses import dataclass\n"
                "@dataclass(frozen=True)\n"
                "class Pricing:\n"
                "    name: str\n"
                "    p_in: float\n"
                "    p_cache: float\n"
                "    p_out: float\n"
                "    def effective_input_rate(self, rho, prompt_tokens=0.0):\n"
                "        return (1-rho)*self.p_in + rho*self.p_cache\n",
                encoding="utf-8",
            )
            pricing_cls, provenance = BRIDGE.load_pricing_class(root)
            pricing = pricing_cls("x", 1.0, 0.1, 2.0)
            self.assertEqual(pricing.effective_input_rate(0.5), 0.55)
            self.assertEqual(len(provenance["model_sha256"]), 64)

    def test_counterfactual_dataset_must_match_benchmark_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "locomo.json"
            raw = json.dumps([{"sample_id": "s"}]).encode("utf-8")
            path.write_bytes(raw)
            expected = hashlib.sha256(raw).hexdigest()
            data, digest = BRIDGE.load_dataset_verified(path, expected)
            self.assertEqual(data, [{"sample_id": "s"}])
            self.assertEqual(digest, expected)
            path.write_text('[{"sample_id":"s","changed":true}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                BRIDGE.load_dataset_verified(path, expected)

    def test_same_query_counterfactual_uses_row_weighted_scopes(self):
        rows = [
            row("a", 600, 500, 1, q=1),
            row("b", 600, 600, 0, q=2),
            row("a", 600, 550, 0, resolved=False, q=3),
        ]
        result = BRIDGE.economics_for_rows(
            rows, FakePricing(), {"a": 10_000, "b": 20_000}
        )
        self.assertEqual(result["attempted_questions"], 3)
        self.assertEqual(result["scorable_questions"], 2)
        arm = result["full_history_same_query_counterfactual"]
        self.assertEqual(arm["attempted_questions"], 3)
        self.assertEqual(arm["total_input_tokens"], 40_000)
        self.assertEqual(arm["mean_input_tokens_per_query"], 13_333.33)
        rho0 = arm["pricing_scenarios"]["rho=0.0"]
        self.assertEqual(rho0["total_input_cost_usd_same_queries"], 0.0264)
        self.assertNotIn("total_cost_usd_1986_queries", rho0)

    def test_marginal_cost_is_explicitly_per_percentage_point(self):
        lo = [
            row("a", 300, 300, 1, q=1),
            row("b", 300, 300, 0, q=2),
        ]
        hi = [
            row("a", 600, 600, 1, q=1),
            row("b", 600, 600, 1, q=2),
        ]
        result = BRIDGE.marginal_analysis(
            {"hybrid": {300: lo, 600: hi}}, FakePricing()
        )["hybrid"]["300->600"]
        self.assertEqual(result["delta_any_gold_percentage_points"], 50.0)
        self.assertEqual(result["delta_input_cost_usd_rho0"], 0.000396)
        self.assertEqual(
            result["marginal_cost_usd_per_1pp_any_gold_gain"], 0.000008
        )

    def test_suite_totals_count_config_query_executions_not_dataset_questions(self):
        rows = []
        for budget in (300, 600):
            rows += [
                row("a", budget, budget, 1, q=1),
                row("b", budget, budget, 0, q=2),
            ]
        bench = {
            "protocol": 2,
            "counter": "cl100k_base",
            "modes": ["hybrid"],
            "budgets": [300, 600],
            "rows": rows,
            "summaries": {},
            "generation_calls": 0,
            "judge_calls": 0,
        }
        scenarios = {"deepseek-v4-pro_offpeak_2026-08-16": FakePricing()}
        report = BRIDGE.build_report(
            bench, scenarios, {"model_sha256": "x"}, {"a": 10_000, "b": 20_000}
        )
        self.assertEqual(report["suite_totals"]["config_count"], 2)
        self.assertEqual(report["suite_totals"]["config_query_executions"], 4)
        self.assertEqual(report["suite_totals"]["attempted_questions_per_config"], 2)


class SuiteReceiptTests(unittest.TestCase):
    def test_default_tags_cannot_target_historical_untagged_artifacts(self):
        self.assertEqual(RUN_SUITE.normalize_tag(None, "cpu"), "-cpu-v2")
        self.assertEqual(RUN_SUITE.normalize_tag(None, "cuda"), "-gpu-v2")
        with self.assertRaises(ValueError):
            RUN_SUITE.normalize_tag("", "cpu")

    def test_redaction_removes_personal_roots(self):
        text = RUN_SUITE.redact_text(
            r"C:\Users\alice\repo\context-economics\model.py",
            [(r"C:\Users\alice\repo\context-economics", "<CE_ROOT>")],
        )
        self.assertEqual(text, r"<CE_ROOT>\model.py")
        self.assertNotIn("alice", text)

    def test_existing_artifact_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                RUN_SUITE.require_new(path)


class HardwareParityTests(unittest.TestCase):
    def artifact(self, selected):
        return {
            "protocol": 2,
            "counter": "cl100k_base",
            "modes": ["hybrid"],
            "budgets": [600],
            "model_id": "m",
            "dataset_sha256": "abc",
            "corpus_fingerprints": {"a": "g"},
            "rows": [
                {
                    **row("a", 600, 580, 1, q=1),
                    "selected_ids": [selected],
                    "selected_ranked_ids": [selected],
                    "total_ms": 50.0,
                    "query_embedding_ms": 20.0,
                }
            ],
        }

    def test_timing_differences_do_not_break_semantic_parity(self):
        cpu = self.artifact("D1:1")
        gpu = self.artifact("D1:1")
        gpu["rows"][0]["total_ms"] = 5.0
        gpu["rows"][0]["query_embedding_ms"] = 0.1
        result = PARITY.compare(cpu, gpu)
        self.assertTrue(result["identity_complete"])
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["max_semantic_numeric_abs_diff"], 0.0)

    def test_retrieval_difference_breaks_parity(self):
        result = PARITY.compare(self.artifact("D1:1"), self.artifact("D1:2"))
        self.assertFalse(result["equivalent"])
        self.assertTrue(any(x["kind"] == "row_field" for x in result["mismatches"]))

    def test_legacy_aggregate_only_rows_are_insufficient_for_positive_parity(self):
        cpu = self.artifact("D1:1")
        gpu = self.artifact("D1:1")
        cpu["rows"][0].pop("selected_ids")
        gpu["rows"][0].pop("selected_ids")
        result = PARITY.compare(cpu, gpu)
        self.assertFalse(result["identity_complete"])
        self.assertFalse(result["equivalent"])
        self.assertTrue(any(
            x["kind"] == "selection_identity_unavailable"
            for x in result["mismatches"]
        ))


if __name__ == "__main__":
    unittest.main()
