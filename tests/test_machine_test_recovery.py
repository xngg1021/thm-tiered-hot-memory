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
REPORT_MD = load_module("report_md_test", "research/economics/report_md.py")


class FakePricing:
    p_in = 0.66
    p_cache = 0.022
    def effective_input_rate(self, rho, prompt_tokens=0.0):
        return (1.0-rho)*self.p_in + rho*self.p_cache


def row(scope, budget, used, hits, *, resolved=True, q=0):
    return {"scope": scope, "question_index": q, "split": "held_out", "mode": "hybrid", "budget": budget,
            "category": 4, "evidence_count": 1, "resolved_count": 1 if resolved else 0,
            "fully_resolved": resolved, "hits": hits, "candidate_hits": hits, "selected_count": 1,
            "selected_ids": [f"{scope}:{q}"], "selected_ranked_ids": [f"{scope}:{q}"],
            "reciprocal_rank": 1.0 if hits else 0.0, "candidate_reciprocal_rank": 1.0 if hits else 0.0,
            "ndcg": 1.0 if hits else 0.0, "budget_used": used, "malformed_evidence": False}


class EconomicsBridgeTests(unittest.TestCase):
    def test_load_pricing_class_supports_dataclass_module(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/"model.py").write_text("from dataclasses import dataclass\n@dataclass(frozen=True)\nclass Pricing:\n    name: str\n    p_in: float\n    p_cache: float\n    p_out: float\n    def effective_input_rate(self, rho, prompt_tokens=0.0):\n        return (1-rho)*self.p_in + rho*self.p_cache\n", encoding="utf-8")
            cls, provenance=BRIDGE.load_pricing_class(root); pricing=cls("x",1.0,0.1,2.0)
            self.assertEqual(pricing.effective_input_rate(.5),.55); self.assertEqual(len(provenance["model_sha256"]),64)

    def test_counterfactual_dataset_must_match_benchmark_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"locomo.json"; raw=json.dumps([{"sample_id":"s"}]).encode(); path.write_bytes(raw)
            expected=hashlib.sha256(raw).hexdigest(); data,digest=BRIDGE.load_dataset_verified(path,expected)
            self.assertEqual(data,[{"sample_id":"s"}]); self.assertEqual(digest,expected)
            path.write_text('[{"sample_id":"s","changed":true}]',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"does not match"): BRIDGE.load_dataset_verified(path,expected)

    def test_same_query_counterfactual_uses_row_weighted_scopes(self):
        rows=[row("a",600,500,1,q=1),row("b",600,600,0,q=2),row("a",600,550,0,resolved=False,q=3)]
        result=BRIDGE.economics_for_rows(rows,FakePricing(),{"a":10000,"b":20000}); arm=result["full_history_same_query_counterfactual"]
        self.assertEqual(result["attempted_questions"],3); self.assertEqual(result["scorable_questions"],2)
        self.assertEqual(arm["total_input_tokens"],40000); self.assertEqual(arm["mean_input_tokens_per_query"],13333.33)
        self.assertEqual(arm["pricing_scenarios"]["rho=0.0"]["total_input_cost_usd_same_queries"],0.0264)

    def test_marginal_cost_is_explicitly_per_percentage_point(self):
        lo=[row("a",300,300,1,q=1),row("b",300,300,0,q=2)]; hi=[row("a",600,600,1,q=1),row("b",600,600,1,q=2)]
        r=BRIDGE.marginal_analysis({"hybrid":{300:lo,600:hi}},FakePricing())["hybrid"]["300->600"]
        self.assertEqual(r["delta_any_gold_percentage_points"],50.0); self.assertEqual(r["marginal_cost_usd_per_1pp_any_gold_gain"],0.000008)

    def test_suite_totals_count_config_query_executions_not_dataset_questions(self):
        rows=[]
        for budget in (300,600): rows += [row("a",budget,budget,1,q=1),row("b",budget,budget,0,q=2)]
        bench={"protocol":2,"counter":"cl100k_base","modes":["hybrid"],"budgets":[300,600],"rows":rows,"summaries":{f"hybrid@{b}": {"main_categories_1_to_4": {"questions":2,"scorable":2}} for b in (300,600)},"generation_calls":0,"judge_calls":0}
        report=BRIDGE.build_report(bench,{"deepseek-v4-pro_offpeak_2026-08-16":FakePricing()},{"model_sha256":"x"},{"a":10000,"b":20000},source_artifact_sha256="c"*64)
        self.assertEqual(report["suite_totals"]["config_count"],2); self.assertEqual(report["suite_totals"]["config_query_executions"],4)
        self.assertEqual(report["benchmark"]["source_artifact_sha256"],"c"*64)

    def test_interpretation_limits_follow_grid_and_counterfactual_presence(self):
        custom=" ".join(BRIDGE.interpretation_limits_for_bench({"budgets":[100,250]},has_full_history=False))
        self.assertIn("[100, 250]",custom); self.assertNotIn("600-token",custom); self.assertIn("No full-history",custom)
        canonical=" ".join(BRIDGE.interpretation_limits_for_bench({"budgets":[300,600,1200]},has_full_history=True))
        self.assertIn("knee candidate",canonical); self.assertIn("same benchmark queries",canonical)


