"""Bounded external environment and official scorer bridges; no built-in LLM."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from .contracts import digest, nonempty


@dataclass(frozen=True)
class EnvironmentIdentity:
    benchmark: str
    environment: str
    implementation_sha256: str
    provenance: str = 'deterministic-fixture'

    def __post_init__(self):
        nonempty(self.benchmark); nonempty(self.environment)
        if self.provenance not in ('deterministic-fixture', 'external-environment'):
            raise ValueError('invalid environment provenance')
        if len(self.implementation_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.implementation_sha256):
            raise ValueError('environment implementation hash required')


class EnvironmentRunner:
    def __init__(self, environment, identity, *, max_steps=32, wall_seconds=30, clock=time.monotonic):
        if type(max_steps) is not int or not 1 <= max_steps <= 256 or type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds) or not 0 < wall_seconds <= 300:
            raise ValueError('bounded environment limits required')
        for method in ('reset', 'step', 'close'):
            if not callable(getattr(environment, method, None)):
                raise TypeError('environment protocol required')
        self.environment, self.identity = environment, identity
        self.max_steps, self.wall_seconds, self.clock = max_steps, wall_seconds, clock

    def run(self, task, policy, memory=None):
        start = self.clock(); trace = []
        try:
            observation = self.environment.reset(task.id)
            done, success = False, None
            for ordinal in range(self.max_steps):
                if self.clock()-start > self.wall_seconds:
                    raise TimeoutError('environment deadline')
                action = policy(task.query, observation, memory)
                result = self.environment.step(action)
                if not isinstance(result, dict) or type(result.get('done')) is not bool:
                    raise ValueError('invalid environment step result')
                observation, done = result.get('observation'), result['done']
                trace.append({'task_id': task.id, 'step': ordinal, 'action': action, 'observation': observation, 'done': done})
                if len(json.dumps(trace)) > 4_000_000:
                    raise ValueError('trace exceeds bounded input')
                if memory is not None and isinstance(observation, str) and observation.strip():
                    memory.add(observation)
                if done:
                    success = result.get('success')
                    if success is not None and type(success) is not bool:
                        raise ValueError('environment success must be boolean or missing')
                    break
            if self.clock()-start > self.wall_seconds:
                raise TimeoutError('environment completion deadline')
            raw = json.dumps(trace, sort_keys=True, allow_nan=False).encode()
            value = {'schema': 'thm-environment/1', 'task_id': task.id, 'identity': asdict(self.identity),
                     'steps': len(trace), 'completed': done, 'status': 'completed' if done else 'step-limit',
                     'environment_success': success, 'trace_sha256': hashlib.sha256(raw).hexdigest(),
                     'latency_ms': (self.clock()-start)*1000, 'task_outcome_accepted': False}
            return {**value, 'receipt_sha256': digest(value)}, raw
        finally:
            self.environment.close()


class OfficialScorerBridge:
    """Explicit callback for an installed official scorer; gold never enters memory."""
    def __init__(self, scorer, *, evaluator_id, implementation_sha256):
        if not callable(scorer):
            raise TypeError('explicit scorer callback required')
        self.scorer, self.evaluator_id = scorer, nonempty(evaluator_id)
        self.implementation_sha256 = implementation_sha256
        EnvironmentIdentity('scorer', self.evaluator_id, implementation_sha256)

    def score(self, task, ground_truth, answer, *, trace_sha256):
        if task.id != ground_truth.task_id:
            raise ValueError('scorer task/gold identity mismatch')
        if len(trace_sha256) != 64 or any(c not in '0123456789abcdef' for c in trace_sha256):
            raise ValueError('trace identity required')
        score = self.scorer(answer=answer, ground_truth=ground_truth.answer, rubric=ground_truth.rubric)
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('official scorer returned invalid score')
        return {'task_id': task.id, 'evaluator_id': self.evaluator_id, 'implementation_sha256': self.implementation_sha256,
                'trace_sha256': trace_sha256, 'answer_accuracy': score, 'independently_certified': False}
