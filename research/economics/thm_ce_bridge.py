#!/usr/bin/env python3
"""THM x Context-Economics bridge: retrieval telemetry -> L4/L5/L6 economics.

Reads a THM retrieval benchmark result (research/recall/benchmark.py output),
applies the context-economics Pricing model (imported from the CE repository),
and produces per-configuration task-economic estimates plus a full-history
carry-along counterfactual arm.

Evidence discipline (CE labels):
  - retrieval metrics: runtime-measured on this machine (benchmark JSON).
  - cost figures: model-proxy. They are billing estimates from published
    pricing, NOT observed bills. generation_calls=0, judge_calls=0.
  - pricing: provider-doc-as-relayed. Multiple conflicting third-party
    snapshots exist for deepseek-v4-pro (promo 0.435 vs Aug-16 peak/off-peak
    0.66/1.32); all are presented as scenarios, none asserted as the live rate.

Retrieval evidence coverage is not answer accuracy; costs here are the cost
of the retrieval context only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # THM engine
sys.path.insert(0, r"D:/hermes-home/you/repos/context-economics")      # CE repo

from model import Pricing  # noqa: E402  (context-economics L0 model)
from thm.retrieval import TokenCounter  # noqa: E402


# ---- Pricing scenarios (all USD per 1M tokens; provider-doc-as-relayed) ----
SCENARIOS = {
    "deepseek-v4-pro_offpeak_2026-08-16": Pricing(
        "deepseek-v4-pro-offpeak", 0.66, 0.022, 1.98),
    "deepseek-v4-pro_peak_2026-08-16": Pricing(
        "deepseek-v4-pro-peak", 1.32, 0.044, 3.96),
    "deepseek-v4-pro_promo_2026-05-22": Pricing(
        "deepseek-v4-pro-promo", 0.435, 0.003625, 0.87),
    "kimi-k3_study_snapshot": Pricing(
        "kimi-k3-study-snapshot", 3.00, 0.30, 15.00),
}

CACHE_SHARES = [0.0, 0.5, 0.9]  # rho scenarios for the recall context prefix


def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "rows" not in data or "summaries" not in data:
        raise ValueError("not a THM benchmark result (missing rows/summaries)")
    return data


def load_dataset(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def conversation_tokens(dataset: list, counter) -> dict:
    """Total document tokens per conversation (cl100k_base), for the
    full-history carry-along counterfactual arm. Uses the same parsing as
    the benchmark (thm.sources.locomo_documents)."""
    from thm.sources import locomo_documents
    out = {}
    for sample in dataset:
        total = 0
        for doc in locomo_documents(sample):
            total += counter(f"{doc.speaker}: {doc.text}")
        out[str(sample.get("sample_id"))] = total
    return out


def usd(v: float) -> float:
    return round(v, 6)


def economics_for_rows(rows, questions_total, pricing: Pricing, counterfactual_tokens: int | None = None):
    """L5 per-config economics for one mode@budget slice."""
    if not rows:
        return {}
    budget = rows[0]["budget"]
    mean_budget_used = sum(r["budget_used"] for r in rows) / len(rows)
    total_recall_tokens = sum(r["budget_used"] for r in rows)
    n = len(rows)
    gold_hits = sum(r["hits"] for r in rows)
    any_gold_questions = sum(1 for r in rows if r["hits"] > 0 and r["fully_resolved"])

    scenarios = {}
    for rho in CACHE_SHARES:
        p_eff = pricing.effective_input_rate(rho)
        per_query_input = mean_budget_used / 1_000_000 * p_eff
        total_input = total_recall_tokens / 1_000_000 * p_eff
        scenarios[f"rho={rho}"] = {
            "effective_input_rate_per_1M": usd(p_eff),
            "per_query_input_cost_usd": usd(per_query_input),
            "total_input_cost_usd": usd(total_input),
            "cost_per_gold_hit_usd": usd(total_input / gold_hits) if gold_hits else None,
            "cost_per_any_gold_question_usd": usd(total_input / any_gold_questions) if any_gold_questions else None,
        }

    out = {
        "questions": n,
        "budget": budget,
        "mean_budget_used_tokens": round(mean_budget_used, 2),
        "total_recall_tokens": total_recall_tokens,
        "gold_hits": gold_hits,
        "any_gold_questions": any_gold_questions,
        "pricing_scenarios": scenarios,
    }
    if counterfactual_tokens:
        # Full-history carry-along: the whole conversation is re-sent per query.
        per_query_tokens = counterfactual_tokens
        out["counterfactual_full_history"] = {
            "per_query_tokens": per_query_tokens,
            "tokens_ratio_vs_recall": round(per_query_tokens / mean_budget_used, 1),
            "costs": {},
        }
        for rho in CACHE_SHARES:
            p_eff = pricing.effective_input_rate(rho)
            per_query = per_query_tokens / 1_000_000 * p_eff
            out["counterfactual_full_history"]["costs"][f"rho={rho}"] = {
                "per_query_input_cost_usd": usd(per_query),
                "total_cost_usd_1986_queries": usd(per_query * questions_total),
            }
    return out


def marginal_analysis(summaries_keyed, rows_keyed):
    """L6-style budget feedback: delta recall vs delta cost across budgets."""
    out = {}
    for mode in rows_keyed:
        budgets = sorted(rows_keyed[mode], key=lambda b: int(b))
        if len(budgets) < 2:
            continue
        out[mode] = {}
        for lo, hi in zip(budgets, budgets[1:]):
            r_lo = rows_keyed[mode][lo]
            r_hi = rows_keyed[mode][hi]
            scorable_lo = sum(1 for r in r_lo if r["fully_resolved"])
            scorable_hi = sum(1 for r in r_hi if r["fully_resolved"])
            any_lo = sum(1 for r in r_lo if r["hits"] > 0 and r["fully_resolved"]) / scorable_lo if scorable_lo else 0
            any_hi = sum(1 for r in r_hi if r["hits"] > 0 and r["fully_resolved"]) / scorable_hi if scorable_hi else 0
            d_recall = any_hi - any_lo
            d_tokens = sum(r["budget_used"] for r in r_hi) - sum(r["budget_used"] for r in r_lo)
            # cost delta at off-peak, rho=0
            d_cost = d_tokens / 1_000_000 * SCENARIOS["deepseek-v4-pro_offpeak_2026-08-16"].p_in
            out[mode][f"{lo}->{hi}"] = {
                "delta_any_gold_rate": round(d_recall, 4),
                "delta_recall_tokens": d_tokens,
                "delta_input_cost_usd_offpeak_rho0": usd(d_cost),
                "marginal_cost_per_point_of_recall_usd": usd(d_cost / d_recall) if d_recall > 0 else None,
            }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--dataset", default=None, help="locomo10.json for the counterfactual arm")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    bench = load_benchmark(Path(args.results))
    rows = bench["rows"]

    # Key rows by mode and budget, main categories 1-4 only.
    mode_budgets: dict[str, dict[int, list]] = {}
    for r in rows:
        if r["category"] == 5:
            continue
        mode_budgets.setdefault(r["mode"], {}).setdefault(int(r["budget"]), []).append(r)

    counter_tokens = {}
    if args.dataset:
        ds = load_dataset(Path(args.dataset))
        counter_tokens = conversation_tokens(ds, TokenCounter("cl100k_base"))

    report = {
        "kind": "thm-x-context-economics-bridge",
        "evidence_labels": {
            "retrieval_metrics": "runtime-measured",
            "cost_figures": "model-proxy",
            "pricing": "provider-doc-as-relayed (conflicting snapshots; scenarios only)",
        },
        "benchmark": {
            "file": Path(args.results).name,
            "protocol": bench.get("protocol"),
            "counter": bench.get("counter"),
            "modes": bench.get("modes"),
            "budgets": bench.get("budgets"),
            "generation_calls": bench.get("generation_calls"),
            "judge_calls": bench.get("judge_calls"),
        },
        "l5_per_config": {},
        "l6_marginal": marginal_analysis({}, mode_budgets),
    }

    for mode, budgets in mode_budgets.items():
        for budget, slice_rows in budgets.items():
            key = f"{mode}@{budget}"
            cf = None
            if counter_tokens and slice_rows:
                # Counterfactual uses the mean conversation size seen by these rows.
                scope_tokens = {}
                for r in slice_rows:
                    scope_tokens[r["scope"]] = counter_tokens.get(r["scope"], 0)
                if scope_tokens:
                    cf = int(sum(scope_tokens.values()) / len(scope_tokens))
            report["l5_per_config"][key] = economics_for_rows(
                slice_rows, len(slice_rows), SCENARIOS["deepseek-v4-pro_offpeak_2026-08-16"], cf)

    # Total-scope numbers: full 1986-question run cost per scenario.
    total_questions = len([r for r in rows if r["category"] != 5])
    report["l5_totals"] = {}
    for name, pricing in SCENARIOS.items():
        total_tokens = sum(r["budget_used"] for r in rows if r["category"] != 5)
        rho_totals = {}
        for rho in CACHE_SHARES:
            p_eff = pricing.effective_input_rate(rho)
            rho_totals[f"rho={rho}"] = {
                "total_input_cost_usd": usd(total_tokens / 1_000_000 * p_eff),
            }
        report["l5_totals"][name] = {
            "questions": total_questions,
            "total_recall_tokens": total_tokens,
            "per_scenario": rho_totals,
        }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
