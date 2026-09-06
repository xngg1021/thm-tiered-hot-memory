#!/usr/bin/env python3
"""Protocol-2 sparse rerank/packing ablation with development-only selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.recall.benchmark import DATASET_COMMIT, DATASET_SHA256, aggregate, evidence_ids
from thm.rerank import RerankConfig, pack_rows, rerank_rows
from thm.retrieval import SearchIndex, TokenCounter
from thm.sources import locomo_documents


WEIGHTS = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50)


def config_for(weight: float) -> RerankConfig:
    return RerankConfig(
        coverage_weight=weight,
        all_focus_bonus=0.15,
        exact_bonus=0.10,
        metadata_match_factor=0.25,
        rank_exponent=0.5,
    )


def row_metric(scope, qpos, split, qa, known, selected_order, ranked_ids, budget_used, elapsed_ms):
    gold, malformed = evidence_ids(qa.get("evidence", []))
    selected = set(selected_order)
    positions = [i for i, value in enumerate(selected_order, 1) if value in gold]
    candidate_positions = [i for i, value in enumerate(ranked_ids, 1) if value in gold]
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(gold), len(selected_order)) + 1))
    return {
        "scope": scope,
        "question_index": qpos,
        "split": split,
        "category": int(qa["category"]),
        "evidence_count": len(gold),
        "resolved_count": len(gold & known),
        "fully_resolved": not malformed and gold <= known,
        "hits": len(gold & selected),
        "candidate_hits": len(gold & set(ranked_ids)),
        "selected_count": len(selected),
        "selected_ranked_ids": selected_order,
        "reciprocal_rank": 1 / positions[0] if positions else 0.0,
        "candidate_reciprocal_rank": 1 / candidate_positions[0] if candidate_positions else 0.0,
        "ndcg": sum(1 / math.log2(i + 1) for i in positions) / ideal if ideal else 0.0,
        "budget_used": budget_used,
        "total_ms": elapsed_ms,
        "query_embedding_ms": 0.0,
        "malformed_evidence": bool(malformed),
        "result_cache_hit": False,
    }


def objective(summary):
    # Development-only lexicographic selection. Latency is a tie-break, never a
    # reason to accept lower evidence coverage.
    return (
        summary["any_gold_hit_rate"] or 0,
        summary["all_gold_hit_rate"] or 0,
        summary["macro_evidence_recall"] or 0,
        summary["mrr"] or 0,
        -(summary["latency_ms"]["mean"] or 0),
    )


def run(dataset, counter, budget):
    if not isinstance(dataset, list) or not dataset:
        raise ValueError("nonempty conversation list required")
    sample_ids = sorted(str(sample["sample_id"]) for sample in dataset)
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("duplicate conversation IDs")
    dev_ids = set(sample_ids[:2])
    strategy_rows = {"baseline": [], "compact": []}
    for weight in WEIGHTS:
        strategy_rows[f"rerank-{weight:.2f}"] = []

    with tempfile.TemporaryDirectory() as temp:
        index = None
        try:
            for sample_number, sample in enumerate(dataset):
                if index is not None:
                    index.close()
                index = SearchIndex(Path(temp) / f"conversation-{sample_number}.sqlite", counter)
                scope = str(sample["sample_id"])
                documents = list(locomo_documents(sample))
                index.replace_scope(scope, documents)
                known = {doc.id for doc in documents}
                rows_by_id = {row["id"]: row for row in index.rows(scope)}
                split = "development" if scope in dev_ids else "held_out"

                for qpos, qa in enumerate(sample["qa"]):
                    if type(qa.get("category")) is not int or qa["category"] not in (1, 2, 3, 4, 5):
                        raise ValueError("unsupported question category")
                    query = qa["question"]
                    base = index.search(scope, query, mode="sparse", budget=budget)
                    ranked = [rows_by_id[row_id] for row_id in base["ranked_ids"]]
                    base_selected = [item["id"] for item in base["selected"] if item["complete"]]
                    strategy_rows["baseline"].append(
                        row_metric(scope, qpos, split, qa, known, base_selected, base["ranked_ids"],
                                   base["budget_used"], base["timing_ms"]["total"])
                    )

                    # Prove that the helper reproduces the current whole-source
                    # serializer exactly before using the compact variant.
                    legacy = pack_rows(ranked, budget=budget, counter=counter, compact_headers=False)
                    legacy_ids = [item["id"] for item in legacy["selected"]]
                    if legacy_ids != base_selected or legacy["budget_used"] != base["budget_used"]:
                        raise AssertionError("rerank pack helper does not reproduce baseline packing")

                    started = time.perf_counter()
                    compact = pack_rows(ranked, budget=budget, counter=counter, compact_headers=True)
                    compact_ms = (time.perf_counter() - started) * 1000
                    compact_ids = [item["id"] for item in compact["selected"]]
                    strategy_rows["compact"].append(
                        row_metric(scope, qpos, split, qa, known, compact_ids, base["ranked_ids"],
                                   compact["budget_used"], compact_ms)
                    )

                    for weight in WEIGHTS:
                        name = f"rerank-{weight:.2f}"
                        started = time.perf_counter()
                        reranked = rerank_rows(query, ranked, config_for(weight))
                        packed = pack_rows(reranked, budget=budget, counter=counter, compact_headers=True)
                        elapsed = (time.perf_counter() - started) * 1000
                        selected = [item["id"] for item in packed["selected"]]
                        strategy_rows[name].append(
                            row_metric(scope, qpos, split, qa, known, selected,
                                       [row["id"] for row in reranked], packed["budget_used"], elapsed)
                        )
                print("RERANK_SCOPE_DONE", scope, len(sample["qa"]), flush=True)
        finally:
            if index is not None:
                index.close()

    def summary_for(name, split):
        rows = [row for row in strategy_rows[name]
                if row["split"] == split and row["category"] != 5]
        return aggregate(rows)

    development = {name: summary_for(name, "development") for name in strategy_rows}
    candidates = [name for name in strategy_rows if name.startswith("rerank-")]
    selected = max(candidates, key=lambda name: (objective(development[name]), name))
    held_out = {
        "baseline": summary_for("baseline", "held_out"),
        "compact": summary_for("compact", "held_out"),
        selected: summary_for(selected, "held_out"),
    }
    all_main = {
        name: aggregate([row for row in strategy_rows[name] if row["category"] != 5])
        for name in ("baseline", "compact", selected)
    }
    return {
        "protocol": "2-rerank-ablation-v1",
        "budget": budget,
        "counter": counter.name,
        "development_conversations": sorted(dev_ids),
        "selection_rule": "max dev any-gold, all-gold, macro-recall, MRR; latency tie-break",
        "weights": list(WEIGHTS),
        "selected_strategy": selected,
        "development": development,
        "held_out": held_out,
        "all_main_diagnostic": all_main,
        "candidate_source": "existing sparse ranked_ids only",
        "generation_calls": 0,
        "judge_calls": 0,
        "label_inputs_to_reranker": 0,
        "notes": [
            "QA evidence IDs are used only after retrieval for evaluation.",
            "Only the two disclosed development conversations select the weight.",
            "Held-out results do not feed parameter selection.",
            "Compact packing removes JSON whitespace but preserves id/speaker/date fields and whole source text.",
            "Rerank latency here excludes the already-completed base sparse candidate retrieval.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--counter", default="cl100k_base")
    parser.add_argument("--budget", type=int, default=600)
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    result = run(dataset, TokenCounter(args.counter), args.budget)
    result["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    result["dataset_upstream_commit"] = DATASET_COMMIT if result["dataset_sha256"] == DATASET_SHA256 else None
    result["dataset_matches_pinned_reference"] = result["dataset_sha256"] == DATASET_SHA256
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("THM_RERANK_SUMMARY_BEGIN")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("THM_RERANK_SUMMARY_END")


if __name__ == "__main__":
    main()
