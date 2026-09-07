#!/usr/bin/env python3
"""THM x Context Economics bridge: retrieval telemetry -> cost proxies.

This is a research adapter, not a taxonomy merge and not a task-quality model.
THM T0-T3 remain memory tiers; Context Economics L0-L6 remain analysis/control
layers. The bridge consumes THM retrieval telemetry and applies the exact
Context Economics Pricing implementation from an explicitly supplied checkout.

Evidence discipline:
  - retrieval metrics: runtime-measured in the input benchmark artifact.
  - cost figures: model-proxy estimates, never observed provider bills.
  - pricing: scenario inputs documented below; conflicting snapshots remain
    separate scenarios.
  - evidence coverage is not answer accuracy or task success.

The full-history arm is a same-query counterfactual: for every benchmark query,
the source conversation's full history is priced instead of the packed retrieval
context. Its dataset bytes must match the benchmark dataset SHA-256. It does NOT
by itself establish chronological O(N^2) carry growth.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

THM_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(THM_ROOT))

from thm.retrieval import TokenCounter  # noqa: E402
from thm.sources import locomo_documents  # noqa: E402

CACHE_SHARES = (0.0, 0.5, 0.9)

SCENARIO_SPECS = {
    "deepseek-v4-pro_offpeak_2026-08-16": {
        "name": "deepseek-v4-pro-offpeak",
        "p_in": 0.66, "p_cache": 0.022, "p_out": 1.98,
    },
    "deepseek-v4-pro_peak_2026-08-16": {
        "name": "deepseek-v4-pro-peak",
        "p_in": 1.32, "p_cache": 0.044, "p_out": 3.96,
    },
    "deepseek-v4-pro_promo_2026-05-22": {
        "name": "deepseek-v4-pro-promo",
        "p_in": 0.435, "p_cache": 0.003625, "p_out": 0.87,
    },
    "kimi-k3_study_snapshot": {
        "name": "kimi-k3-study-snapshot",
        "p_in": 3.00, "p_cache": 0.30, "p_out": 15.00,
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and len(value) == 40 else None


def resolve_ce_root(value: str | None) -> Path:
    raw = value or os.environ.get("CONTEXT_ECONOMICS_ROOT")
    if not raw:
        raise ValueError(
            "Context Economics checkout required: pass --ce-root or set "
            "CONTEXT_ECONOMICS_ROOT"
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir() or not (root / "model.py").is_file():
        raise ValueError("Context Economics root must contain model.py")
    return root


def load_pricing_class(root: Path):
    model_path = root / "model.py"
    spec = importlib.util.spec_from_file_location("_thm_ce_pricing_model", model_path)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load Context Economics model.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    pricing = getattr(module, "Pricing", None)
    if pricing is None:
        raise ValueError("Context Economics model.py has no Pricing class")
    provenance = {
        "repository": "xngg1021/context-economics",
        "git_commit": git_head(root),
        "model_sha256": sha256_file(model_path),
    }
    return pricing, provenance


def build_scenarios(pricing_cls) -> dict[str, Any]:
    return {name: pricing_cls(**spec) for name, spec in SCENARIO_SPECS.items()}


def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "rows" not in data or "summaries" not in data:
        raise ValueError("not a THM benchmark result (missing rows/summaries)")
    if data.get("protocol") != 2:
        raise ValueError("economics bridge requires THM LoCoMo Protocol 2")
    if data.get("counter") != "cl100k_base":
        raise ValueError("economics bridge requires cl100k_base accounting")
    return data


def load_dataset_verified(path: Path, expected_sha256: str) -> tuple[list, str]:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("benchmark artifact must carry a 64-character dataset_sha256")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError(
            "counterfactual dataset SHA-256 does not match the benchmark artifact"
        )
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError("LoCoMo dataset must be a nonempty list")
    return data, digest


def conversation_tokens(dataset: list, counter) -> dict[str, int]:
    """Return full-history tokens by LoCoMo conversation scope."""
    out: dict[str, int] = {}
    for sample in dataset:
        scope = str(sample.get("sample_id"))
        if not scope or scope in out:
            raise ValueError("dataset contains missing/duplicate sample_id")
        blocks = [f"{doc.speaker}: {doc.text}" for doc in locomo_documents(sample)]
        out[scope] = counter("\n\n".join(blocks))
    return out


def usd(value: float) -> float:
    return round(value, 6)


def input_cost(tokens: int | float, pricing, rho: float) -> float:
    """Price one request, honoring CE long-context request-rate semantics."""
    rate = pricing.effective_input_rate(rho, prompt_tokens=float(tokens))
    return float(tokens) / 1_000_000 * rate


def _scorable(row: dict) -> bool:
    return bool(row.get("fully_resolved")) and int(row.get("evidence_count", 0)) > 0


def economics_for_rows(
    rows: list[dict],
    pricing,
    full_history_tokens: dict[str, int] | None = None,
) -> dict:
    """Cost proxies for one mode@budget slice on one common query denominator."""
    if not rows:
        return {}
    budgets = {int(r["budget"]) for r in rows}
    if len(budgets) != 1:
        raise ValueError("one economics slice must contain exactly one budget")
    budget = budgets.pop()
    n = len(rows)
    scorable = sum(_scorable(r) for r in rows)
    packed_tokens = [int(r["budget_used"]) for r in rows]
    total_packed_tokens = sum(packed_tokens)
    gold_hits = sum(int(r["hits"]) for r in rows if _scorable(r))
    any_gold = sum(int(r["hits"]) > 0 for r in rows if _scorable(r))

    scenarios = {}
    for rho in CACHE_SHARES:
        costs = [input_cost(tokens, pricing, rho) for tokens in packed_tokens]
        total_cost = sum(costs)
        scenarios[f"rho={rho}"] = {
            "mean_effective_input_rate_per_1M": usd(
                sum(pricing.effective_input_rate(rho, prompt_tokens=t) for t in packed_tokens) / n
            ),
            "per_query_input_cost_usd": usd(total_cost / n),
            "total_input_cost_usd": usd(total_cost),
            "cost_per_gold_evidence_hit_usd": usd(total_cost / gold_hits) if gold_hits else None,
            "cost_per_any_gold_scorable_question_usd": usd(total_cost / any_gold) if any_gold else None,
        }

    out = {
        "attempted_questions": n,
        "scorable_questions": scorable,
        "budget": budget,
        "mean_budget_used_tokens": round(total_packed_tokens / n, 2),
        "total_packed_retrieval_tokens": total_packed_tokens,
        "gold_evidence_hits": gold_hits,
        "any_gold_scorable_questions": any_gold,
        "pricing_scenarios": scenarios,
    }

    if full_history_tokens is not None:
        missing = sorted({str(r["scope"]) for r in rows} - set(full_history_tokens))
        if missing:
            raise ValueError(f"full-history token map missing scopes: {missing[:5]}")
        full_tokens = [full_history_tokens[str(r["scope"])] for r in rows]
        total_full_tokens = sum(full_tokens)
        arm = {
            "attempted_questions": n,
            "mean_input_tokens_per_query": round(total_full_tokens / n, 2),
            "total_input_tokens": total_full_tokens,
            "tokens_ratio_vs_packed_retrieval": round(
                total_full_tokens / total_packed_tokens, 4
            ) if total_packed_tokens else None,
            "pricing_scenarios": {},
        }
        for rho in CACHE_SHARES:
            full_cost = sum(input_cost(tokens, pricing, rho) for tokens in full_tokens)
            packed_cost = sum(input_cost(tokens, pricing, rho) for tokens in packed_tokens)
            arm["pricing_scenarios"][f"rho={rho}"] = {
                "per_query_input_cost_usd": usd(full_cost / n),
                "total_input_cost_usd_same_queries": usd(full_cost),
                "cost_ratio_vs_packed_retrieval": round(
                    full_cost / packed_cost, 4
                ) if packed_cost else None,
            }
        out["full_history_same_query_counterfactual"] = arm
    return out


def marginal_analysis(rows_keyed: dict, pricing) -> dict:
    """L6-style grid sensitivity, with percentage-point units explicit."""
    out = {}
    for mode, budget_rows in rows_keyed.items():
        budgets = sorted(budget_rows)
        if len(budgets) < 2:
            continue
        out[mode] = {}
        for lo, hi in zip(budgets, budgets[1:]):
            r_lo, r_hi = budget_rows[lo], budget_rows[hi]
            s_lo = [r for r in r_lo if _scorable(r)]
            s_hi = [r for r in r_hi if _scorable(r)]
            if not s_lo or not s_hi or len(s_lo) != len(s_hi):
                raise ValueError("marginal comparison requires equal nonempty scorable cohorts")
            any_lo = sum(int(r["hits"]) > 0 for r in s_lo) / len(s_lo)
            any_hi = sum(int(r["hits"]) > 0 for r in s_hi) / len(s_hi)
            delta_rate = any_hi - any_lo
            cost_lo = sum(input_cost(int(r["budget_used"]), pricing, 0.0) for r in r_lo)
            cost_hi = sum(input_cost(int(r["budget_used"]), pricing, 0.0) for r in r_hi)
            delta_cost = cost_hi - cost_lo
            delta_pp = delta_rate * 100.0
            out[mode][f"{lo}->{hi}"] = {
                "delta_any_gold_rate": round(delta_rate, 6),
                "delta_any_gold_percentage_points": round(delta_pp, 4),
                "delta_packed_tokens": sum(int(r["budget_used"]) for r in r_hi)
                                      - sum(int(r["budget_used"]) for r in r_lo),
                "delta_input_cost_usd_rho0": usd(delta_cost),
                "marginal_cost_usd_per_1pp_any_gold_gain": (
                    usd(delta_cost / delta_pp) if delta_pp > 0 else None
                ),
            }
    return out


def build_report(
    bench: dict,
    scenarios: dict,
    ce_provenance: dict,
    full_history_tokens: dict[str, int] | None = None,
    result_name: str | None = None,
    counterfactual_dataset_sha256: str | None = None,
) -> dict:
    rows = bench["rows"]
    mode_budgets: dict[str, dict[int, list[dict]]] = {}
    for row in rows:
        if int(row["category"]) == 5:
            continue
        mode_budgets.setdefault(str(row["mode"]), {}).setdefault(
            int(row["budget"]), []
        ).append(row)

    primary_name = "deepseek-v4-pro_offpeak_2026-08-16"
    primary = scenarios[primary_name]
    per_config = {}
    for mode, budgets in mode_budgets.items():
        for budget, slice_rows in budgets.items():
            per_config[f"{mode}@{budget}"] = economics_for_rows(
                slice_rows, primary, full_history_tokens
            )

    all_main_rows = [row for row in rows if int(row["category"]) != 5]
    config_count = len(per_config)
    attempted_by_config = sorted({v["attempted_questions"] for v in per_config.values()})
    scorable_by_config = sorted({v["scorable_questions"] for v in per_config.values()})

    suite_totals = {
        "config_count": config_count,
        "config_query_executions": len(all_main_rows),
        "scorable_config_query_executions": sum(_scorable(r) for r in all_main_rows),
        "attempted_questions_per_config": attempted_by_config[0] if len(attempted_by_config) == 1 else attempted_by_config,
        "scorable_questions_per_config": scorable_by_config[0] if len(scorable_by_config) == 1 else scorable_by_config,
        "total_packed_retrieval_tokens": sum(int(r["budget_used"]) for r in all_main_rows),
        "note": (
            "Suite totals sum every mode@budget arm. They are experiment-run totals, "
            "not the cost of one deployed policy."
        ),
        "pricing_scenarios": {},
    }
    for name, pricing in scenarios.items():
        suite_totals["pricing_scenarios"][name] = {}
        for rho in CACHE_SHARES:
            total = sum(input_cost(int(r["budget_used"]), pricing, rho) for r in all_main_rows)
            suite_totals["pricing_scenarios"][name][f"rho={rho}"] = {
                "total_input_cost_usd": usd(total)
            }

    benchmark_info = {
        "file": result_name,
        "protocol": bench.get("protocol"),
        "counter": bench.get("counter"),
        "dataset_sha256": bench.get("dataset_sha256"),
        "modes": bench.get("modes"),
        "budgets": bench.get("budgets"),
        "generation_calls": bench.get("generation_calls"),
        "judge_calls": bench.get("judge_calls"),
    }
    if counterfactual_dataset_sha256 is not None:
        benchmark_info["counterfactual_dataset_sha256"] = counterfactual_dataset_sha256
        benchmark_info["counterfactual_dataset_matches_benchmark"] = (
            counterfactual_dataset_sha256 == bench.get("dataset_sha256")
        )

    return {
        "kind": "thm-x-context-economics-bridge-v2",
        "evidence_labels": {
            "retrieval_metrics": "runtime-measured",
            "cost_figures": "model-proxy",
            "pricing": "provider-doc-as-relayed (conflicting snapshots; scenarios only)",
            "answer_accuracy": "not_measured",
            "observed_provider_bill": "not_measured",
        },
        "context_economics_provenance": ce_provenance,
        "benchmark": benchmark_info,
        "pricing_scenario_specs": SCENARIO_SPECS,
        "primary_proxy_scenario": primary_name,
        "per_config": per_config,
        "suite_totals": suite_totals,
        "l6_budget_grid_sensitivity": marginal_analysis(mode_budgets, primary),
        "interpretation_limits": [
            "Retrieval evidence coverage is not answer accuracy or task success.",
            "All monetary values are pricing-model proxies, not observed bills.",
            "Per-config full-history comparisons use exactly the same benchmark queries and dataset bytes.",
            "Suite totals aggregate all experimental arms and are not a deployed-policy cost.",
            "The full-history counterfactual does not by itself prove chronological O(N^2) growth.",
            "Only three tested budgets are present; a 600-token knee is a grid observation, not an optimized threshold.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", required=True)
    ap.add_argument("--dataset", help="locomo10.json for same-query full-history counterfactual")
    ap.add_argument("--ce-root", help="Context Economics checkout; or CONTEXT_ECONOMICS_ROOT")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    bench_path = Path(args.results)
    bench = load_benchmark(bench_path)
    ce_root = resolve_ce_root(args.ce_root)
    pricing_cls, ce_provenance = load_pricing_class(ce_root)
    scenarios = build_scenarios(pricing_cls)

    full_history = None
    dataset_digest = None
    if args.dataset:
        dataset, dataset_digest = load_dataset_verified(
            Path(args.dataset), bench.get("dataset_sha256")
        )
        full_history = conversation_tokens(dataset, TokenCounter("cl100k_base"))

    report = build_report(
        bench, scenarios, ce_provenance, full_history, bench_path.name,
        counterfactual_dataset_sha256=dataset_digest,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
