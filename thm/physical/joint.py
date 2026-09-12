"""Joint compute/data plans reuse the existing physical placement manifest."""
from dataclasses import asdict, dataclass
from thm.runtime.fabric.contracts import identity
from .segments import current


@dataclass(frozen=True)
class JointExecutionPlan:
    scope_identity: str
    generation: str
    embedding_profile: str | None
    semantic_policy: str
    inference_provider: str
    vector_index_provider: str
    current_placement: str
    target_residency: str
    transfer_provider: str
    device: str
    workload: str
    batch_policy: str
    expected_p95_ms: float | None
    expected_cpu_seconds: float | None
    staging_ms: float | None
    expected_reuses: int
    fallback: str
    source_representation: str
    automatic_relocation: bool = False
    semantic_activity_mutation: bool = False

    def receipt(self):
        value = asdict(self)
        return {**value, 'plan_id': identity(value)}


class JointComputeDataPlanner:
    def choose(self, candidates, *, objective, constraints, current_generation, profile_identity, expected_reuses=1):
        """Hard constraints followed by named lexicographic costs, never a weighted score."""
        import math
        if objective not in ('interactive', 'bulk', 'background') or type(expected_reuses) is not int or expected_reuses < 1:
            raise ValueError('valid objective/reuse horizon required')
        required = ('logical_object', 'representation', 'compute_profile', 'placement', 'transfer_plan', 'resident_index', 'runtime_provider')
        admitted, rejected = [], []
        for candidate in candidates:
            reasons = []
            if any(not candidate.get(k) for k in required):
                reasons.append('incomplete-joint-identity')
            if candidate.get('generation') != current_generation or candidate.get('profile_identity') != profile_identity:
                reasons.append('stale-profile-or-generation')
            if candidate.get('semantic_safe') is not True:
                reasons.append('semantic-evidence')
            metrics = candidate.get('metrics', {})
            for key, (relation, limit) in constraints.items():
                value = metrics.get(key)
                if relation not in ('max', 'min', 'equal'):
                    raise ValueError('unknown constraint relation')
                if relation != 'equal' and (type(limit) not in (int, float) or not math.isfinite(limit)):
                    raise ValueError('finite numeric constraint limit required')
                if value is None or (relation != 'equal' and (type(value) not in (int, float) or not math.isfinite(value))) or (relation == 'max' and value > limit) or (relation == 'min' and value < limit) or (relation == 'equal' and value != limit):
                    reasons.append('constraint:' + key)
            costs = ('latency_ms', 'transfer_ms', 'startup_ms', 'compile_ms', 'throughput', 'cpu_seconds')
            if any(type(metrics.get(k)) not in (int, float) or not math.isfinite(metrics[k]) or metrics[k] < 0 for k in costs):
                reasons.append('unknown-cost')
            if reasons:
                rejected.append({'candidate_id': identity(candidate), 'reasons': reasons})
                continue
            latency = metrics['latency_ms'] + (metrics['transfer_ms']+metrics['startup_ms']+metrics['compile_ms'])/expected_reuses
            key = ((latency, -metrics['throughput']) if objective == 'interactive' else
                   (-metrics['throughput'], latency) if objective == 'bulk' else
                   (metrics['cpu_seconds'], latency))
            admitted.append((key, identity(candidate), candidate, latency))
        admitted.sort(key=lambda row: (row[0], row[1]))
        return {'schema': 'thm-joint-selection/1', 'selected': admitted[0][2] if admitted else None,
                'predicted_latency_ms': admitted[0][3] if admitted else None, 'objective': objective,
                'ordering': 'latency,throughput' if objective == 'interactive' else 'throughput,latency' if objective == 'bulk' else 'cpu-seconds,latency',
                'rejected': rejected, 'fallback': 'validated-reference-local', 'automatic_relocation': False}

    def plan(self, index, scope, *, embedding_profile=None, candidate=None, workload='interactive',
             policy='auto-safe', observations=None, resident=False, expected_reuses=1):
        with index._lock:
            generation = index.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
            if generation is None:
                raise ValueError('scope not indexed')
            placement = current(index, scope, embedding_profile) if embedding_profile else None
        if placement and placement['generation'] != generation[0]:
            raise ValueError('stale physical placement')
        observation = observations or {}
        staged = 0.0 if resident else observation.get('staging_ms')
        estimate = observation.get('p95')
        if estimate is not None and not resident:
            estimate = estimate + staged/max(1, expected_reuses) if staged is not None else None
        provider = candidate.provider if candidate else 'reference'
        device = candidate.device if candidate else 'cpu'
        return JointExecutionPlan(identity(scope), generation[0], embedding_profile, policy,
            candidate.inference_provider if candidate else 'reference', provider,
            placement['target_id'] if placement else 'sqlite-local',
            candidate.placement if candidate else 'dram', candidate.transfer if candidate else 'host.transfer',
            device, workload, 'deadline-aware-opportunity', estimate, observation.get('cpu_seconds'), staged,
            max(1, expected_reuses), 'validated-reference', 'immutable-segment' if placement else 'vectors_v2')

    def validate(self, plan, index, scope):
        with index._lock:
            row = index.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
            placement = current(index, scope, plan.embedding_profile) if plan.embedding_profile else None
        if identity(scope) != plan.scope_identity or not row or row[0] != plan.generation:
            raise ValueError('joint execution plan stale')
        if (placement['target_id'] if placement else 'sqlite-local') != plan.current_placement:
            raise ValueError('physical placement changed')
        return True
