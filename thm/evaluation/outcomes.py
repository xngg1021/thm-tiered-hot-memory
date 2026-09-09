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


def attach_outcomes(receipt, outcomes, *, trace_bytes):
    """Verify trace bytes and exact task coverage, not the evaluator's score truth."""
    outcomes = tuple(outcomes)
    result = copy.deepcopy(receipt)
    claimed = result.pop('receipt_sha256', None)
    if claimed != digest(result):
        raise ValueError('invalid source receipt checksum')
    if result['provenance'] != 'external-dataset':
        raise ValueError('fixture receipts cannot acquire live agent outcomes')
    expected = {r['task_id'] for r in result['layers']['memory-dataplane']['rows']}
    ids = [o.task_id for o in outcomes]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('outcomes must cover exactly the executed task IDs')
    trace_sha = hashlib.sha256(trace_bytes).hexdigest()
    if any(o.trace_sha256 != trace_sha for o in outcomes):
        raise ValueError('trace checksum mismatch')
    scores = {}
    for metric in ('answer_accuracy', 'environment_success'):
        values = [getattr(o, metric) for o in outcomes if getattr(o, metric) is not None]
        scores[metric] = sum(values) / len(values) if values else None
        scores[metric + '_count'] = len(values)
    result['layers']['LLM-agent-outcome'] = {
        **scores, 'aggregation': 'macro mean over available per-task scores; nulls excluded',
        'status': 'measured', 'scope': 'externally supplied evaluator; not independently certified',
        'trace_sha256': trace_sha, 'rows': [asdict(o) for o in outcomes],
        'generation_calls': sum(o.generation_calls for o in outcomes),
        'judge_calls': sum(o.judge_calls for o in outcomes)}
    result['full_dataset_acceptance'] = False
    return {**result, 'receipt_sha256': digest(result)}