class SuiteReceiptTests(unittest.TestCase):
    def test_default_tags_cannot_target_historical_untagged_artifacts(self):
        self.assertEqual(RUN_SUITE.normalize_tag(None,"cpu"),"-cpu-v2"); self.assertEqual(RUN_SUITE.normalize_tag(None,"cuda"),"-gpu-v2")
        with self.assertRaises(ValueError): RUN_SUITE.normalize_tag("","cpu")
    def test_redaction_removes_personal_roots(self):
        text=RUN_SUITE.redact_text(r"C:\Users\alice\repo\context-economics\model.py",[(r"C:\Users\alice\repo\context-economics","<CE_ROOT>")]); self.assertNotIn("alice",text)
    def test_existing_artifact_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"artifact.json"; path.write_text("{}")
            with self.assertRaises(FileExistsError): RUN_SUITE.require_new(path)
    def test_suite_tag_is_atomically_consumed_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"suite-cpu-v2.json"; RUN_SUITE.reserve_suite_receipt(path,"-cpu-v2",["locomo.json","suite.json"])
            self.assertEqual(json.loads(path.read_text())["status"],"reserved")
            with self.assertRaisesRegex(FileExistsError,"already reserved or completed"): RUN_SUITE.reserve_suite_receipt(path,"-cpu-v2",["x"])


