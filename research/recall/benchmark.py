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
from research.evidence_io import require_new_output, write_new_text
from thm.sources import locomo_documents
from research.recall.scoring import is_scorable

DATASET_COMMIT = '3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376'
DATASET_SHA256 = '79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4'
CATEGORY = {1: 'multi_hop', 2: 'temporal', 3: 'open_domain', 4: 'single_hop', 5: 'adversarial'}


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
    scored = [r for r in rows if is_scorable(r)]
    denominator = len(scored)
    return {'questions': len(rows), 'scorable': denominator,
            'no_gold_questions': sum(r['evidence_count']==0 for r in rows),
            'partially_or_unresolved_questions': sum(bool(r['evidence_count']) and not r['fully_resolved'] for r in rows),
            'parent_locator_coverage':sum(r.get('parent_locator_hits',r['hits'])>0 for r in scored)/denominator if denominator else None,
            'conservative_complete_evidence_coverage':sum(r['hits']>0 for r in scored)/denominator if denominator else None,
            'any_gold_hits': sum(r['hits'] > 0 for r in scored),
            'any_gold_hit_rate': sum(r['hits']>0 for r in scored)/denominator if denominator else None,
            'all_gold_hit_rate': sum(r['hits']==r['evidence_count'] for r in scored)/denominator if denominator else None,
            'macro_evidence_recall': statistics.mean(r['hits']/r['evidence_count'] for r in scored) if scored else None,
            'micro_evidence_recall': sum(r['hits'] for r in scored)/sum(r['evidence_count'] for r in scored) if scored else None,
            'candidate_any_gold_rate': sum(r['candidate_hits']>0 for r in scored)/denominator if denominator else None,
            'empty_context_rate': statistics.mean(r.get('packed_selected_count',r['selected_count'])==0 for r in rows) if rows else None,
            'mean_budget_used': statistics.mean(r['budget_used'] for r in rows) if rows else None,
            'latency_ms': {'p50': percentile([r['total_ms'] for r in rows], .5),
                           'p95': percentile([r['total_ms'] for r in rows], .95),
                           'p99': percentile([r['total_ms'] for r in rows], .99),
                           'mean': statistics.mean(r['total_ms'] for r in rows) if rows else None},
            'mrr': statistics.mean(r['reciprocal_rank'] for r in scored) if scored and all('reciprocal_rank' in r for r in scored) else None,
            'ndcg': statistics.mean(r['ndcg'] for r in scored) if scored and all('ndcg' in r for r in scored) else None,
            'query_embedding_ms_mean': statistics.mean(r['query_embedding_ms'] for r in rows) if rows else None}


