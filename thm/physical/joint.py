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