class ReportClaimTests(unittest.TestCase):
    @staticmethod
    def locomo(*,budgets=(300,600,1200),rate600=.7134):
        summaries={}
        for budget in budgets:
            rate=rate600 if budget==600 else (.8087 if budget==1200 else .5894)
            summaries[f"hybrid@{budget}"]={"main_categories_1_to_4":{"questions":1540,"scorable":1532,"any_gold_hit_rate":rate}}
        return {"protocol":2,"counter":"cl100k_base","dataset_sha256":"a"*64,"dataset_matches_pinned_reference":True,
                "modes":["hybrid"],"budgets":list(budgets),"generation_calls":0,"judge_calls":0,"summaries":summaries}
    @classmethod
    def econ_for(cls,locomo,digest="c"*64):
        return {"per_config": {k: {"attempted_questions":1540,"scorable_questions":1532} for k in locomo["summaries"]}, "suite_totals": {"config_count":len(locomo["summaries"]), "config_query_executions":1540*len(locomo["summaries"]), "scorable_config_query_executions":1532*len(locomo["summaries"]), "attempted_questions_per_config":1540,"scorable_questions_per_config":1532}, "kind":"thm-x-context-economics-bridge-v2","benchmark":{"source_artifact_sha256":digest,**{f:locomo.get(f) for f in ("dataset_sha256","protocol","counter","modes","budgets","generation_calls","judge_calls")}}}

    def test_numerical_match_is_not_called_full_reproduction(self):
        claim=REPORT_MD.locomo_observation(self.locomo()); self.assertIn("数值上与仓库固定 reference 71.34% 相同",claim); self.assertIn("不单独构成完整协议复现证明",claim)
    def test_missing_hybrid_600_does_not_emit_reference_value(self):
        claim=REPORT_MD.locomo_observation(self.locomo(budgets=(300,900))); self.assertNotIn("71.34%",claim)
    def test_report_rejects_mismatched_bridge_benchmark_identity_and_source_digest(self):
        loc=self.locomo(); econ=self.econ_for(loc); REPORT_MD.validate_locomo_bridge_pair(loc,econ,"c"*64)
        bad=json.loads(json.dumps(econ)); bad["benchmark"]["budgets"]=[300,600]
        with self.assertRaisesRegex(ValueError,"does not match"): REPORT_MD.validate_locomo_bridge_pair(loc,bad,"c"*64)
        with self.assertRaisesRegex(ValueError,"bytes do not match"): REPORT_MD.validate_locomo_bridge_pair(loc,econ,"d"*64)
    def test_report_rejects_counterfactual_hash_mismatch(self):
        loc=self.locomo(); econ=self.econ_for(loc); econ["benchmark"]["counterfactual_dataset_sha256"]="b"*64; econ["benchmark"]["counterfactual_dataset_matches_benchmark"]=False
        with self.assertRaises(ValueError): REPORT_MD.validate_locomo_bridge_pair(loc,econ,"c"*64)
    def test_full_history_claim_requires_every_config_arm(self):
        self.assertFalse(REPORT_MD.has_full_history_counterfactual({"per_config":{"hybrid@600":{"pricing_scenarios":{}}}}))
        self.assertTrue(REPORT_MD.has_full_history_counterfactual({"per_config":{"hybrid@600":{"full_history_same_query_counterfactual":{}}}}))
    def test_lme_input_is_opt_in(self):
        self.assertIsNone(REPORT_MD.load_optional_lme(None))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"lme.json"; path.write_text('{"benchmark":"lme"}',encoding="utf-8")
            self.assertEqual(REPORT_MD.load_optional_lme(str(path))["benchmark"],"lme")
        with self.assertRaises(FileNotFoundError): REPORT_MD.load_optional_lme("definitely-missing-lme.json")
    def test_knee_claim_is_derived_from_actual_adjacent_grid(self):
        supported={"l6_budget_grid_sensitivity":{"hybrid":{"300->600":{"delta_any_gold_percentage_points":10.0,"marginal_cost_usd_per_1pp_any_gold_gain":1.0},"600->1200":{"delta_any_gold_percentage_points":5.0,"marginal_cost_usd_per_1pp_any_gold_gain":2.5}}}}
        self.assertIn("knee candidate",REPORT_MD.knee_observation(supported))
        self.assertIn("不作 600-token knee claim",REPORT_MD.knee_observation({"l6_budget_grid_sensitivity":{"hybrid":{}}}))
    def test_l6_table_enumerates_actual_artifact_intervals(self):
        rows=REPORT_MD.l6_rows({"l6_budget_grid_sensitivity":{"sparse":{"100->250":{"delta_any_gold_percentage_points":3.25,"marginal_cost_usd_per_1pp_any_gold_gain":.125}}}}); self.assertIn("100->250",rows[0])


