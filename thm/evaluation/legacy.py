"""Additive fabric projection; old native metrics/rows remain inspectable."""
from .contracts import Receipt, Taxonomy, digest
from .metrics import legacy_metrics
from .identity import implementation_identity


def project(benchmark, rows, source):
    groups = {}
    for row in rows:
        key = f"{row['mode']}@{row['budget']}"
        groups.setdefault(key, []).append(row)
    return Receipt(benchmark, 'native-runner-projection/1', digest(source), implementation_identity(),
        'full-research', 'external-dataset', Taxonomy(compute_profile='see-native-runtime-receipt'),
        {'memory-dataplane': {'status': 'measured', 'operating_points': {
            k: legacy_metrics(v, benchmark) for k, v in groups.items()}},
         'systems-runtime': {'status': 'measured', 'scope': 'native per-query timing only',
             'physical_storage': {'status': 'unavailable', 'storage_profile': None,
                                  'placement': None, 'io_telemetry': None}},
         'LLM-agent-outcome': {'status': 'not-run', 'generation_calls': 0, 'judge_calls': 0,
                              'answer_accuracy': None}},
         {'rows': len(rows), 'scope': 'caller-supplied source; completeness not certified'}).public()
