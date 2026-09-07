#!/usr/bin/env python3
"""Paired, conversation-cluster bootstrap summaries of a frozen ablation."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.recall.benchmark import percentile


def paired(before, after, split='held_out', budget=600, category=None):
    def eligible(r):
        return (r['budget'] == budget and r['category'] != 5 and r['evidence_count']
                and r['fully_resolved'] and (split == 'all' or r['split'] == split)
                and (category is None or r['category'] == category))
    a = {(r['scope'], r['question_index']): r for r in before if eligible(r)}
    b = {(r['scope'], r['question_index']): r for r in after if eligible(r)}
    if a.keys() != b.keys(): raise ValueError('paired question identity mismatch')
    groups = defaultdict(list)
    wins = losses = ties = 0
    for key in a:
        delta = int(b[key]['hits'] > 0) - int(a[key]['hits'] > 0)
        groups[key[0]].append(delta)
        wins += delta > 0; losses += delta < 0; ties += delta == 0
    rng = random.Random(20260907)
    ids = sorted(groups)
    boot = []
    for _ in range(2000):
        sample = [rng.choice(ids) for _ in ids]
        values = [d for scope in sample for d in groups[scope]]
        if values: boot.append(100 * sum(values) / len(values))
    n = len(a)
    baseline_hits = sum(r['hits'] > 0 for r in a.values())
    return {'denominator': n, 'wins': wins, 'losses': losses, 'ties': ties,
            'delta_pp': 100*(wins-losses)/n if n else None,
            'relative_percent': 100*(wins-losses)/baseline_hits if baseline_hits else None,
            'cluster_bootstrap_95ci_pp': [percentile(boot, .025), percentile(boot, .975)],
            'bootstrap_unit': 'conversation', 'bootstrap_seed': 20260907, 'replicates': 2000}


def report(data):
    policies = data['policies']
    name = next(k for k in policies if k != 'baseline')
    a, b = policies['baseline'], policies[name]
    budgets = a['budgets']
    out = {k: v for k, v in data.items() if k != 'policies'}
    out['summaries'] = {k: v['summaries'] for k, v in policies.items()}
    out['builds'] = {k: v['builds'] for k, v in policies.items()}
    out['paired'] = {str(budget): {split: paired(a['rows'], b['rows'], split, budget)
                                  for split in ['development', 'held_out', 'all']} for budget in budgets}
    out['category_paired_600'] = {str(c): paired(a['rows'], b['rows'], category=c) for c in range(1, 5)}
    out['failure_census_v2'] = {}
    for policy, result in policies.items():
        rows = [r for r in result['rows'] if r['budget'] == 600 and r['category'] != 5
                and r['fully_resolved'] and r['evidence_count']]
        out['failure_census_v2'][policy] = {
            'denominator': len(rows), 'candidate_missing': sum(r['candidate_hits'] == 0 for r in rows),
            'candidate_present_not_packed': sum(r['candidate_hits'] > 0 and r['hits'] == 0 for r in rows),
            'causal_labels': 'Temporal/entity/association causes and stale/scope cases not inferred from category.'}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = report(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(output['paired']['600'], indent=2))


if __name__ == '__main__': main()
