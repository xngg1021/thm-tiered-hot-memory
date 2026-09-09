"""Versioned, JSON-safe evaluation contracts with evaluator-only ground truth."""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Iterable, Protocol
from thm.retrieval import Document

SCHEMA = 'thm-evaluation/1'
LAYERS = ('memory-dataplane', 'systems-runtime', 'LLM-agent-outcome')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def nonempty(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('nonempty string required')
    return value


@dataclass(frozen=True)
class Taxonomy:
    logical_tier: str = 'T3'
    compute_profile: str = 'python-sparse-cpu'
    physical_placement: str = 'sqlite-os-managed'

    def __post_init__(self):
        if self.logical_tier not in ('T0', 'T1', 'T2', 'T3'):
            raise ValueError('invalid logical tier')
        nonempty(self.compute_profile)
        nonempty(self.physical_placement)
        # No mapping from any one axis to another is permitted.


@dataclass(frozen=True)
class Task:
    id: str
    scope: str
    query: str
    documents: tuple[Document, ...] = field(repr=False)
    sequence: int = 0
    query_image: str | None = None

    def __post_init__(self):
        for value in (self.id, self.scope, self.query):
            nonempty(value)
        ids = [d.id for d in self.documents]
        if len(ids) != len(set(ids)) or any(d.scope != self.scope for d in self.documents):
            raise ValueError('duplicate document or foreign scope')
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError('invalid sequence')


@dataclass(frozen=True)
class GroundTruth:
    task_id: str
    evidence_ids: tuple[str, ...] = ()
    unit: str = 'document'
    resolved: bool = True
    diagnostic_only: bool = False
    answer: object = field(default=None, repr=False)
    rubric: object = field(default=None, repr=False)

    def __post_init__(self):
        nonempty(self.task_id)
        if self.unit not in ('document', 'session', 'unavailable'):
            raise ValueError('unsupported evidence unit')
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('duplicate evidence')
        for value in self.evidence_ids:
            nonempty(value)
        if self.unit == 'unavailable' and self.evidence_ids:
            raise ValueError('unavailable evidence cannot contain IDs')

    @property
    def scorable(self):
        return bool(self.evidence_ids) and self.resolved and not self.diagnostic_only


@dataclass(frozen=True)
class Result:
    task_id: str
    ground_truth: GroundTruth
    selected_ids: tuple[str, ...]
    selected_units: tuple[str, ...]
    parent_units: tuple[str, ...]
    budget_used: int
    latency_ms: float
    packed_count: int

    def __post_init__(self):
        if self.task_id != self.ground_truth.task_id:
            raise ValueError('result/ground-truth identity mismatch')
        if type(self.budget_used) is not int or self.budget_used < 0:
            raise ValueError('invalid budget')
        if not math.isfinite(self.latency_ms) or self.latency_ms < 0:
            raise ValueError('invalid latency')

    def public(self):
        gold = set(self.ground_truth.evidence_ids)
        return {'task_id': self.task_id, 'evidence_unit': self.ground_truth.unit,
                'gold_count': len(gold), 'scorable': self.ground_truth.scorable,
                'resolved': self.ground_truth.resolved,
                'diagnostic_only': self.ground_truth.diagnostic_only,
                'hits': len(gold.intersection(self.selected_units)),
                'parent_locator_hits': len(gold.intersection(self.parent_units)),
                'selected_ids': list(self.selected_ids), 'budget_used': self.budget_used,
                'latency_ms': self.latency_ms, 'packed_count': self.packed_count}


class Adapter(Protocol):
    name: str
    protocol: str

    def tasks(self, source: object) -> Iterable[tuple[Task, GroundTruth]]: ...


@dataclass(frozen=True)
class Receipt:
    benchmark: str
    protocol: str
    source_sha256: str
    implementation_sha256: str
    mode: str
    provenance: str
    taxonomy: Taxonomy
    layers: dict
    coverage: dict
    schema: str = SCHEMA
    full_dataset_acceptance: bool = False

    def __post_init__(self):
        if self.schema != SCHEMA or self.mode not in ('smoke', 'acceptance', 'full-research'):
            raise ValueError('invalid schema/mode')
        if self.provenance not in ('deterministic-fixture', 'external-dataset'):
            raise ValueError('invalid provenance')
        if set(self.layers) != set(LAYERS):
            raise ValueError('all three evidence layers required')
        for layer in self.layers.values():
            if layer.get('status') not in ('measured', 'not-run', 'unavailable'):
                raise ValueError('invalid evidence status')
        if self.full_dataset_acceptance:
            raise ValueError('measurement never automatically admits full dataset acceptance')
        for sha in (self.source_sha256, self.implementation_sha256):
            if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('SHA256 identity required')

    def public(self):
        value = asdict(self)
        return {**value, 'receipt_sha256': digest(value)}