class HardwareParityTests(unittest.TestCase):
    def artifact(self,selected):
        return {"protocol":2,"counter":"cl100k_base","modes":["hybrid"],"budgets":[600],"model_id":"m","dataset_sha256":"abc","corpus_fingerprints":{"a":"g"},"rows":[{**row("a",600,580,1,q=1),"selected_ids":[selected],"selected_ranked_ids":[selected],"total_ms":50.0,"query_embedding_ms":20.0}]}
    def test_timing_differences_do_not_break_semantic_parity(self):
        cpu=self.artifact("D1:1"); gpu=self.artifact("D1:1"); gpu["rows"][0]["total_ms"]=5.0; self.assertTrue(PARITY.compare(cpu,gpu)["equivalent"])
    def test_retrieval_difference_breaks_parity(self):
        self.assertFalse(PARITY.compare(self.artifact("D1:1"),self.artifact("D1:2"))["equivalent"])
    def test_legacy_aggregate_only_rows_are_insufficient_for_positive_parity(self):
        cpu=self.artifact("D1:1"); gpu=self.artifact("D1:1"); cpu["rows"][0].pop("selected_ids"); gpu["rows"][0].pop("selected_ids"); result=PARITY.compare(cpu,gpu); self.assertFalse(result["identity_complete"]); self.assertFalse(result["equivalent"])


