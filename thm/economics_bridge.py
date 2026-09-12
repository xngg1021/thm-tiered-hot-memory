"""Portable THM <-> Context Economics evidence/advice protocol; neither imports the other."""
from dataclasses import asdict, dataclass, replace
import argparse
import json
import math
from pathlib import Path
from ._bounded_files import bounded_file_bytes
from .evaluation.contracts import digest, nonempty


UNITS = {
    'packed_tokens': 'token', 'full_history_tokens': 'token', 'latency': 'ms',
    'retrieval_recall': 'fraction', 'miss_reacquisition': 'token', 'resident_carry': 'token',
    'prefetch_waste': 'token', 'physical_read': 'byte', 'physical_write': 'byte',
    'compile_startup': 'ms', 'cpu': 'second', 'gpu': 'second', 'ram_peak': 'byte',
    'vram_peak': 'byte', 'task_success': 'fraction', 'cost': 'USD',
}


@dataclass(frozen=True)
class Measurement:
    value: float | None
    unit: str
    denominator: int
    aggregation: str
    source_sha256: str

    def __post_init__(self):
        if self.value is not None and (type(self.value) not in (int, float) or not math.isfinite(self.value) or self.value < 0):
            raise ValueError('invalid measured value')
        if type(self.denominator) is not int or self.denominator < 0:
            raise ValueError('explicit nonnegative denominator required')
        if self.value is not None and self.denominator == 0:
            raise ValueError('measured value requires observations')
        if self.aggregation not in ('sum', 'mean', 'peak', 'ratio', 'unknown'):
            raise ValueError('explicit aggregation required')
        if len(self.source_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.source_sha256):
            raise ValueError('measurement source hash required')


def verify_envelope(value, schema):
    body = {k: v for k, v in value.items() if k != 'receipt_sha256'}
    if body.get('schema') != schema or value.get('receipt_sha256') != digest(body):
        raise ValueError('invalid bridge schema/checksum')
    return body


def export_evidence(receipt, *, source_commit, observations=None):
    body = {k: v for k, v in receipt.items() if k != 'receipt_sha256'}
    if receipt.get('receipt_sha256') != digest(body):
        raise ValueError('source evaluation checksum mismatch')
    if len(source_commit) != 40 or any(c not in '0123456789abcdef' for c in source_commit):
        raise ValueError('exact THM commit required')
    rows = body['layers']['memory-dataplane']['rows']
    ids = [r['task_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate task denominator')
    source_sha = receipt['receipt_sha256']
    measurements = {name: Measurement(None, unit, 0, 'unknown', source_sha) for name, unit in UNITS.items()}
    for name, column, unit in (('packed_tokens', 'budget_used', 'token'), ('latency', 'latency_ms', 'ms')):
        values = [r[column] for r in rows if r.get(column) is not None]
        measurements[name] = Measurement(sum(values) if values else None, unit, len(values), 'sum', source_sha)
    gold = [r for r in rows if r.get('scorable')]
    count = sum(r['gold_count'] for r in gold)
    measurements['retrieval_recall'] = Measurement(sum(r['hits'] for r in gold)/count if count else None,
                                                 'fraction', count, 'ratio', source_sha)
    for name, supplied in (observations or {}).items():
        if name not in UNITS or name in ('packed_tokens', 'latency', 'retrieval_recall'):
            raise ValueError('unknown or canonical measurement override')
        measurement = supplied if isinstance(supplied, Measurement) else Measurement(**supplied)
        if measurement.unit != UNITS[name]:
            raise ValueError('bridge unit mismatch')
        if measurement.source_sha256 != source_sha:
            raise ValueError('measurement belongs to a different source receipt')
        measurements[name] = measurement
    value = {'schema': 'thm-ce-evidence/1', 'producer': 'THM', 'source_commit': source_commit,
             'source_receipt_sha256': source_sha, 'dataset_sha256': body.get('source_sha256'),
             'implementation_sha256': body.get('implementation_sha256'), 'task_ids': ids,
             'logical_taxonomy': 'THM:T0-T3', 'consumer_taxonomy': 'CE:L0-L6-independent',
             'provenance': body['provenance'], 'measurements': {k: asdict(v) for k, v in measurements.items()},
             'pricing_assumed': False, 'economic_optimum_accepted': False}
    return {**value, 'receipt_sha256': digest(value)}


@dataclass(frozen=True)
class EconomicAdvice:
    source_identity: str
    source_commit: str
    evidence_sha256: str
    min_budget: int
    max_budget: int
    recommended_budget: int
    latency_limit_ms: float | None = None
    cost_limit_usd: float | None = None
    objective: str = 'bounded-token-cost'
    policy_advice: str | None = None

    def __post_init__(self):
        nonempty(self.source_identity); nonempty(self.objective)
        if len(self.source_commit) != 40 or any(c not in '0123456789abcdef' for c in self.source_commit):
            raise ValueError('exact advice producer commit required')
        if len(self.evidence_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.evidence_sha256):
            raise ValueError('exact evidence receipt hash required')
        if any(type(x) is not int for x in (self.min_budget, self.max_budget, self.recommended_budget)) or not 0 <= self.min_budget <= self.recommended_budget <= self.max_budget <= 32768:
            raise ValueError('advice budget outside canonical bounds')
        for value in (self.latency_limit_ms, self.cost_limit_usd):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError('invalid economic envelope')

    def public(self):
        value = {'schema': 'ce-thm-advice/1', **asdict(self), 'automatic_mutation': False,
                 'taxonomy': {'THM': 'T0-T3', 'CE': 'L0-L6'}}
        return {**value, 'receipt_sha256': digest(value)}


def import_advice(value, *, expected_evidence_sha256):
    body = verify_envelope(value, 'ce-thm-advice/1')
    if body.get('automatic_mutation') is not False or body.get('taxonomy') != {'THM': 'T0-T3', 'CE': 'L0-L6'}:
        raise ValueError('advice cannot merge taxonomies or enable mutations')
    advice = EconomicAdvice(**{k: body[k] for k in EconomicAdvice.__dataclass_fields__})
    if advice.evidence_sha256 != expected_evidence_sha256:
        raise ValueError('advice belongs to a different evidence cohort')
    return advice


def configure_session(config, advice, *, apply=False):
    """Explicit configuration for a new harness session; running sessions are untouched."""
    if type(apply) is not bool:
        raise ValueError('explicit apply flag required')
    config.validate()
    candidate = replace(config, budget=advice.recommended_budget)
    candidate.validate()
    return candidate if apply else config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('export', 'validate-advice'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit')
    parser.add_argument('--evidence-sha256')
    args = parser.parse_args()
    try:
        raw = bounded_file_bytes(args.input, 8_000_000).decode('utf-8')
    except (OSError, ValueError) as exc:
        parser.error('bridge input must be a stable UTF-8 regular file within 8 MB: ' + str(exc))
    value = json.loads(raw)
    if args.operation == 'export':
        if not args.source_commit:
            parser.error('--source-commit required')
        result = export_evidence(value, source_commit=args.source_commit)
    else:
        result = import_advice(value, expected_evidence_sha256=args.evidence_sha256).public()
    with args.output.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
