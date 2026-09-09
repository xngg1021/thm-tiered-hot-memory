"""Comparable retrieval metrics; no synthetic gold and no answer-accuracy alias."""
import statistics


def summarize(rows):
    scored = [r for r in rows if r['scorable']]
    n = len(scored)
    latencies = sorted(r['latency_ms'] for r in rows)
    def percentile(q):
        if not latencies:
            return None
        at = (len(latencies) - 1) * q
        lo = int(at)
        hi = min(lo + 1, len(latencies) - 1)
        return latencies[lo] + (latencies[hi] - latencies[lo]) * (at - lo)
    return {'tasks': len(rows), 'scorable': n,
            'no_gold': sum(r['gold_count'] == 0 for r in rows),
            'unresolved': sum(not r['resolved'] for r in rows),
            'diagnostic_only': sum(r['diagnostic_only'] for r in rows),
            'any_gold_hit_rate': sum(r['hits'] > 0 for r in scored) / n if n else None,
            'all_gold_hit_rate': sum(r['hits'] == r['gold_count'] for r in scored) / n if n else None,
            'macro_evidence_recall': statistics.mean(r['hits'] / r['gold_count'] for r in scored) if n else None,
            'micro_evidence_recall': sum(r['hits'] for r in scored) / sum(r['gold_count'] for r in scored) if n else None,
            'parent_locator_coverage': sum(r['parent_locator_hits'] > 0 for r in scored) / n if n else None,
            'empty_context_rate': statistics.mean(r['packed_count'] == 0 for r in rows) if rows else None,
            'mean_budget_used': statistics.mean(r['budget_used'] for r in rows) if rows else None,
            'latency_ms': {'p50': percentile(.5), 'p95': percentile(.95), 'p99': percentile(.99)}}


def legacy_metrics(rows, benchmark):
    """Project native rows without changing their old protocol or denominators."""
    projected = []
    for row in rows:
        lme = benchmark == 'longmemeval-s'
        gold = row['gold_sessions'] if lme else row['evidence_count']
        resolved = row['resolved_gold'] == gold if lme else row['fully_resolved']
        diagnostic = False if lme else row['category'] == 5
        projected.append({'gold_count': gold, 'resolved': resolved,
            'diagnostic_only': diagnostic, 'scorable': bool(gold) and resolved and not diagnostic,
            'hits': row['hits'], 'parent_locator_hits': row.get('parent_locator_hits', row['hits']),
            'packed_count': row.get('packed_selected_count', row['selected_count']),
            'budget_used': row['budget_used'], 'latency_ms': row['total_ms']})
    return summarize(projected)