class V2R1RegressionTests(unittest.TestCase):
    def test_true_counter_and_bridge_orchestration(self):
        counter = BRIDGE.TokenCounter()
        dataset = [{"sample_id":"a", "conversation":{"session_1":[{"speaker":"Alice", "text":"你好 world"}], "session_2":[{"speaker":"Bob", "text":"A second session"}] }},
                   {"sample_id":"b", "conversation":{"session_1":[{"speaker":"Bob", "text":"Another scope"}]}}]
        tokens = BRIDGE.conversation_tokens(dataset, counter)
        self.assertEqual(tokens, {"a":counter("Alice: 你好 world\nBob: A second session"), "b":counter("Bob: Another scope")})
        self.assertTrue(all(n > 0 for n in tokens.values()))
        rows = [row("a",600,20,1), row("b",600,20,0)]
        bench = {"rows":rows,"modes":["hybrid"],"budgets":[600], "summaries":{"hybrid@600":{"main_categories_1_to_4":{"questions":2,"scorable":2}}}}
        result = BRIDGE.build_report(bench,{"deepseek-v4-pro_offpeak_2026-08-16":FakePricing()},{}, tokens)
        self.assertEqual(result["per_config"]["hybrid@600"]["full_history_same_query_counterfactual"]["total_input_tokens"], sum(tokens.values()))

    def test_canonical_scorable(self):
        for evidence, resolved, expected in [(0,True,False),(1,False,False),(1,True,True)]:
            self.assertEqual(BRIDGE._scorable({"evidence_count":evidence,"fully_resolved":resolved}),expected)
        self.assertFalse(BRIDGE._scorable({"evidence_count":1}))

    def test_denominator_contract_and_totals(self):
        loc = ReportClaimTests.locomo()
        econ = ReportClaimTests.econ_for(loc)
        REPORT_MD.validate_locomo_bridge_pair(loc,econ,"c"*64)
        econ["per_config"]["hybrid@600"]["scorable_questions"] = 1536
        with self.assertRaisesRegex(ValueError,"denominator contract"):
            REPORT_MD.validate_locomo_bridge_pair(loc,econ,"c"*64)
        econ = ReportClaimTests.econ_for(loc)
        econ["suite_totals"]["scorable_config_query_executions"] += 1
        with self.assertRaisesRegex(ValueError,"suite total"):
            REPORT_MD.validate_locomo_bridge_pair(loc,econ,"c"*64)

    def test_twelve_config_bridge_excludes_no_gold_and_binds_source(self):
        from research.recall.benchmark import aggregate
        rows, summaries = [], {}
        modes, budgets = ["literal","sparse","dense","hybrid"], [300,600,1200]
        for mode in modes:
            for budget in budgets:
                cohort = [row("a",budget,20,1,q=0), row("a",budget,20,0,q=1), row("a",budget,20,0,resolved=False,q=2)]
                cohort[1].update(evidence_count=0,resolved_count=0,fully_resolved=True)
                for r in cohort: r.update(mode=mode,total_ms=0,query_embedding_ms=0)
                summaries[f"{mode}@{budget}"] = {"main_categories_1_to_4":aggregate(cohort)}
                rows.extend(cohort)
        bench = {"rows":rows,"modes":modes,"budgets":budgets,"summaries":summaries}
        report = BRIDGE.build_report(bench,{"deepseek-v4-pro_offpeak_2026-08-16":FakePricing()},{})
        nconfigs = len(modes)*len(budgets)
        self.assertEqual(report["suite_totals"]["config_query_executions"],nconfigs*3)
        self.assertEqual(report["suite_totals"]["scorable_config_query_executions"],nconfigs)
        summaries["hybrid@600"]["main_categories_1_to_4"]["scorable"] += 1
        with self.assertRaisesRegex(ValueError,"denominator contract"):
            BRIDGE.build_report(bench,{"deepseek-v4-pro_offpeak_2026-08-16":FakePricing()},{})

    def test_preview_does_not_cap_total(self):
        cpu = {"rows":[row("a",600,580,1,q=i) for i in range(10)]}
        gpu = json.loads(json.dumps(cpu))
        for r in gpu["rows"]: r["selected_ids"] = ["changed"]
        result = PARITY.compare(cpu,gpu,max_mismatches=3)
        self.assertEqual(result["total_mismatch_count"],10)
        self.assertEqual(result["mismatching_row_count"],10)
        self.assertEqual(result["mismatch_preview_count"],3)
        self.assertTrue(result["mismatch_preview_truncated"])
        self.assertEqual(result["selection_set_mismatch_row_count"],10)

    def test_aggregate_and_strict_classification(self):
        cpu = HardwareParityTests().artifact("a")
        cpu["summaries"] = {"hybrid@600":{"main":{"questions":1,"any_gold_hits":1,"mrr":1,"latency_ms":{"p50":10}}}}
        cpu["rows"][0].update(selected_ids=["a","b"],selected_ranked_ids=["a","b"])
        gpu = json.loads(json.dumps(cpu))
        gpu["summaries"]["hybrid@600"]["main"]["latency_ms"]["p50"] = 1
        gpu["rows"][0]["selected_ranked_ids"] = ["b","a"]
        result = PARITY.compare(cpu,gpu)
        self.assertTrue(result["aggregate_semantic_metrics_equivalent"])
        self.assertFalse(result["strict_semantic_equivalent"])
        self.assertEqual(result["rank_only_mismatch_row_count"],1)
        self.assertEqual(result["selection_set_mismatch_row_count"],0)
        gpu["rows"][0]["selected_ids"] = ["a","c"]
        result = PARITY.compare(cpu,gpu)
        self.assertEqual(result["selection_set_mismatch_row_count"],1)
        self.assertEqual(result["rank_only_mismatch_row_count"],0)
        gpu["summaries"]["hybrid@600"]["main"]["mrr"] = .5
        self.assertFalse(PARITY.compare(cpu,gpu)["aggregate_semantic_metrics_equivalent"])

    def test_paths_fail_before_runtime(self):
        from types import SimpleNamespace
        args = SimpleNamespace(datasets_root=None, model_path=None, ce_root=None, skip_lme=True, modes=["hybrid"])
        with self.assertRaisesRegex(ValueError,"datasets-root"): RUN_SUITE.validate_inputs(args)
        with tempfile.TemporaryDirectory() as tmp:
            args.datasets_root = tmp
            Path(tmp,"locomo10.json").write_text("[]")
            with self.assertRaisesRegex(ValueError,"model-path"): RUN_SUITE.validate_inputs(args)
            args.model_path = tmp
            with self.assertRaisesRegex(ValueError,"ce-root"): RUN_SUITE.validate_inputs(args)
            args.ce_root = tmp
            Path(tmp,"model.py").write_text("")
            self.assertEqual(RUN_SUITE.validate_inputs(args)[0],Path(tmp).resolve())


if __name__ == "__main__": unittest.main()
