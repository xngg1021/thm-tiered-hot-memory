#!/usr/bin/env python3
"""Protocol 2 baseline instrumentation; diagnostic labels never enter search.

The search timer ends before instrumentation. Standalone source costs use the
identical serializer and tokenizer. Oracle feasibility is analysis only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.recall import benchmark as bench
from thm.retrieval import SearchIndex, TokenCounter


def census(rows):
    scored = [r for r in rows if r['category'] != 5 and r['fully_resolved'] and r['evidence_count']]
    result = {}
    for category in ['all', *[bench.CATEGORY[c] for c in range(1, 5)]]:
        subset = [r for r in scored if category == 'all' or bench.CATEGORY[r['category']] == category]
        counts = Counter(r['failure_bucket'] for r in subset if not r['hits'])
        result[category] = {key: {
            'count': counts[key], 'denominator': len(subset),
            'percentage': 100 * counts[key] / len(subset) if subset else None,
            'example_ids': [f"{r['scope']}:{r['question_index']}" for r in subset
                            if not r['hits'] and r['failure_bucket'] == key][:8],
        } for key in ('candidate_miss', 'candidate_found_but_not_packed', 'budget_impossible')}
    return result


def run(dataset, counter):
    traces = []
    original = SearchIndex.search

    def instrument(index, scope, query, **kwargs):
        out = original(index, scope, query, **kwargs)
        # The benchmark-only observer runs after the production timer stops.
        costs = {}
        for row in index.rows(scope):
            if row['id'] in out['ranked_ids']:
                label = json.dumps({'id': row['id'], 'speaker': row['speaker'],
                                    'date': row['timestamp']}, ensure_ascii=False)
                costs[row['id']] = counter(f"[source {label}]\n{row['text']}")
        traces.append({'candidate_ids': out['ranked_ids'], 'standalone_tokens': costs})
        return out

    with patch.object(SearchIndex, 'search', instrument):
        result = bench.run(dataset, counter, ['literal', 'sparse'], [600])
    samples = {str(s['sample_id']): s for s in dataset}
    for row, trace in zip(result['rows'], traces):
        qa = samples[row['scope']]['qa'][row['question_index']]
        gold, _ = bench.evidence_ids(qa.get('evidence', []))
        candidates = gold & set(trace['candidate_ids'])
        feasible = {g for g in candidates if trace['standalone_tokens'][g] <= row['budget']}
        row.update(trace)
        row['oracle_any_gold_feasible'] = bool(feasible)
        row['oversized_gold_ids'] = sorted(candidates - feasible)
        row['failure_bucket'] = ('success' if row['hits'] else 'candidate_miss' if not candidates
                                 else 'candidate_found_but_not_packed' if feasible else 'budget_impossible')
    result['frontier_schema'] = 1
    result['failure_census'] = {mode: census([r for r in result['rows'] if r['mode'] == mode])
                                for mode in ('literal', 'sparse')}
    result['split_contract'] = {
        'unit': 'conversation', 'algorithm': 'lexicographically first two sample IDs are calibration',
        'calibration': result['development_conversations'],
        'holdout': sorted(set(samples) - set(result['development_conversations'])),
        'inherited_from_protocol2': True,
        'promotion': 'holdout once, after calibration parameters are frozen',
    }
    result['diagnostic_limits'] = [
        'Candidate-found-not-packed includes feasible gold displaced by ranking and remaining budget.',
        'Temporal/entity/structural causes are not established by category labels.',
        'Segment feasibility does not establish that a fragment contains annotated evidence.',
        'Oracle only tests existence of one legal whole-source packing; never used by retrieval.',
        'Observer overhead excluded from the unchanged production search timer.',
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != bench.DATASET_SHA256:
        raise ValueError('pinned Protocol 2 dataset digest required')
    result = run(json.loads(raw), TokenCounter('cl100k_base'))
    result.update(dataset_sha256=digest, dataset_matches_pinned_reference=True,
                  dataset_upstream_commit=bench.DATASET_COMMIT)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps(result['failure_census'], indent=2))


if __name__ == '__main__':
    main()
