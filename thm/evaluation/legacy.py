"""Additive fabric projection; old native metrics/rows remain inspectable."""
from .contracts import Receipt, Taxonomy, digest
from .metrics import legacy_metrics
from .identity import implementation_identity


def project(benchmark, rows, source, *, native_source_sha256):
    if not isinstance(native_source_sha256, str) or len(native_source_sha256) != 64 or any(c not in "0123456789abcdef" for c in native_source_sha256):
        raise ValueError("native runner source SHA256 required")
    implementation = digest({"thm": implementation_identity(), "native_runner": benchmark, "native_source_sha256": native_source_sha256})
    groups = {}
    for row in rows:
        key = f"{row['mode']}@{row['budget']}"
        groups.setdefault(key, []).append(row)
    return Receipt(benchmark, 'native-runner-projection/1', digest(source), implementation,
        'full-research', 'external-dataset', Taxonomy(compute_profile='see-native-runtime-receipt'),
        {'memory-dataplane': {'status': 'measured', 'operating_points': {
            k: legacy_metrics(v, benchmark) for k, v in groups.items()}},
         'systems-runtime': {'status': 'measured', 'native_source_sha256': native_source_sha256, 'scope': 'native per-query timing only',
             'physical_storage': {'status': 'unavailable', 'storage_profile': None,
                                  'placement': None, 'io_telemetry': None}},
         'LLM-agent-outcome': {'status': 'not-run', 'generation_calls': 0, 'judge_calls': 0,
                              'answer_accuracy': None}},
         {'rows': len(rows), 'scope': 'caller-supplied source; completeness not certified'}).public()
