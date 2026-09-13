"""THM 1.6 <-> CE version-2 telemetry/advice. No CE import or source authority."""
from dataclasses import asdict, dataclass, field
from .contracts import digest, finite, integer
from thm.economics_bridge import export_evidence, verify_envelope, EconomicAdvice

RUNTIME_UNITS = {
    'full_history_counterfactual': 'token', 'retrieval_latency': 'ms', 'candidate_ceiling': 'fraction',
    'budget_oracle': 'fraction', 'ranking_loss': 'evidence-unit', 'packing_loss': 'evidence-unit',
    'evidence_recall': 'fraction', 'energy': 'joule', 'power': 'watt', 'temperature': 'celsius',
    'thermal_headroom': 'celsius', 'throttle_time': 'second', 'effective_clock': 'hertz',
    'concurrency': 'request', 'queue_wait': 'ms', 'recovery_time': 'second', 'failure_probability': 'fraction',
    'MTTR': 'second', 'B10': 'declared-exposure', 'hazard': 'declared-exposure-inverse',
    'TUFR': 'ms', 'task_completion_time': 'ms'}
RUNTIME_DIMENSIONS = ('provider', 'physical_io', 'NUMA', 'storage_tier', 'topology_epoch', 'reliability', 'task_outcome')


@dataclass(frozen=True)
class RuntimeMeasurement:
    value: float | None
    unit: str
    denominator: int
    source_sha256: str
    evidence: str
    aggregation: str = 'mean'
    exposure_unit: str | None = None

    def __post_init__(self):
        integer(self.denominator)
        if self.value is not None:
            finite(self.value, minimum=-273.15 if self.unit == 'celsius' else 0)
            if not self.denominator:
                raise ValueError('measurement requires observations')
        if self.evidence not in ('simulated', 'hardware-observed', 'production-observed', 'callable-fixture', 'unavailable'):
            raise ValueError('runtime evidence class required')
        if self.evidence == 'unavailable' and self.value is not None:
            raise ValueError('unavailable measurements must be null')
        if len(self.source_sha256) != 64 or any(x not in '0123456789abcdef' for x in self.source_sha256):
            raise ValueError('source receipt identity required')
        if self.unit.startswith('declared-exposure') and self.value is not None and not self.exposure_unit:
            raise ValueError('reliability exposure unit required')


def export_systems_evidence(evaluation_receipt, *, source_commit, systems_receipt, measurements=None, observations=None):
    base = export_evidence(evaluation_receipt, source_commit=source_commit, observations=observations)
    if evaluation_receipt['layers']['memory-dataplane'].get('counter') == 'utf8_bytes':
        # Byte budgets cannot become token measurements when crossing the bridge.
        base['measurements']['packed_tokens'].update(value=None, denominator=0, aggregation='unknown')
    body = {k:v for k,v in systems_receipt.items() if k != 'receipt_sha256'}
    if systems_receipt.get('receipt_sha256') != digest(body):
        raise ValueError('systems receipt checksum mismatch')
    if body.get('task_ids') != base['task_ids'] or body.get('source_commit') != source_commit:
        raise ValueError('systems/evaluation denominator or commit mismatch')
    sha = systems_receipt['receipt_sha256']
    selected = {name: RuntimeMeasurement(None,unit,0,sha,'unavailable') for name,unit in RUNTIME_UNITS.items()}
    for name, value in (measurements or {}).items():
        if name not in selected:
            raise ValueError('unknown runtime measurement')
        row = value if isinstance(value,RuntimeMeasurement) else RuntimeMeasurement(**value)
        if row.unit != RUNTIME_UNITS[name] or row.source_sha256 != sha:
            raise ValueError('measurement unit/source mismatch')
        selected[name] = row
    output = {k:v for k,v in base.items() if k != 'receipt_sha256'}
    output.update(schema='thm-ce-evidence/2', bridge_version='1.6', systems_receipt_sha256=sha,
        systems_measurements={k:asdict(v) for k,v in selected.items()},
        systems_dimensions={k:body.get(k) for k in RUNTIME_DIMENSIONS})
    return {**output,'receipt_sha256':digest(output)}


@dataclass(frozen=True)
class RuntimeEconomicAdvice:
    memory: EconomicAdvice
    topology_epoch: int
    expires_at: float
    retrieval_budget: int | None = None
    energy_envelope: float | None = None
    concurrency_constraint: int | None = None
    provider_constraint: tuple[str,...] = ()
    residency_advice: str | None = None
    prefetch_advice: str | None = None
    operating_point_advice: str | None = None

    def __post_init__(self):
        integer(self.topology_epoch)
        finite(self.expires_at)
        if self.retrieval_budget is not None:
            integer(self.retrieval_budget,maximum=32768)
        if self.energy_envelope is not None:
            finite(self.energy_envelope)
        if self.concurrency_constraint is not None:
            integer(self.concurrency_constraint,minimum=1,maximum=100000)

    def public(self):
        body={'schema':'ce-thm-advice/2',**asdict(self),'automatic_mutation':False,
              'taxonomy':{'THM':'T0-T3','CE':'L0-L6'}}
        return {**body,'receipt_sha256':digest(body)}


def import_systems_advice(value, *, expected_evidence_sha256, topology_epoch, now):
    body=verify_envelope(value,'ce-thm-advice/2')
    if body.get('automatic_mutation') is not False or body.get('taxonomy') != {'THM':'T0-T3','CE':'L0-L6'}:
        raise ValueError('advice authority violation')
    fields={k:body[k] for k in RuntimeEconomicAdvice.__dataclass_fields__}
    fields['memory']=EconomicAdvice(**fields['memory'])
    advice=RuntimeEconomicAdvice(**fields)
    if advice.memory.evidence_sha256 != expected_evidence_sha256 or advice.topology_epoch != topology_epoch or now >= advice.expires_at:
        raise ValueError('stale or mismatched CE advice')
    return advice
