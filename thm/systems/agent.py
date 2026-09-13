"""Agent program, KV and tool lifecycle contracts independent of inference engines."""
from dataclasses import asdict, dataclass
from typing import Protocol
from .contracts import finite, integer, nonempty

PROGRAM_KINDS = ('AgentProgram', 'Trajectory', 'Session', 'Turn', 'LLMCall', 'ToolCall', 'SubagentCall', 'EnvironmentStep')
KV_STATES = ('active_inference', 'waiting_tool', 'waiting_subagent', 'idle_likely_reuse', 'expired')
KV_TIERS = ('HBM', 'DRAM', 'SSD', 'remote', 'recompute')
RUNTIMES = ('vllm', 'sglang', 'tensorrt-llm', 'llama.cpp', 'dynamo', 'lmcache', 'mooncake', 'hermes', 'fixture')


@dataclass(frozen=True)
class AgentProgramIdentity:
    program: str
    trajectory: str
    session: str
    turn: str
    call: str
    kind: str
    parent: str | None = None

    def __post_init__(self):
        if self.kind not in PROGRAM_KINDS:
            raise ValueError('invalid agent event kind')
        for value in (self.program, self.trajectory, self.session, self.turn, self.call):
            nonempty(value)


@dataclass(frozen=True)
class KVRecord:
    prefix_identity: str
    session_identity: str
    model_identity: str
    runtime_identity: str
    device: str
    size: int
    last_use: float
    expected_reuse: float
    state: str = 'idle_likely_reuse'
    tier: str = 'HBM'
    topology_epoch: int = 0

    def __post_init__(self):
        for value in (self.prefix_identity, self.session_identity, self.model_identity, self.runtime_identity, self.device):
            nonempty(value)
        integer(self.size)
        integer(self.topology_epoch)
        finite(self.last_use)
        finite(self.expected_reuse)
        if self.state not in KV_STATES or self.tier not in KV_TIERS:
            raise ValueError('invalid KV lifecycle')


class KVResidencyProvider(Protocol):
    runtime: str
    def observe(self, session: str) -> tuple[KVRecord, ...]: ...
    def apply(self, action: str, record: KVRecord): ...
    def close(self): ...


class KVResidencyBridge:
    def __init__(self, provider):
        if provider.runtime not in RUNTIMES:
            raise ValueError('unsupported runtime integration contract')
        self.provider = provider

    def advise(self, record, *, now, memory_pressure=0., epoch=None):
        finite(now)
        finite(memory_pressure)
        if now < record.last_use or not 0 <= memory_pressure <= 1:
            raise ValueError('invalid lifecycle observation')
        if epoch is not None and record.topology_epoch != epoch:
            action = 'recompute'
        elif record.state == 'expired':
            action = 'evict'
        elif record.state == 'active_inference':
            action = 'keep' if record.tier == 'HBM' else 'reload'
        elif memory_pressure >= .8 and record.tier == 'HBM':
            action = 'offload'
        elif now-record.last_use > record.expected_reuse:
            action = 'evict'
        else:
            action = 'keep'
        return {'action': action, 'record': asdict(record), 'mode': 'advice',
                'source_memory_persisted': False, 'semantic_memory_is_kv': False}

    def execute(self, advice, *, apply=False):
        if apply is not True:
            return {**advice, 'applied': False}
        record = KVRecord(**advice['record'])
        current = tuple(self.provider.observe(record.session_identity))
        if record not in current:
            raise ValueError('KV advice is stale or cross-session')
        action = advice['action']
        if action not in ('keep', 'offload', 'reload', 'recompute', 'evict'):
            raise ValueError('unknown KV action')
        return {'applied': True, 'result': self.provider.apply(action, record)}


@dataclass(frozen=True)
class ProgramSchedulerObservation:
    identity: AgentProgramIdentity
    runtime: str
    queue_state: str
    dependencies: tuple[str, ...] = ()
    tool_wait: bool = False
    prefix_reuse: bool = False
    session_affinity: str | None = None
    phase: str = 'prefill'

    def __post_init__(self):
        if self.runtime not in RUNTIMES or self.phase not in ('prefill', 'decode', 'tool', 'idle'):
            raise ValueError('invalid program scheduler observation')


