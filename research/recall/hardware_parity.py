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
import sys
import json
import math
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.evidence_io import read_json_bound, require_new_output, write_new_text
from research.recall.scoring import is_scorable

TOP_LEVEL_IDENTITY = (
    "protocol", "counter", "modes", "budgets", "model_id", "dataset_sha256",
    "dataset_upstream_commit", "dataset_matches_pinned_reference",
    "idf_scope", "neighbor_turns", "generation_calls", "judge_calls",
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
    value, digest = read_json_bound(path)
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise ValueError(f"{path} is not a THM retrieval artifact with rows")
    return value, digest


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



def top_level_coverage_errors(data):
    """Shared omissions cannot establish the provenance of a parity pair."""
    errors = []
    def require(field, valid):
        if field not in data or not valid(data.get(field)):
            errors.append(field)
    def digest(value, length=64):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{%d}" % length, value) is not None
    require("protocol", lambda v: type(v) is int and v in (1, 2))
    require("counter", lambda v: isinstance(v, str) and bool(v.strip()))
    require("modes", lambda v: isinstance(v, list) and bool(v) and all(isinstance(m, str) and m in ("literal", "sparse", "dense", "hybrid") for m in v) and len(set(v)) == len(v))
    require("budgets", lambda v: isinstance(v, list) and bool(v) and all(type(b) is int and b >= 0 for b in v) and len(set(v)) == len(v))
    dense = isinstance(data.get("modes"), list) and any(m in ("dense", "hybrid") for m in data["modes"])
    require("model_id", lambda v: (isinstance(v, str) and bool(v.strip())) or (v is None and not dense))
    require("dataset_sha256", digest)
    require("corpus_fingerprints", lambda v: isinstance(v, dict) and bool(v) and all(isinstance(k, str) and bool(k) and digest(d) for k, d in v.items()) and all(isinstance(r.get("scope"), str) for r in data["rows"]) and set(v) == {r["scope"] for r in data["rows"]})
    expected_idf = "one_database_per_conversation" if data.get("protocol") == 2 else "one_database_per_instance"
    require("idf_scope", lambda v: v == expected_idf)
    for field in ("generation_calls", "judge_calls"):
        require(field, lambda v: type(v) is int and v >= 0)
    if data.get("protocol") == 2:
        require("neighbor_turns", lambda v: type(v) is int and v >= 0)
        require("dataset_matches_pinned_reference", lambda v: type(v) is bool)
        require("dataset_upstream_commit", lambda v: digest(v, 40) or (v is None and data.get("dataset_matches_pinned_reference") is False))
    elif data.get("protocol") == 1:
        require("benchmark", lambda v: v == "LongMemEval-S retrieval coverage (session-level evidence)")
    return errors


def strict_row_coverage_errors(data):
    """Known runner fields must be present before complete strict claims."""
    if not data["rows"]:
        return {"no_measured_rows": 1}
    common = {"scope", "split", "mode", "budget", "hits", "selected_count",
              "selected_ids", "reciprocal_rank", "budget_used"}
    protocol = data.get("protocol")
    if protocol == 2:
        required = common | {"question_index", "category", "evidence_count", "resolved_count",
                             "fully_resolved", "candidate_hits", "candidate_reciprocal_rank",
                             "selected_ranked_ids", "ndcg", "malformed_evidence"}
    elif protocol == 1 and data.get("benchmark") == "LongMemEval-S retrieval coverage (session-level evidence)":
        required = common | {"gold_sessions", "resolved_gold", "candidate_hits", "selected_sources"}
    else:
        return {"unsupported_row_protocol": len(data["rows"]) or 1}
    errors = Counter()
    for row in data["rows"]:
        for field in required - set(row):
            errors[f"missing:{field}"] += 1
        count_fields = {"question_index", "category", "budget", "hits", "selected_count", "budget_used",
                        "evidence_count", "resolved_count", "gold_sessions", "resolved_gold", "candidate_hits"}
        rate_fields = {"reciprocal_rank", "candidate_reciprocal_rank", "ndcg"}
        for field in required & count_fields:
            value = row.get(field)
            if protocol == 1 and field == "candidate_hits" and value is None:
                continue
            if type(value) is not int or value < 0:
                errors[f"invalid:{field}"] += 1
        for field in required & rate_fields:
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                errors[f"invalid:{field}"] += 1
        for field in required & {"fully_resolved", "malformed_evidence"}:
            if type(row.get(field)) is not bool:
                errors[f"invalid:{field}"] += 1
        for field in ("scope", "split", "mode"):
            if not isinstance(row.get(field), str):
                errors[f"invalid:{field}"] += 1
        if row.get("split") not in ("development", "held_out"):
            errors["invalid:split"] += 1
        ids = row.get("selected_ids")
        valid_ids = isinstance(ids, list) and all(isinstance(value, str) for value in ids)
        if not valid_ids:
            errors["invalid:selected_ids"] += 1
            continue
        if len(set(ids)) != len(ids) or type(row.get("selected_count")) is not int or row.get("selected_count") != len(ids):
            errors["inconsistent:selected_count_or_ids"] += 1
        if protocol == 2:
            ranks = row.get("selected_ranked_ids")
            if not isinstance(ranks, list) or not all(isinstance(value, str) for value in ranks):
                errors["invalid:selected_ranked_ids"] += 1
            elif len(ranks) != len(ids) or set(ranks) != set(ids):
                errors["inconsistent:selected_ranked_ids"] += 1
        else:
            sources = row.get("selected_sources")
            if not isinstance(sources, list) or len(sources) != len(ids) or not all(isinstance(value, str) for value in sources):
                errors["invalid:selected_sources"] += 1
    return dict(sorted(errors.items()))

def grid_cohort_errors(data):
    """Every declared arm must measure the same nonempty query cohort once."""
    if top_level_coverage_errors(data) or strict_row_coverage_errors(data):
        return ["invalid provenance or row schema"]
    grid = {(mode, budget): [] for mode in data["modes"] for budget in data["budgets"]}
    metadata = {}
    errors = []
    for row in data["rows"]:
        arm = (row["mode"], row["budget"])
        if arm not in grid:
            errors.append("measured row outside declared grid")
            continue
        query = (row["scope"], row["question_index"]) if data["protocol"] == 2 else (row["scope"],)
        grid[arm].append(query)
        fields = ("split", "category", "evidence_count", "resolved_count", "fully_resolved", "malformed_evidence") if data["protocol"] == 2 else ("split", "gold_sessions", "resolved_gold")
        values = tuple(row.get(field) for field in fields)
        if query in metadata and metadata[query] != values:
            errors.append("query metadata differs across grid arms")
        metadata[query] = values
    expected = set(metadata)
    for arm, queries in grid.items():
        if not queries or len(queries) != len(set(queries)) or set(queries) != expected:
            errors.append(f"incomplete or duplicate query cohort: {arm[0]}@{arm[1]}")
    return sorted(set(errors))


QUALITY_FIELDS = frozenset((
    "questions", "scorable", "no_gold_questions", "partially_or_unresolved_questions",
    "any_gold_hits", "any_gold_hit_rate", "all_gold_hit_rate", "macro_evidence_recall",
    "micro_evidence_recall", "candidate_any_gold_rate", "mrr", "ndcg", "empty_context_rate", "mean_budget_used",
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


def summary_coverage_errors(data):
    """Require the full known runner schema, including empty cohorts."""
    if top_level_coverage_errors(data):
        return ["incomplete top-level provenance"]
    if any(row.get("split") not in ("development", "held_out") for row in data["rows"]):
        return ["measured row outside development/held_out partition"]
    cohort_errors = grid_cohort_errors(data)
    if cohort_errors:
        return cohort_errors
    modes, budgets = data.get("modes"), data.get("budgets")
    if not isinstance(modes, list) or not modes or not isinstance(budgets, list) or not budgets:
        return ["missing mode/budget grid"]
    if len(set(modes)) != len(modes) or len(set(budgets)) != len(budgets):
        return ["duplicate grid entries"]
    expected = {f"{mode}@{budget}" for mode in modes for budget in budgets}
    if any(f"{row.get('mode')}@{row.get('budget')}" not in expected for row in data["rows"]):
        return ["measured row outside declared mode/budget grid"]
    summaries = data.get("summaries")
    if not isinstance(summaries, dict) or set(summaries) != expected:
        return ["missing or unexpected summary configurations"]
    if data.get("protocol") == 2:
        predicates = {
            "main_categories_1_to_4": lambda r: r.get("category") in (1,2,3,4),
            "conversational_categories_1_2_4": lambda r: r.get("category") in (1,2,4),
            "all_categories_diagnostic_only": lambda r: True,
            "development": lambda r: r.get("split") == "development" and r.get("category") in (1,2,3,4),
            "held_out": lambda r: r.get("split") == "held_out" and r.get("category") in (1,2,3,4),
        }
        for category, name in enumerate(("multi_hop", "temporal", "open_domain", "single_hop", "adversarial"), 1):
            predicates[f"by_category/{name}"] = lambda r, c=category: r.get("category") == c
        required = QUALITY_FIELDS
    elif data.get("protocol") == 1 and data.get("benchmark") == "LongMemEval-S retrieval coverage (session-level evidence)":
        predicates = {"all_instances": lambda r: True,
                      "development": lambda r: r.get("split") == "development",
                      "held_out": lambda r: r.get("split") == "held_out"}
        required = QUALITY_FIELDS - {"scorable", "no_gold_questions", "partially_or_unresolved_questions", "candidate_any_gold_rate", "mrr", "ndcg"}
    else:
        return ["unsupported aggregate summary protocol"]
    errors = []
    for config in sorted(expected):
        rows = [r for r in data["rows"] if f"{r.get('mode')}@{r.get('budget')}" == config]
        for cohort, predicate in predicates.items():
            cohort_rows = [r for r in rows if predicate(r)]
            count = len(cohort_rows)
            leaf = summaries[config]
            present = True
            for part in cohort.split("/"):
                if not isinstance(leaf, dict) or part not in leaf:
                    present = False
                    break
                leaf = leaf[part]
            # LME emits null only for a recorded empty cohort.
            if present and data.get("protocol") == 1 and count == 0 and leaf is None:
                continue
            if not present or not isinstance(leaf, dict) or not required.issubset(leaf):
                errors.append(f"{config}/{cohort}: missing quality fields")
                continue
            if type(leaf["questions"]) is not int or leaf["questions"] != count:
                errors.append(f"{config}/{cohort}: row denominator mismatch")
            if any(type(r.get("hits")) is not int or r["hits"] < 0 for r in cohort_rows):
                errors.append(f"{config}/{cohort}: invalid row hits for count binding")
                continue
            if data.get("protocol") == 2:
                if any(type(r.get("evidence_count")) is not int or r["evidence_count"] < 0
                       or type(r.get("fully_resolved")) is not bool for r in cohort_rows):
                    errors.append(f"{config}/{cohort}: invalid row scoring fields for count binding")
                    continue
                scored = [r for r in cohort_rows if is_scorable(r)]
                expected_counts = {
                    "questions": count, "scorable": len(scored),
                    "no_gold_questions": sum(r["evidence_count"] == 0 for r in cohort_rows),
                    "partially_or_unresolved_questions": sum(r["evidence_count"] > 0 and not r["fully_resolved"] for r in cohort_rows),
                    "any_gold_hits": sum(r["hits"] > 0 for r in scored),
                }
            else:
                scored = cohort_rows
                expected_counts = {"questions": count, "any_gold_hits": sum(r["hits"] > 0 for r in scored)}
            for field, expected_count in expected_counts.items():
                if type(leaf[field]) is not int or leaf[field] != expected_count:
                    errors.append(f"{config}/{cohort}/{field}: canonical row count mismatch")
            expected_rate = expected_counts["any_gold_hits"] / len(scored) if scored else None
            if leaf["any_gold_hit_rate"] != expected_rate:
                errors.append(f"{config}/{cohort}/any_gold_hit_rate: count/rate mismatch")
            for field in required:
                value = leaf[field]
                denominator = count if field in ("empty_context_rate", "mean_budget_used") or data.get("protocol") == 1 else leaf.get("scorable", 0)
                count_field = field in {"questions", "scorable", "no_gold_questions", "partially_or_unresolved_questions", "any_gold_hits"}
                if value is None and (count_field or denominator != 0):
                    errors.append(f"{config}/{cohort}/{field}: missing numeric metric")
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        errors.append(f"{config}/{cohort}/{field}: invalid numeric metric")
                    elif count_field and (type(value) is not int or not 0 <= value <= count):
                        errors.append(f"{config}/{cohort}/{field}: invalid count range")
                    elif not count_field and field != "mean_budget_used" and not 0 <= value <= 1:
                        errors.append(f"{config}/{cohort}/{field}: invalid normalized range")
                    elif field == "mean_budget_used" and value < 0:
                        errors.append(f"{config}/{cohort}/{field}: negative budget use")
    if not data["rows"]:
        errors.append("no measured rows")
    return errors


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
    row_errors_cpu, row_errors_gpu = strict_row_coverage_errors(cpu), strict_row_coverage_errors(gpu)
    top_cpu, top_gpu = top_level_coverage_errors(cpu), top_level_coverage_errors(gpu)
    if top_cpu or top_gpu:
        structural = True
        record({"kind": "top_level_identity_unavailable", "cpu": top_cpu, "gpu": top_gpu})
    grid_cpu, grid_gpu = grid_cohort_errors(cpu), grid_cohort_errors(gpu)
    if grid_cpu or grid_gpu:
        structural = True
        record({"kind": "grid_cohort_unavailable", "cpu": grid_cpu, "gpu": grid_gpu})
    identity_complete = not grid_cpu and not grid_gpu and not top_cpu and not top_gpu and missing_cpu == 0 and missing_gpu == 0 and not row_errors_cpu and not row_errors_gpu
    if not identity_complete:
        record({"kind": "selection_identity_unavailable",
                "cpu_rows_missing_selected_ids": missing_cpu, "gpu_rows_missing_selected_ids": missing_gpu,
                "cpu_row_coverage_errors": row_errors_cpu, "gpu_row_coverage_errors": row_errors_gpu})
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
        changed_fields = set()
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
                    changed_fields.add(field)
                    record({"kind": "row_field", "row": repr(key), "field": field, "cpu": a, "gpu": b})
            if isinstance(left.get("selected_ids"), list) and isinstance(right.get("selected_ids"), list):
                selection_set = set(left["selected_ids"]) != set(right["selected_ids"])
                rank_only = not selection_set and changed_fields == {"selected_ranked_ids"}
                if cpu.get("protocol") == gpu.get("protocol") == 1 and not selection_set:
                    ls, rs = left.get("selected_sources"), right.get("selected_sources")
                    rank_only = (isinstance(ls, list) and isinstance(rs, list)
                                 and dict(zip(left["selected_ids"], ls)) == dict(zip(right["selected_ids"], rs))
                                 and "selected_ids" in changed_fields
                                 and changed_fields <= {"selected_ids", "selected_sources"})
        if changed:
            cohort = "main_categories_1_to_4" if str(row.get("category")) in ("1", "2", "3", "4") else ("diagnostic_category_5" if str(row.get("category")) == "5" else "other")
            increments = {"mismatching_rows": 1, "selection_set_rows": int(selection_set), "rank_only_rows": int(rank_only),
                          "other_semantic_rows": int(not selection_set and not rank_only)}
            counts.update(increments)
            counts[cohort] += 1
            label = f"{row.get('mode')}@{row.get('budget')}/category={row.get('category')}"
            breakdown.setdefault(label, Counter()).update(increments)
    cq, gq = quality_projection(cpu.get("summaries", {})), quality_projection(gpu.get("summaries", {}))
    coverage_cpu, coverage_gpu = summary_coverage_errors(cpu), summary_coverage_errors(gpu)
    aggregate_diff = []
    for key in sorted(set(cq) | set(gq)):
        a, b = cq.get(key), gq.get(key)
        if (isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool)
            and math.isfinite(float(a)) and math.isfinite(float(b))):
            max_abs_diff = max(max_abs_diff, abs(float(a) - float(b)))
        if key not in cq or key not in gq or not same(cq.get(key), gq.get(key), float_tol):
            item = {"kind": "aggregate_metric", "field": "/".join(key), "cpu": cq.get(key), "gpu": gq.get(key)}
            aggregate_diff.append(item)
            record(item)
    aggregate_available = not coverage_cpu and not coverage_gpu
    strict = identity_complete and total == 0
    return {
        "kind": "thm-hardware-semantic-parity",
        "identity_complete": identity_complete,
        "top_level_coverage_errors": {"cpu": top_cpu, "gpu": top_gpu},
        "grid_cohort_errors": {"cpu": grid_cpu, "gpu": grid_gpu},
        "equivalent": strict, "strict_semantic_equivalent": strict,
        "aggregate_semantic_metrics_available": aggregate_available,
        "aggregate_summary_coverage_errors": {"cpu": coverage_cpu, "gpu": coverage_gpu},
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
        "other_semantic_mismatch_row_count": counts["other_semantic_rows"],
        "strict_row_coverage_errors": {"cpu": row_errors_cpu, "gpu": row_errors_gpu},
        "main_category_mismatch_row_count": counts["main_categories_1_to_4"],
        "diagnostic_mismatch_row_count": counts["diagnostic_category_5"],
        "other_category_mismatch_row_count": counts["other"],
        "mismatch_counts_by_field": dict(sorted(fields.items())),
        "mismatch_rows_by_mode_budget_category": {k: dict(v) for k, v in sorted(breakdown.items())},
        "excluded_from_parity": ["timing_ms", "query_embedding_ms", "build/index seconds", "environment strings", "wall-clock throughput"],
        "interpretation": "Strict parity includes selected IDs and ranked order across all rows, including category 5. Aggregate parity compares only explicit retrieval-quality summary fields. Rank-only requires ordering to be the sole semantic drift; mixed changes are other-semantic rows unless the selected set differs. Protocol 2 requires ranked IDs; LME requires ordered IDs with aligned source identities. Missing summaries do not establish aggregate parity.",
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

    require_new_output(args.output)
    cpu, cpu_digest = load(Path(args.cpu))
    gpu, gpu_digest = load(Path(args.gpu))
    receipt = compare(cpu, gpu, float_tol=args.float_tol, max_mismatches=args.max_mismatches)
    receipt["source_artifacts"] = {
        "cpu": {"file": Path(args.cpu).name, "sha256": cpu_digest},
        "gpu": {"file": Path(args.gpu).name, "sha256": gpu_digest},
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_new_text(out, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(
        f"wrote {out}: equivalent={receipt['equivalent']} "
        f"identity_complete={receipt['identity_complete']}"
    )
    raise SystemExit(0 if receipt["equivalent"] else 1)


if __name__ == "__main__":
    main()
