"""Ingest externally measured agent outcomes without automatic acceptance."""
from dataclasses import asdict, dataclass
import copy
import hashlib
import math
from .contracts import digest, nonempty


@dataclass(frozen=True)
class AgentOutcome:
    task_id: str
    model_id: str
    evaluator_id: str
    trace_sha256: str
    generation_calls: int
    judge_calls: int
    answer_accuracy: float | None = None
    environment_success: float | None = None
    environment_id: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    answer_numerator: int | None = None
    answer_denominator: int | None = None

    def __post_init__(self):
        for value in (self.task_id, self.model_id, self.evaluator_id):
            nonempty(value)
        if len(self.trace_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.trace_sha256):
            raise ValueError('external trace SHA256 required')
        for value in (self.generation_calls, self.judge_calls):
            if type(value) is not int or value < 0:
                raise ValueError('nonnegative integer call counts required')
        if not self.generation_calls:
            raise ValueError('agent outcome requires a real generation call')
        if self.answer_accuracy is None and self.environment_success is None:
            raise ValueError('at least one measured outcome required')
        for value in (self.answer_accuracy, self.environment_success):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError('outcomes must lie in [0,1]')
        if self.environment_id is not None:
            nonempty(self.environment_id)
        for value in (self.latency_ms, self.cost_usd):
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError('latency/cost must be finite and nonnegative')
        if (self.answer_numerator is None) != (self.answer_denominator is None):
            raise ValueError('micro score needs numerator and denominator')
        if self.answer_denominator is not None:
            if type(self.answer_numerator) is not int or type(self.answer_denominator) is not int or not 0 <= self.answer_numerator <= self.answer_denominator or self.answer_denominator < 1:
                raise ValueError('invalid micro score denominator')
            if self.answer_accuracy is None or abs(self.answer_accuracy-self.answer_numerator/self.answer_denominator) > 1e-12:
                raise ValueError('macro/micro score mismatch')


def attach_outcomes(receipt, outcomes, *, trace_bytes, allow_partial=False):
    """Verify trace bytes and exact task coverage, not the evaluator's score truth."""
    outcomes = tuple(outcomes)
    if not outcomes:
        raise ValueError('at least one new measured outcome required')
    result = copy.deepcopy(receipt)
    claimed = result.pop('receipt_sha256', None)
    if claimed != digest(result):
        raise ValueError('invalid source receipt checksum')
    if result['provenance'] != 'external-dataset':
        raise ValueError('fixture receipts cannot acquire live agent outcomes')
    expected = {r['task_id'] for r in result['layers']['memory-dataplane']['rows']}
    ids = [o.task_id for o in outcomes]
    if type(allow_partial) is not bool:
        raise ValueError('explicit partial flag required')
    if len(ids) != len(set(ids)) or not set(ids) <= expected or (not allow_partial and set(ids) != expected):
        raise ValueError('outcomes must cover exactly the executed task IDs')
    trace_sha = hashlib.sha256(trace_bytes).hexdigest()
    if any(o.trace_sha256 != trace_sha for o in outcomes):
        raise ValueError('trace checksum mismatch')
    previous = result['layers'].get('LLM-agent-outcome', {}).get('rows', [])
    if previous:
        if not allow_partial or set(ids) & {r['task_id'] for r in previous}:
            raise ValueError('duplicate outcome attachment')
        outcomes = tuple(AgentOutcome(**r) for r in previous) + outcomes
    ids = [o.task_id for o in outcomes]
    scores = {}
    for metric in ('answer_accuracy', 'environment_success'):
        values = [getattr(o, metric) for o in outcomes if getattr(o, metric) is not None]
        scores[metric] = sum(values) / len(values) if values else None
        scores[metric + '_count'] = len(values)
    result['layers']['LLM-agent-outcome'] = {
        **scores, 'aggregation': 'macro mean over available per-task scores; nulls excluded',
        'status': 'measured', 'coverage_status': 'complete' if set(ids) == expected else 'partial',
        'missing_task_ids': sorted(expected-set(ids)), 'executed_task_count': len(expected),
        'reported_task_count': len(ids), 'scope': 'externally supplied evaluator; not independently certified',
        'trace_sha256': trace_sha, 'rows': [asdict(o) for o in outcomes],
        'generation_calls': sum(o.generation_calls for o in outcomes),
        'judge_calls': sum(o.judge_calls for o in outcomes)}
    layer = result['layers']['LLM-agent-outcome']
    numerators = [o.answer_numerator for o in outcomes if o.answer_denominator is not None]
    denominators = [o.answer_denominator for o in outcomes if o.answer_denominator is not None]
    layer['answer_micro_accuracy'] = sum(numerators)/sum(denominators) if denominators else None
    layer['answer_micro_denominator'] = sum(denominators) if denominators else None
    layer['trace_sha256s'] = sorted({o.trace_sha256 for o in outcomes})
    for metric in ('latency_ms', 'cost_usd'):
        values = [getattr(o, metric) for o in outcomes if getattr(o, metric) is not None]
        layer[metric + '_observed_sum'] = sum(values) if values else None
        layer[metric + '_count'] = len(values)
    result['full_dataset_acceptance'] = False
    return {**result, 'receipt_sha256': digest(result)}