@dataclass(frozen=True)
class ToolInvocation:
    identity: AgentProgramIdentity
    state: str
    readiness: str
    side_effect_class: str
    input_sha256: str
    result_identity: str | None = None

    def __post_init__(self):
        if self.state not in ('proposed', 'running', 'completed', 'cancelled', 'failed'):
            raise ValueError('invalid tool state')
        if self.readiness not in ('incomplete', 'ready', 'unavailable'):
            raise ValueError('invalid tool readiness')
        if self.side_effect_class not in ('read-only', 'safe-idempotent', 'side-effecting'):
            raise ValueError('tool effect class required')
        if len(self.input_sha256) != 64:
            raise ValueError('input identity required')

    def speculation(self, *, opt_in=False):
        eligible = self.readiness == 'ready' and self.side_effect_class in ('read-only', 'safe-idempotent') and self.state == 'proposed'
        return {'eligible': eligible, 'mode': 'execute' if eligible and opt_in is True else 'shadow',
                'automatic_side_effect': False, 'input_sha256': self.input_sha256}


def execute_speculation(invocation, function, *, opt_in=False):
    policy = invocation.speculation(opt_in=opt_in)
    if policy['mode'] != 'execute':
        return {**policy, 'executed': False, 'result': None}
    # Work must be submitted to an owned deadline worker by the host runtime.
    result = function(invocation)
    return {**policy, 'executed': True, 'result': result}


@dataclass(frozen=True)
class Span:
    identity: str
    component: str
    start: float
    end: float
    dependencies: tuple[str, ...] = ()

    def __post_init__(self):
        nonempty(self.identity)
        if self.component not in ('retrieval', 'context-assembly', 'prefill', 'decode', 'tool', 'queue', 'io', 'kv-reload', 'recompute'):
            raise ValueError('unknown latency component')
        finite(self.start)
        finite(self.end)
        if self.end < self.start:
            raise ValueError('negative span')


def critical_path(spans, *, submitted, useful_first=None, completed=None):
    spans = tuple(spans)
    finite(submitted)
    if len(spans) > 10000:
        raise ValueError('span bound')
    lookup = {s.identity: s for s in spans}
    if len(lookup) != len(spans):
        raise ValueError('duplicate span')
    costs, paths = {}, {}
    raw = {}
    for span in sorted(spans, key=lambda s: (s.end, s.start, s.identity)):
        if span.start < submitted:
            raise ValueError('span precedes task')
        if any(key not in lookup or lookup[key].end > span.start or key not in costs for key in span.dependencies):
            raise ValueError('invalid span dependency or cycle')
        predecessor = max(span.dependencies, key=lambda key: costs[key], default=None)
        duration = span.end-span.start
        costs[span.identity] = duration + (costs[predecessor] if predecessor else 0)
        paths[span.identity] = (paths[predecessor] if predecessor else ())+(span.identity,)
        raw[span.component] = raw.get(span.component, 0)+duration
    endpoint = max(costs, key=costs.get, default=None)
    path = paths[endpoint] if endpoint else ()
    exposed = {}
    for key in path:
        span = lookup[key]
        exposed[span.component] = exposed.get(span.component, 0)+span.end-span.start
    finish = max((s.end for s in spans), default=submitted) if completed is None else finite(completed)
    if finish < max((s.end for s in spans), default=submitted):
        raise ValueError('completion precedes final span')
    if useful_first is not None and not submitted <= useful_first <= finish:
        raise ValueError('useful response timestamp outside task')
    return {'raw_component_time': raw, 'exposed_critical_path_time': exposed, 'critical_path': list(path),
            'overlapped_or_noncritical_time': {k: value-exposed.get(k, 0) for k, value in raw.items()},
            'TUFR': None if useful_first is None else useful_first-submitted,
            'task_completion_time': finish-submitted,
            'unattributed_critical_time': finish-submitted-sum(exposed.values()),
            'TTFT_substituted_for_TUFR': False, 'speedups_multiplied': False}


def tool_overlap(tool_start, tool_end, decode_start, decode_end, *, used=True):
    for value in (tool_start, tool_end, decode_start, decode_end):
        finite(value)
    if tool_end < tool_start or decode_end < decode_start:
        raise ValueError('negative tool/decode span')
    overlap = max(0., min(tool_end, decode_end)-max(tool_start, decode_start))
    total = tool_end-tool_start
    return {'total_tool_latency': total, 'exposed_tool_latency': total-overlap,
            'overlapped_tool_latency': overlap, 'wasted_speculation': 0. if used else total}
