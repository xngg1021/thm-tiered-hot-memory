#!/usr/bin/env python3
"""LoCoMo retrieval-only comparison. No generation, judge or benchmark-label index.

Download data yourself from the pinned upstream link in README. Results contain
IDs/metrics, never original conversation text. This measures evidence coverage,
not answer accuracy, and is not the user's unavailable original experiment.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from thm.retrieval import SearchIndex, SentenceEncoder, TokenCounter
from thm.sources import locomo_documents

DATASET_COMMIT = '3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376'
CATEGORY = {1: 'single_hop', 2: 'temporal', 3: 'open_domain', 4: 'multi_hop', 5: 'adversarial'}


def evidence_ids(value):
    if not isinstance(value, list):
        raise ValueError('evidence must be a list')
    found, malformed = set(), []
    for item in value:
        if not isinstance(item, str):
            malformed.append(str(type(item)))
            continue
        matches = re.findall(r'D\s*(\d+)\s*:\s*(\d+)', item)
        found.update(f'D{int(s)}:{int(t)}' for s, t in matches)
        remainder = re.sub(r'D\s*\d+\s*:\s*\d+', '', item)
        if not matches or re.sub(r'[\s,;\[\]()]+', '', remainder):
            malformed.append(item)
    return found, malformed


def percentile(values, q):
    if not values: return None
    values = sorted(values)
    at = (len(values)-1)*q
    low, high = math.floor(at), math.ceil(at)
    return values[low]+(values[high]-values[low])*(at-low)


def aggregate(rows):
    scored = [r for r in rows if r['evidence_count'] and r['fully_resolved']]
    denominator = len(scored)
    return {'questions': len(rows), 'scorable': denominator,
            'no_gold_questions': sum(r['evidence_count']==0 for r in rows),
            'partially_or_unresolved_questions': sum(bool(r['evidence_count']) and not r['fully_resolved'] for r in rows),
            'any_gold_hits': sum(r['hits'] > 0 for r in scored),
            'any_gold_hit_rate': sum(r['hits']>0 for r in scored)/denominator if denominator else None,
            'all_gold_hit_rate': sum(r['hits']==r['evidence_count'] for r in scored)/denominator if denominator else None,
            'macro_evidence_recall': statistics.mean(r['hits']/r['evidence_count'] for r in scored) if scored else None,
            'micro_evidence_recall': sum(r['hits'] for r in scored)/sum(r['evidence_count'] for r in scored) if scored else None,
            'candidate_any_gold_rate': sum(r['candidate_hits']>0 for r in scored)/denominator if denominator else None,
            'empty_context_rate': statistics.mean(r['selected_count']==0 for r in rows) if rows else None,
            'mean_budget_used': statistics.mean(r['budget_used'] for r in rows) if rows else None,
            'latency_ms': {'p50': percentile([r['total_ms'] for r in rows], .5),
                           'p95': percentile([r['total_ms'] for r in rows], .95),
                           'mean': statistics.mean(r['total_ms'] for r in rows) if rows else None},
            'query_embedding_ms_mean': statistics.mean(r['query_embedding_ms'] for r in rows) if rows else None}


def run(dataset, counter, modes, budgets, *, model_path=None, model_id=None, neighbors=0):
    encoder = SentenceEncoder(model_path, model_id) if model_path else None
    if any(m in ('dense','hybrid') for m in modes) and not encoder:
        raise ValueError('local model required for requested dense run')
    all_rows, builds, generations = [], [], {}
    ids = sorted(str(s['sample_id']) for s in dataset)
    dev_ids = set(ids[:2])  # No parameter is selected using QA outcomes in this script.
    with tempfile.TemporaryDirectory() as temp:
        index = SearchIndex(Path(temp)/'recall.sqlite', counter)
        try:
            for sample in dataset:
                scope = str(sample['sample_id'])
                documents = list(locomo_documents(sample))
                start = time.perf_counter()
                metadata = index.replace_scope(scope, documents)
                generations[scope] = metadata['generation']
                build = {'scope': scope, 'documents': len(documents), 'index_seconds': time.perf_counter()-start}
                if encoder:
                    build['embedding'] = index.embed(scope, encoder, model_id)
                builds.append(build)
                known = {d.id for d in documents}
                for mode in modes:
                    for budget in budgets:
                        for position, qa in enumerate(sample['qa']):
                            gold, malformed = evidence_ids(qa.get('evidence', []))
                            # Only the question is passed. No gold/answer/category information enters search.
                            out = index.search(scope, qa['question'], mode=mode, budget=budget,
                                               neighbor_turns=neighbors, encoder=encoder, model_id=model_id)
                            selected = {x['id'] for x in out['selected'] if x['complete']}
                            all_rows.append({'scope': scope, 'question_index': position,
                                'split': 'development' if scope in dev_ids else 'held_out',
                                'mode': mode, 'budget': budget, 'category': int(qa['category']),
                                'evidence_count': len(gold), 'resolved_count': len(gold & known),
                                'fully_resolved': not malformed and gold <= known,
                                'hits': len(gold & selected), 'candidate_hits': len(gold & set(out['ranked_ids'])),
                                'selected_count': len(selected), 'selected_ids': sorted(selected),
                                'budget_used': out['budget_used'],
                                'total_ms': out['timing_ms']['total'],
                                'query_embedding_ms': out['timing_ms']['query_embedding'],
                                'malformed_evidence': bool(malformed)})
                print('BENCH_SCOPE_DONE', scope, len(sample['qa']), flush=True)
        finally:
            index.close()
    summaries = {}
    for mode in modes:
        for budget in budgets:
            rows = [r for r in all_rows if r['mode']==mode and r['budget']==budget]
            summaries[f'{mode}@{budget}'] = {
                'main_categories_1_to_4': aggregate([r for r in rows if r['category']!=5]),
                'conversational_categories_1_2_4': aggregate([r for r in rows if r['category'] in (1,2,4)]),
                'all_categories_diagnostic_only': aggregate(rows),
                'development': aggregate([r for r in rows if r['split']=='development' and r['category']!=5]),
                'held_out': aggregate([r for r in rows if r['split']=='held_out' and r['category']!=5]),
                'by_category': {CATEGORY[c]: aggregate([r for r in rows if r['category']==c]) for c in CATEGORY}}
    return {'protocol': 1, 'counter': counter.name, 'modes': modes, 'budgets': budgets,
            'neighbor_turns': neighbors, 'summaries': summaries, 'builds': builds,
            'corpus_fingerprints': generations, 'rows': all_rows,
            'generation_calls': 0, 'judge_calls': 0,
            'model_id': model_id, 'development_conversations': sorted(dev_ids),
            'notes': ['Retrieval coverage is not answer accuracy.',
                      'Adversarial-category evidence is diagnostic, not a correct-answer target.',
                      'All-gold counts require every reference resolved; partial mappings are reported separately.',
                      'No QA answer, gold evidence, category, supplied observation or summary is indexed.',
                      'No LoCoMo QA ordering is used to tune decay.',
                      'The original local script/results were unavailable: this is a new protocol, not a replication.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--counter', default='utf8_bytes')
    parser.add_argument('--modes', nargs='+', default=['literal','sparse'])
    parser.add_argument('--budgets', nargs='+', type=int, default=[600])
    parser.add_argument('--model-path')
    parser.add_argument('--model-id')
    parser.add_argument('--neighbors', type=int, default=0)
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    result = run(dataset, TokenCounter(args.counter), args.modes, args.budgets,
                 model_path=args.model_path, model_id=args.model_id, neighbors=args.neighbors)
    result['dataset_sha256'] = hashlib.sha256(raw).hexdigest()
    result['dataset_upstream_commit'] = DATASET_COMMIT
    result['environment'] = {'python': sys.version.split()[0], 'os': platform.platform(),
                             'sqlite': sqlite3.sqlite_version}
    result['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), *Path(__file__).resolve().parents[2].joinpath('thm').glob('*.py')]}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    summary = {k: v for k, v in result.items() if k != 'rows'}
    print('THM_BENCHMARK_SUMMARY_BEGIN')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('THM_BENCHMARK_SUMMARY_END')


if __name__ == '__main__':
    main()
