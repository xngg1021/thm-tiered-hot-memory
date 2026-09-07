#!/usr/bin/env python3
"""Bridge THM retrieval artifacts into Context Economics pricing proxies.

This module deliberately remains a research adapter rather than a production
cross-repository dependency. It consumes runtime-measured THM evidence and an
explicit Context Economics checkout, then emits model-proxy economics with
matched query denominators and pinned provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thm.retrieval import TokenCounter

CACHE_SHARES = (0.0, 0.5, 0.9)

SCENARIO_SPECS = {
    "deepseek-v4-pro_offpeak_2026-08-16": {
        "name": "deepseek-v4-pro_offpeak_2026-08-16",
        "p_in": 0.66,
        "p_cache": 0.022,
        "p_out": 2.64,
    },
    "deepseek-v4-pro_peak_2026-08-16": {
        "name": "deepseek-v4-pro_peak_2026-08-16",
        "p_in": 1.32,
        "p_cache": 0.044,
        "p_out": 5.28,
    },
    "deepseek-v4-pro_promo_2026-08-16": {
        "name": "deepseek-v4-pro_promo_2026-08-16",
        "p_in": 0.435,
        "p_cache": 0.0145,
        "p_out": 1.74,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_ce_root(cli_value: str | None) -> Path:
    raw = cli_value or os.environ.get("CONTEXT_ECONOMICS_ROOT")
    if not raw:
        raise ValueError(
            "Context Economics checkout is required: pass --ce-root or set "
            "CONTEXT_ECONOMICS_ROOT"
        )
    root = Path(raw).expanduser().resolve()
    model = root / "model.py"
    if not model.is_file():
        raise FileNotFoundError(f"Context Economics model.py not found under {root}")
    return root


def _git_commit(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = proc.stdout.strip()
    return value if len(value) == 40 else None


def load_pricing_class(root: Path):
    model_path = root / "model.py"
    module_name = f"context_economics_model_{sha256_file(model_path)[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {model_path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses and other decorators may inspect sys.modules while a module is
    # executing, so register this explicitly before exec_module().
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    pricing_cls = getattr(module, "Pricing", None)
    if pricing_cls is None:
        raise AttributeError(f"{model_path} has no Pricing class")
    return pricing_cls, {
        "root_name": root.name,
        "git_commit": _git_commit(root),
        "model_sha256": sha256_file(model_path),
    }


def build_scenarios(pricing_cls) -> dict:
    scenarios = {}
    for name, spec in SCENARIO_SPECS.items():
        scenarios[name] = pricing_cls(**spec)
    return scenarios


def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError(f"invalid benchmark artifact: {path}")
    digest = data.get("dataset_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("benchmark artifact is missing a valid dataset_sha256")
    return data


def load_dataset_verified(path: Path, expected_sha256: str) -> tuple[object, str]:
    digest = sha256_file(path)
    if digest != expected_sha256:
        raise ValueError(
            "counterfactual dataset SHA-256 does not match benchmark artifact: "
            f"expected {expected_sha256}, got {digest}"
        )
    return json.loads(path.read_text(encoding="utf-8")), digest


def _speaker_text(turn: dict) -> str:
    speaker = turn.get("speaker") or turn.get("name") or turn.get("role") or "unknown"
    text = turn.get("text") or turn.get("content") or turn.get("message") or ""
    return f"{speaker}: {text}"


def _extract_conversation(sample: dict) -> list[dict]:
    conversation = sample.get("conversation") or sample.get("conversations") or sample.get("dialogue")
    if isinstance(conversation, list):
        return [turn for turn in conversation if isinstance(turn, dict)]
    # LoCoMo commonly stores sessions as conversation/session_N arrays. Preserve
    # source order and concatenate each session as one full-history text stream.
    if isinstance(conversation, dict):
        turns: list[dict] = []
        for key, value in conversation.items():
            if str(key).lower().startswith("session") and isinstance(value, list):
                turns.extend(turn for turn in value if isinstance(turn, dict))
        if turns:
            return turns
    turns = []
    for key, value in sample.items():
        if str(key).lower().startswith("session") and isinstance(value, list):
            turns.extend(turn for turn in value if isinstance(turn, dict))
    return turns


def conversation_tokens(dataset: object, counter: TokenCounter) -> dict[str, int]:
    if isinstance(dataset, dict):
        samples = dataset.get("data") or dataset.get("samples") or dataset.get("conversations")
    else:
        samples = dataset
    if not isinstance(samples, list):
        raise ValueError("counterfactual dataset must contain a list of LoCoMo samples")
    out: dict[str, int] = {}
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            continue
        scope = str(sample.get("sample_id") or sample.get("conversation_id") or index)
        turns = _extract_conversation(sample)
        text = "\n".join(_speaker_text(turn) for turn in turns)
        out[scope] = counter.count(text)
    return out


def usd(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _effective_rate(pricing, rho: float, prompt_tokens: int) -> float:
    try:
        return float(pricing.effective_input_rate(rho, prompt_tokens=prompt_tokens))
    except TypeError:
        return float(pricing.effective_input_rate(rho))


def input_cost(tokens: int, pricing, rho: float) -> float:
    return tokens / 1_000_000.0 * _effective_rate(pricing, rho, tokens)


def _scorable(row: dict) -> bool:
    return bool(row.get("fully_resolved", row.get("resolved_count") == row.get("evidence_count")))


def economics_for_rows(
    rows: list[dict],
    pricing,
    full_history_tokens: dict[str, int] | None = None,
) -> dict:
    n = len(rows)
    if n == 0:
        raise ValueError("economics_for_rows requires a nonempty query cohort")
    scorable = [row for row in rows if _scorable(row)]
    any_gold = sum(int(row.get("hits", 0)) > 0 for row in scorable)
    packed_tokens = [int(row.get("budget_used", 0)) for row in rows]
    total_packed_tokens = sum(packed_tokens)
    out = {
        "attempted_questions": n,
        "scorable_questions": len(scorable),
        "any_gold_scorable_questions": any_gold,
        "mean_packed_tokens_per_query": round(total_packed_tokens / n, 2),
        "total_packed_tokens": total_packed_tokens,
        "pricing_scenarios": {},
    }
    for rho in CACHE_SHARES:
        packed_cost = sum(input_cost(tokens, pricing, rho) for tokens in packed_tokens)
        out["pricing_scenarios"][f"rho={rho}"] = {
            "per_query_input_cost_usd": usd(packed_cost / n),
            "total_input_cost_usd_same_queries": usd(packed_cost),
            "cost_per_any_gold_scorable_question_usd": (
                usd(packed_cost / any_gold) if any_gold else None
            ),
        }

    if full_history_tokens is not None:
        missing = sorted({str(r["scope"]) for r in rows if str(r["scope"]) not in full_history_tokens})
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


def interpretation_limits_for_bench(bench: dict) -> list[str]:
    limits = [
        "Retrieval evidence coverage is not answer accuracy or task success.",
        "All monetary values are pricing-model proxies, not observed bills.",
        "Per-config full-history comparisons use exactly the same benchmark queries and dataset bytes.",
        "Suite totals aggregate all experimental arms and are not a deployed-policy cost.",
        "The full-history counterfactual does not by itself prove chronological O(N^2) growth.",
    ]
    budgets = sorted({int(value) for value in (bench.get("budgets") or [])})
    if budgets == [300, 600, 1200]:
        limits.append(
            "The tested budget grid is 300/600/1200; 600 can at most be treated as a grid-level knee candidate, not an optimized global threshold."
        )
    elif budgets:
        limits.append(
            f"Budget sensitivity is limited to the tested grid {budgets}; no untested budget or global optimum is established."
        )
    else:
        limits.append(
            "No explicit budget grid is recorded; no budget-knee or global-optimum claim is supported."
        )
    return limits


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
        "interpretation_limits": interpretation_limits_for_bench(bench),
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
