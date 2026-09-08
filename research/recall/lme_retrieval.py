#!/usr/bin/env python3
"""LongMemEval-S retrieval-only coverage runner (zero LLM, zero judge).

Evidence = answer_session_ids (official gold). Retrieval is message-level:
each haystack message becomes a document whose id encodes session#index.
A gold session counts as HIT when at least one of its messages enters the
packed context. Metrics mirror the LoCoMo runner: any-gold rate and macro
evidence recall over sessions. No answer is generated.

Dataset: xiaowu0162/longmemeval `longmemeval_s` (HF, xet). Download with
huggingface_hub.hf_hub_download(repo_type='dataset'). License: CC BY-NC 4.0
family per the LongMemEval release; not redistributed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thm.retrieval import Document, SearchIndex, SentenceEncoder, TokenCounter
from research.evidence_io import require_new_output, write_new_text


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    at = (len(values) - 1) * q
    low, high = math.floor(at), math.ceil(at)
    return values[low] + (values[high] - values[low]) * (at - low)


def aggregate(rows):
    denominator = len(rows)
    if not rows:
        return None
    return {
        "questions": denominator,
        "any_gold_hits": sum(r["hits"] > 0 for r in rows),
        "any_gold_hit_rate": sum(r["hits"] > 0 for r in rows) / denominator,
        "all_gold_hit_rate": sum(r["hits"] == r["gold_sessions"] for r in rows) / denominator,
        "macro_evidence_recall": statistics.mean(r["hits"] / r["gold_sessions"] for r in rows),
        "micro_evidence_recall": sum(r["hits"] for r in rows) / sum(r["gold_sessions"] for r in rows),
        "empty_context_rate": statistics.mean(r.get("packed_selected_count",r["selected_count"]) == 0 for r in rows),
        "mean_budget_used": statistics.mean(r["budget_used"] for r in rows),
        "latency_ms": {
            "p50": percentile([r["total_ms"] for r in rows], 0.5),
            "p95": percentile([r["total_ms"] for r in rows], 0.95),
            "mean": statistics.mean(r["total_ms"] for r in rows),
        },
    }


def messages_of(instance):
    """Yield (document_id, text, session_id, role) for every haystack message.

    document_id encodes session occurrence index to stay unique even when the
    dataset repeats a haystack session id."""
    for session_idx, (session_id, session) in enumerate(
        zip(instance["haystack_session_ids"], instance["haystack_sessions"])
    ):
        for msg_idx, msg in enumerate(session):
            role = str(msg.get("role", "")).strip()
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            text = f"{role}: {content}" if role else content
            yield f"{session_id}~{session_idx}#{msg_idx}", text, session_id, role


def run(dataset, counter, modes, budgets, *, model_path=None, model_id=None, limit=None,
        threads=None, device='cpu', batch_size=64, execution_config=None, cache_path=None):
    if not isinstance(dataset, list) or not dataset:
        raise ValueError("nonempty instance list required")
    if not modes or len(set(modes))!=len(modes) or any(m not in ('literal','sparse','dense','hybrid') for m in modes):raise ValueError('unique supported modes required')
    if not budgets or len(set(budgets))!=len(budgets) or any(type(b) is not int or not 0<=b<=32768 for b in budgets):raise ValueError('unique valid budgets required')
    if limit is not None and (type(limit) is not int or limit<=0):raise ValueError('positive integer limit required')
    if limit:
        dataset = dataset[:limit]
    ids = [str(x["question_id"]) for x in dataset]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids")
    from thm.runtime.research import Execution
    execution=Execution(execution_config,model_path,model_id,cache_path) if execution_config else None
    encoder=execution.encoder if execution else SentenceEncoder(model_path,model_id,threads=threads,device=device,batch_size=batch_size) if model_path else None
    if execution and any(b>0 for b in budgets) and any(m in ('dense','hybrid') for m in modes):execution.preencode([instance['question'] for instance in dataset])
    if any(m in ("dense", "hybrid") for m in modes) and not encoder:
        raise ValueError("local model required for dense/hybrid")

    all_rows, builds, generations = [], [], {}
    dev_ids = set(sorted(ids)[:3])
    with tempfile.TemporaryDirectory() as temp:
        index = SearchIndex(Path(temp) / "lme.sqlite", counter)
        try:
            for number, instance in enumerate(dataset):
                index.close()
                index = SearchIndex(Path(temp) / f"lme-{number}.sqlite", counter)
                scope = str(instance["question_id"])
                docs = []
                for doc_id, text, session_id, role in messages_of(instance):
                    docs.append(Document(doc_id, scope, doc_id, 0, text,
                                         speaker=role, timestamp='', source=session_id))
                gold = set(instance["answer_session_ids"])
                known = {d.source for d in docs}
                start = time.perf_counter()
                metadata = index.replace_scope(scope, docs)
                generations[scope] = metadata["generation"]
                build = {"scope": scope, "documents": len(docs),
                         "haystack_sessions": len(instance["haystack_session_ids"]),
                         "gold_sessions": len(gold),
                         "index_seconds": time.perf_counter() - start}
                if encoder and any(m in ('dense','hybrid') for m in modes) and any(b>0 for b in budgets):
                    build["embedding"] = execution.embed(index,scope) if execution else index.embed(scope, encoder, model_id)
                builds.append(build)

                for mode in modes:
                    for budget in budgets:
                        out = execution.search_many(index,scope,[instance["question"]],mode=mode,budget=budget)[0] if execution else index.search(scope, instance["question"], mode=mode,
                                           budget=budget, encoder=encoder, model_id=model_id)
                        selected_rows = [x for x in out["selected"] if x["complete"]]
                        selected_order = [x["id"] for x in selected_rows]
                        selected_sources = [x.get("source") for x in selected_rows]
                        selected = set(selected_order)
                        hit_sessions = {
                            row.get("source") for row in selected_rows
                            if row.get("source") in gold
                        }
                        positions = [
                            i for i, row in enumerate(selected_rows, 1)
                            if row.get("source") in gold
                        ]
                        all_rows.append({
                            "scope": scope, "split": "development" if scope in dev_ids else "held_out",
                            "mode": mode, "budget": budget,
                            "gold_sessions": len(gold),
                            "resolved_gold": len(gold & known),
                            "hits": len(hit_sessions),
                            "candidate_hits": None,
                            "selected_count": len(selected), "complete_selected_count":len(selected),
                            "packed_selected_count":len(out["selected"]), "packed_selections":[{k:x.get(k) for k in ("id","complete","span_start","span_end")} for x in out["selected"]],
                            "selected_ids": selected_order,
                            "selected_sources": selected_sources,
                            "reciprocal_rank": 1 / positions[0] if positions else 0.0,
                            "runtime_diagnostics":out.get("runtime_diagnostics"),"timing_breakdown_ms":out["timing_ms"],'timing_kind':out.get('timing_kind','sequential'),'batch_receipt':out.get('batch_receipt'),
                            "parent_locator_ids":out.get("parent_locator_ids",[]),"budget_used": out["budget_used"],
                            "total_ms": out["timing_ms"].get("amortized_total",out["timing_ms"]["total"]),
                            "query_embedding_ms": out["timing_ms"]["query_embedding"],
                        })
                print("LME_SCOPE_DONE", scope, len(instance["haystack_session_ids"]), flush=True)
        finally:
            runtime_receipt=execution.receipt() if execution else None
            index.close()
            if execution:execution.close()
            elif encoder and hasattr(encoder,'close'):encoder.close()

    summaries = {}
    for mode in modes:
        for budget in budgets:
            rows = [r for r in all_rows if r["mode"] == mode and r["budget"] == budget]
            summaries[f"{mode}@{budget}"] = {
                "all_instances": aggregate(rows),
                "development": aggregate([r for r in rows if r["split"] == "development"]),
                "held_out": aggregate([r for r in rows if r["split"] == "held_out"]),
            }
    return {
        "benchmark": "LongMemEval-S retrieval coverage (session-level evidence)",
        "protocol": 1,"runtime":runtime_receipt, "counter": counter.name, "modes": modes, "budgets": budgets,
        "idf_scope": "one_database_per_instance",
        "summaries": summaries, "builds": builds,
        "corpus_fingerprints": generations, "rows": all_rows,
        "generation_calls": 0, "judge_calls": 0, "model_id": model_id,
        "development_instances": sorted(dev_ids),
        "notes": [
            "Retrieval coverage is not answer accuracy.",
            "Gold = official answer_session_ids; a session counts as hit when any of its messages is retrieved.",
            "No question type, answer text, or gold ids enter the index.",
            "selected_ids/source identities are emitted so CPU/GPU semantic parity can be verified on future runs.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--counter", default="cl100k_base")
    ap.add_argument("--modes", nargs="+", default=["literal", "sparse"])
    ap.add_argument("--budgets", nargs="+", type=int, default=[600])
    ap.add_argument("--model-path")
    ap.add_argument("--model-id")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=64)
    from thm.runtime.research import add_arguments,config_from_args
    add_arguments(ap)
    args = ap.parse_args()
    require_new_output(args.output)
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    result = run(dataset, TokenCounter(args.counter), args.modes, args.budgets,
                 model_path=args.model_path, model_id=args.model_id, limit=args.limit,
                 threads=args.threads, device=args.device, batch_size=args.batch_size,execution_config=config_from_args(args),cache_path=args.embedding_cache)
    result["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    result["environment"] = {"python": sys.version.split()[0], "os": platform.platform(),
                             "sqlite": sqlite3.sqlite_version}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_new_text(out, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    summary = {k: v for k, v in result.items() if k != "rows"}
    print("LME_BENCHMARK_SUMMARY_BEGIN")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("LME_BENCHMARK_SUMMARY_END")


if __name__ == "__main__":
    main()