def run(dataset, counter, modes, budgets, *, model_path=None, model_id=None, neighbors=0,
        device='cpu', batch_size=64, execution_config=None, cache_path=None):
    if not isinstance(dataset, list) or not dataset:
        raise ValueError('nonempty conversation list required')
    sample_ids = [str(s['sample_id']) for s in dataset]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError('duplicate conversation IDs')
    if not modes or any(m not in ('literal','sparse','dense','hybrid') for m in modes) or len(set(modes)) != len(modes):
        raise ValueError('unique supported modes required')
    if not budgets or any(type(b) is not int or not 0 <= b <= 32768 for b in budgets) or len(set(budgets)) != len(budgets):
        raise ValueError('unique valid budgets required')
    from thm.runtime.research import Execution
    from contextlib import ExitStack
    with ExitStack() as resources:
        execution=Execution(execution_config,model_path,model_id,cache_path) if execution_config else None
        if execution:resources.callback(execution.close)
        encoder = execution.encoder if execution else SentenceEncoder(model_path, model_id, device=device,batch_size=batch_size) if model_path else None
        if not execution and encoder and hasattr(encoder,'close'):resources.callback(encoder.close)
        if any(m in ('dense','hybrid') for m in modes) and not encoder:
            raise ValueError('local model required for requested dense run')
        all_rows, builds, generations = [], [], {}
        ids = sorted(str(s['sample_id']) for s in dataset)
        dev_ids = set(ids[:2])  # No parameter is selected using QA outcomes in this script.
        with tempfile.TemporaryDirectory() as temp:
            index = SearchIndex(Path(temp)/'recall.sqlite', counter)
            try:
                for sample_number, sample in enumerate(dataset):
                    # FTS5 IDF statistics are table-wide. Separate databases keep
                    # unrelated conversations and dataset iteration order out of ranking.
                    index.close()
                    index = SearchIndex(Path(temp)/f'conversation-{sample_number}.sqlite', counter)
                    scope = str(sample['sample_id'])
                    documents = list(locomo_documents(sample))
                    start = time.perf_counter()
                    metadata = index.replace_scope(scope, documents)
                    generations[scope] = metadata['generation']
                    build = {'scope': scope, 'documents': len(documents), 'index_seconds': time.perf_counter()-start}
                    if encoder and any(m in ('dense','hybrid') for m in modes) and any(b>0 for b in budgets):
                        build['embedding'] = execution.embed(index,scope) if execution else index.embed(scope, encoder, model_id)
                    builds.append(build)
                    known = {d.id for d in documents}
                    for mode in modes:
                        for budget in budgets:
                            batch_results=execution.search_many(index,scope,[qa['question'] for qa in sample['qa']],mode=mode,budget=budget,neighbor_turns=neighbors) if execution else None
                            for position, qa in enumerate(sample['qa']):
                                if type(qa.get('category')) is not int or qa['category'] not in CATEGORY:
                                    raise ValueError('unsupported question category')
                                gold, malformed = evidence_ids(qa.get('evidence', []))
                                # Only the question is passed. No gold/answer/category information enters search.
                                out = batch_results[position] if batch_results is not None else index.search(scope, qa['question'], mode=mode, budget=budget,
                                                   neighbor_turns=neighbors, encoder=encoder, model_id=model_id)
                                selected_order = [x['id'] for x in out['selected'] if x['complete']]
                                selected = set(selected_order)
                                positions = [i for i, value in enumerate(selected_order, 1) if value in gold]
                                candidate_positions = [i for i, value in enumerate(out['ranked_ids'], 1) if value in gold]
                                ideal = sum(1/math.log2(i+1) for i in range(1, min(len(gold), len(selected_order))+1))
                                ndcg = sum(1/math.log2(i+1) for i in positions)/ideal if ideal else 0.0
                                all_rows.append({'scope': scope, 'question_index': position,
                                    'split': 'development' if scope in dev_ids else 'held_out',
                                    'mode': mode, 'budget': budget, 'category': int(qa['category']),
                                    'evidence_count': len(gold), 'resolved_count': len(gold & known),
                                    'fully_resolved': not malformed and gold <= known,
                                    'hits': len(gold & selected),'parent_locator_hits':len(gold & set(out.get('parent_locator_ids',selected))), 'candidate_hits': len(gold & set(out['ranked_ids'])),
                                    'selected_count': len(selected), 'complete_selected_count':len(selected),
                                    'packed_selected_count':len(out['selected']), 'packed_selections':[{k:x.get(k) for k in ('id','complete','span_start','span_end')} for x in out['selected']], 'selected_ids': sorted(selected),
                                    'selected_ranked_ids': selected_order,
                                    'reciprocal_rank': 1/positions[0] if positions else 0.0,
                                    'candidate_reciprocal_rank': 1/candidate_positions[0] if candidate_positions else 0.0,
                                    'ndcg': ndcg, 'result_cache_hit': out.get('result_cache_hit', False),
                                    'budget_used': out['budget_used'],
                                    'total_ms': out['timing_ms'].get('amortized_total',out['timing_ms']['total']),
                                    'query_embedding_ms': out['timing_ms']['query_embedding'],
                                    'runtime_diagnostics':out.get('runtime_diagnostics'),'timing_breakdown_ms':out['timing_ms'],'timing_kind':out.get('timing_kind','sequential'),'batch_receipt':out.get('batch_receipt'),
                                    'parent_locator_ids':out.get('parent_locator_ids',[]),'malformed_evidence': bool(malformed)})
                    print('BENCH_SCOPE_DONE', scope, len(sample['qa']), flush=True)
            finally:
                try:runtime_receipt=execution.receipt() if execution else None
                finally:index.close()
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
    return {'protocol': 2, 'runtime':runtime_receipt, 'counter': counter.name, 'modes': modes, 'budgets': budgets,
            'neighbor_turns': neighbors, 'idf_scope': 'one_database_per_conversation', 'summaries': summaries, 'builds': builds,
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
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--threads',type=int,default=1)
    from thm.runtime.research import add_arguments,config_from_args
    add_arguments(parser)
    args = parser.parse_args()
    require_new_output(args.output)
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    result = run(dataset, TokenCounter(args.counter), args.modes, args.budgets,
                 model_path=args.model_path, model_id=args.model_id, neighbors=args.neighbors,
                 device=args.device, batch_size=args.batch_size,execution_config=config_from_args(args),cache_path=args.embedding_cache)
    result['dataset_sha256'] = hashlib.sha256(raw).hexdigest()
    result['dataset_upstream_commit'] = DATASET_COMMIT if result['dataset_sha256'] == DATASET_SHA256 else None
    result['dataset_matches_pinned_reference'] = result['dataset_sha256'] == DATASET_SHA256
    result['environment'] = {'python': sys.version.split()[0], 'os': platform.platform(),
                             'sqlite': sqlite3.sqlite_version}
    result['source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__), *Path(__file__).resolve().parents[2].joinpath('thm').glob('*.py')]}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    write_new_text(output, json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    summary = {k: v for k, v in result.items() if k != 'rows'}
    print('THM_BENCHMARK_SUMMARY_BEGIN')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('THM_BENCHMARK_SUMMARY_END')


if __name__ == '__main__':
    main()
