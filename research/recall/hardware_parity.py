#!/usr/bin/env python3
"""Compare CPU/GPU THM retrieval artifacts for deterministic semantic parity.

Timing, environment strings and embedding throughput are intentionally excluded.
The comparator checks dataset/protocol identity plus per-query retrieval outcomes.
It exits nonzero on any semantic mismatch and writes a machine-readable receipt.
"""
from __future__ import annotations

import argparse
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
    "selected_count", "selected_ids", "selected_ranked_ids",
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


def compare(cpu: dict, gpu: dict, *, float_tol: float = 0.0, max_mismatches: int = 50) -> dict:
    mismatches = []
    max_abs_diff = 0.0

    for field in TOP_LEVEL_IDENTITY:
        if field in cpu or field in gpu:
            if cpu.get(field) != gpu.get(field):
                mismatches.append({
                    "kind": "top_level_identity",
                    "field": field,
                    "cpu": cpu.get(field),
                    "gpu": gpu.get(field),
                })

    if cpu.get("corpus_fingerprints") != gpu.get("corpus_fingerprints"):
        mismatches.append({"kind": "corpus_fingerprints"})

    cpu_rows, gpu_rows = cpu["rows"], gpu["rows"]
    if len(cpu_rows) != len(gpu_rows):
        mismatches.append({
            "kind": "row_count",
            "cpu": len(cpu_rows),
            "gpu": len(gpu_rows),
        })

    cpu_map = {row_key(row, i): row for i, row in enumerate(cpu_rows)}
    gpu_map = {row_key(row, i): row for i, row in enumerate(gpu_rows)}
    if len(cpu_map) != len(cpu_rows) or len(gpu_map) != len(gpu_rows):
        mismatches.append({"kind": "duplicate_row_identity"})

    keys = sorted(set(cpu_map) | set(gpu_map), key=repr)
    compared = 0
    for key in keys:
        left, right = cpu_map.get(key), gpu_map.get(key)
        if left is None or right is None:
            if len(mismatches) < max_mismatches:
                mismatches.append({
                    "kind": "missing_row",
                    "row": repr(key),
                    "cpu_present": left is not None,
                    "gpu_present": right is not None,
                })
            continue
        compared += 1
        for field in SEMANTIC_FIELDS:
            if field not in left and field not in right:
                continue
            a, b = left.get(field), right.get(field)
            if (
                isinstance(a, (int, float)) and not isinstance(a, bool)
                and isinstance(b, (int, float)) and not isinstance(b, bool)
                and math.isfinite(float(a)) and math.isfinite(float(b))
            ):
                max_abs_diff = max(max_abs_diff, abs(float(a) - float(b)))
            if not same(a, b, float_tol) and len(mismatches) < max_mismatches:
                mismatches.append({
                    "kind": "row_field",
                    "row": repr(key),
                    "field": field,
                    "cpu": a,
                    "gpu": b,
                })

    return {
        "kind": "thm-hardware-semantic-parity",
        "equivalent": not mismatches,
        "rows_cpu": len(cpu_rows),
        "rows_gpu": len(gpu_rows),
        "rows_compared": compared,
        "float_abs_tolerance": float_tol,
        "max_semantic_numeric_abs_diff": max_abs_diff,
        "mismatch_count_capped": len(mismatches),
        "mismatches": mismatches,
        "excluded_from_parity": [
            "timing_ms", "query_embedding_ms", "build/index seconds",
            "environment strings", "wall-clock throughput",
        ],
        "interpretation": (
            "equivalent=true means CPU and GPU produced the same checked retrieval "
            "semantics for this artifact pair. It does not mean equal latency or "
            "bit-identical embedding vectors."
        ),
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
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: equivalent={receipt['equivalent']}")
    raise SystemExit(0 if receipt["equivalent"] else 1)


if __name__ == "__main__":
    main()
