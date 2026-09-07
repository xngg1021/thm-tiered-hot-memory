#!/usr/bin/env python3
"""Compare CPU/GPU THM retrieval artifacts for deterministic semantic parity.

Timing, environment strings and embedding throughput are intentionally excluded.
A positive receipt requires per-query selected document identities. Legacy
artifacts that only contain aggregate hit/count metrics are reported as
insufficient rather than silently passing semantic parity.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

TOP_LEVEL_IDENTITY = (
    "protocol", "counter", "modes", "budgets", "model_id", "dataset_sha256",
    "dataset_upstream_commit", "dataset_matches_pinned_reference",
)
ROW_IDENTITY = (
    "scope", "question_index", "split", "mode", "budget", "category",
)
SEMANTIC_FIELDS = (
    "evidence_count", "resolved_count", "fully_resolved",
    "gold_sessions", "resolved_gold",
    "hits", "candidate_hits",
    "selected_count", "selected_ids", "selected_sources", "selected_ranked_ids",
    "reciprocal_rank", "candidate_reciprocal_rank", "ndcg",
    "budget_used", "malformed_evidence",
)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError(f"{path} is not a THM retrieval artifact with rows")
    return value


def row_key(row: dict, position: int) -> tuple:
    present = tuple((name, row.get(name)) for name in ROW_IDENTITY if name in row)
    return present or (("_position", position),)


def same(a, b, tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if not (math.isfinite(float(a)) and math.isfinite(float(b))):
            return a == b
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tol)
    return a == b


def _missing_selection_identity(rows: list[dict]) -> int:
    return sum(not isinstance(row.get("selected_ids"), list) for row in rows)


QUALITY_FIELDS = frozenset((
    "questions", "scorable", "no_gold_questions", "partially_or_unresolved_questions",
    "any_gold_hits", "any_gold_hit_rate", "all_gold_hit_rate", "macro_evidence_recall",
    "micro_evidence_recall", "candidate_any_gold_rate", "mrr", "ndcg", "empty_context_rate",
))


def quality_projection(value, prefix=()):
    out = {}
    if isinstance(value, dict):
        for key, child in value.items():
            if key in QUALITY_FIELDS:
                out[prefix + (key,)] = child
            elif isinstance(child, dict):
                out.update(quality_projection(child, prefix + (key,)))
    return out


def compare(cpu: dict, gpu: dict, *, float_tol: float = 0.0, max_mismatches: int = 50) -> dict:
    if not math.isfinite(float_tol) or float_tol < 0 or max_mismatches <= 0:
        raise ValueError("finite nonnegative tolerance and positive preview limit required")
    mismatches = []
    fields = Counter()
    total = 0
    max_abs_diff = 0.0
    structural = False
    def record(item):
        nonlocal total
        total += 1
        fields[item.get("field", item["kind"])] += 1
        if len(mismatches) < max_mismatches:
            mismatches.append(item)

    for field in (*TOP_LEVEL_IDENTITY, "corpus_fingerprints"):
        if cpu.get(field) != gpu.get(field):
            structural = True
            record({"kind": "top_level_identity", "field": field,
                    "cpu": cpu.get(field), "gpu": gpu.get(field)})
    cpu_rows, gpu_rows = cpu["rows"], gpu["rows"]
    if len(cpu_rows) != len(gpu_rows):
        structural = True
        record({"kind": "row_count", "cpu": len(cpu_rows), "gpu": len(gpu_rows)})
    missing_cpu = _missing_selection_identity(cpu_rows)
    missing_gpu = _missing_selection_identity(gpu_rows)
    identity_complete = missing_cpu == 0 and missing_gpu == 0
    if not identity_complete:
        record({"kind": "selection_identity_unavailable",
                "cpu_rows_missing_selected_ids": missing_cpu, "gpu_rows_missing_selected_ids": missing_gpu})
    cpu_map = {row_key(row, i): row for i, row in enumerate(cpu_rows)}
    gpu_map = {row_key(row, i): row for i, row in enumerate(gpu_rows)}
    if len(cpu_map) != len(cpu_rows) or len(gpu_map) != len(gpu_rows):
        structural = True
        record({"kind": "duplicate_row_identity"})
    counts = Counter()
    breakdown = {}
    compared = 0
    for key in sorted(set(cpu_map) | set(gpu_map), key=repr):
        left, right = cpu_map.get(key), gpu_map.get(key)
        row = left if left is not None else right
        changed = False
        selection_set = rank_only = False
        if left is None or right is None:
            structural = True
            changed = True
            record({"kind": "missing_row", "row": repr(key),
                    "cpu_present": left is not None, "gpu_present": right is not None})
        else:
            compared += 1
            for field in SEMANTIC_FIELDS:
                if field not in left and field not in right:
                    continue
                a, b = left.get(field), right.get(field)
                if (isinstance(a, (int, float)) and not isinstance(a, bool)
                    and isinstance(b, (int, float)) and not isinstance(b, bool)
                    and math.isfinite(float(a)) and math.isfinite(float(b))):
                    max_abs_diff = max(max_abs_diff, abs(float(a) - float(b)))
                if not same(a, b, float_tol):
                    changed = True
                    record({"kind": "row_field", "row": repr(key), "field": field, "cpu": a, "gpu": b})
            if isinstance(left.get("selected_ids"), list) and isinstance(right.get("selected_ids"), list):
                selection_set = set(left["selected_ids"]) != set(right["selected_ids"])
                rank_only = not selection_set and left.get("selected_ranked_ids") != right.get("selected_ranked_ids")
        if changed:
            cohort = "main_categories_1_to_4" if str(row.get("category")) in ("1", "2", "3", "4") else ("diagnostic_category_5" if str(row.get("category")) == "5" else "other")
            increments = {"mismatching_rows": 1, "selection_set_rows": int(selection_set), "rank_only_rows": int(rank_only)}
            counts.update(increments)
            counts[cohort] += 1
            label = f"{row.get('mode')}@{row.get('budget')}/category={row.get('category')}"
            breakdown.setdefault(label, Counter()).update(increments)
    cq, gq = quality_projection(cpu.get("summaries", {})), quality_projection(gpu.get("summaries", {}))
    aggregate_diff = []
    for key in sorted(set(cq) | set(gq)):
        if key not in cq or key not in gq or not same(cq.get(key), gq.get(key), float_tol):
            item = {"kind": "aggregate_metric", "field": "/".join(key), "cpu": cq.get(key), "gpu": gq.get(key)}
            aggregate_diff.append(item)
            record(item)
    aggregate_available = bool(cq) and bool(gq)
    strict = identity_complete and total == 0
    return {
        "kind": "thm-hardware-semantic-parity",
        "identity_complete": identity_complete,
        "equivalent": strict, "strict_semantic_equivalent": strict,
        "aggregate_semantic_metrics_available": aggregate_available,
        "aggregate_semantic_metrics_equivalent": aggregate_available and not structural and not aggregate_diff,
        "aggregate_metric_fields_compared": len(set(cq) & set(gq)),
        "rows_cpu": len(cpu_rows), "rows_gpu": len(gpu_rows), "rows_compared": compared,
        "float_abs_tolerance": float_tol, "max_semantic_numeric_abs_diff": max_abs_diff,
        "total_mismatch_count": total, "mismatch_preview_count": len(mismatches),
        "mismatch_preview_limit": max_mismatches, "mismatch_preview_truncated": total > len(mismatches),
        "mismatch_count_capped": len(mismatches), "mismatches": mismatches,
        "mismatching_row_count": counts["mismatching_rows"],
        "selection_set_mismatch_row_count": counts["selection_set_rows"],
        "rank_only_mismatch_row_count": counts["rank_only_rows"],
        "main_category_mismatch_row_count": counts["main_categories_1_to_4"],
        "diagnostic_mismatch_row_count": counts["diagnostic_category_5"],
        "other_category_mismatch_row_count": counts["other"],
        "mismatch_counts_by_field": dict(sorted(fields.items())),
        "mismatch_rows_by_mode_budget_category": {k: dict(v) for k, v in sorted(breakdown.items())},
        "excluded_from_parity": ["timing_ms", "query_embedding_ms", "build/index seconds", "environment strings", "wall-clock throughput"],
        "interpretation": "Strict parity includes selected IDs and ranked order across all rows, including category 5. Aggregate parity compares only explicit retrieval-quality summary fields. Rank-only classifies selection drift; other semantic field differences remain strict mismatches. Missing summaries do not establish aggregate parity.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cpu", required=True)
    ap.add_argument("--gpu", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--float-tol", type=float, default=0.0)
    ap.add_argument("--max-mismatches", type=int, default=50)
    args = ap.parse_args()
    if args.float_tol < 0 or args.max_mismatches <= 0:
        raise ValueError("float tolerance must be >=0 and mismatch cap must be >0")

    receipt = compare(
        load(Path(args.cpu)),
        load(Path(args.gpu)),
        float_tol=args.float_tol,
        max_mismatches=args.max_mismatches,
    )
    receipt["source_artifacts"] = {name: {"file": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()} for name, path in (("cpu", args.cpu), ("gpu", args.gpu))}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {out}: equivalent={receipt['equivalent']} "
        f"identity_complete={receipt['identity_complete']}"
    )
    raise SystemExit(0 if receipt["equivalent"] else 1)


if __name__ == "__main__":
    main()
