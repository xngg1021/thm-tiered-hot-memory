#!/usr/bin/env python3
"""Calibration-only first: isolated deterministic ranking ablations."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.recall import benchmark as bench
from research.recall.frontier_temporal import reorder
from thm.retrieval import SearchIndex, TokenCounter
from research.recall.frontier_entity import reorder as entity_reorder


class TemporalIndex(SearchIndex):
    def _rank_candidates(self, scope, query, ranked):
        return reorder(ranked, query)


class EntityIndex(SearchIndex):
    def _rank_candidates(self, scope, query, ranked):
        return entity_reorder(ranked, query)


class SegmentIndex(SearchIndex):
    def _pack_candidates(self, expanded, budget, query):
        from research.recall.frontier_segments import pack
        return pack(self, expanded, budget, query)


class AssociationIndex(SearchIndex):
    def _rank_candidates(self, scope, query, ranked):
        from research.recall.frontier_association import expand
        return expand(self, scope, ranked)


class ValueIndex(SearchIndex):
    def _rank_candidates(self, scope, query, ranked):
        costs = []
        for n, row in enumerate(ranked, 1):
            label = json.dumps({'id': row['id'], 'speaker': row['speaker'], 'date': row['timestamp']}, ensure_ascii=False)
            cost = self._count('[source ' + label + ']\n' + row['text'])
            costs.append((1 / (60 + n) / cost ** 0.5, n, row))
        return [r for _, _, r in sorted(costs, key=lambda x: (-x[0], x[1]))]


class CombinedIndex(SearchIndex):
    def _rank_candidates(self, scope, query, ranked):
        from research.recall.frontier_association import expand
        return expand(self, scope, entity_reorder(ranked, query))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--policy', choices=['temporal', 'entity', 'segment', 'association', 'value', 'combined'], default='temporal')
    p.add_argument('--budgets', nargs='+', type=int, default=[600])
    p.add_argument('--split', choices=['calibration', 'full'], default='calibration')
    args = p.parse_args()
    raw = Path(args.dataset).read_bytes()
    if hashlib.sha256(raw).hexdigest() != bench.DATASET_SHA256:
        raise ValueError('exact pinned dataset required')
    data = json.loads(raw)
    calibration = sorted(s['sample_id'] for s in data)[:2]
    if args.split == 'calibration': data = [s for s in data if s['sample_id'] in calibration]
    results = {}
    for name, cls in [('baseline', SearchIndex), (args.policy, {'temporal': TemporalIndex, 'entity': EntityIndex, 'segment': SegmentIndex, 'association': AssociationIndex, 'value': ValueIndex, 'combined': CombinedIndex}[args.policy])]:
        with patch.object(bench, 'SearchIndex', cls):
            results[name] = bench.run(data, TokenCounter('cl100k_base'), ['sparse'], args.budgets)
    out = {'schema': 1, 'split': args.split, 'dataset_sha256': bench.DATASET_SHA256,
           'policies': results, 'temporal_weight': 0.25, 'generation_calls': 0,
           'parameter_search': False, 'embedding_used': False}
    Path(args.output).write_text(json.dumps(out, separators=(',', ':'))+'\n')
    for name, r in results.items():
        print(name, json.dumps(r['summaries'][f'sparse@{args.budgets[0]}']['main_categories_1_to_4']))

if __name__ == '__main__': main()
