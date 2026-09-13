"""Deterministic trace replay and a common-denominator A0-A11 ablation harness."""
from dataclasses import asdict, dataclass
from bisect import bisect_right
import heapq
from .contracts import digest, finite, integer, nonempty
from .thermal import quantiles
from .agent import tool_overlap

ABLATIONS = ('baseline', 'retrieval', 'residency', 'program-scheduling', 'kv-reuse', 'multi-tier-kv',
             'tool-overlap', 'syscore', 'numa-io-qos', 'thermal-power', 'ce-advice', 'full-stack')


@dataclass(frozen=True)
class AgentTaskTrace:
    task_id: str
    user: str
    session: str
    arrival: float
    retrieval: float
    context_assembly: float
    prefill: float
    decode: float
    tool: float
    storage: float
    prefix_identity: str
    memory_evidence_recall: float | None = None
    task_success: bool | None = None
    tokens: int | None = None

    def __post_init__(self):
        for name in ('task_id', 'user', 'session', 'prefix_identity'):
            nonempty(getattr(self, name))
        for name in ('arrival', 'retrieval', 'context_assembly', 'prefill', 'decode', 'tool', 'storage'):
            finite(getattr(self, name))
        if self.memory_evidence_recall is not None and not 0 <= self.memory_evidence_recall <= 1:
            raise ValueError('invalid evidence recall')


class AgentSystemsSimulator:
    def __init__(self, *, concurrency=2, topology_events=(), thermal_trace=()):
        integer(concurrency, minimum=1, maximum=128)
        self.concurrency = concurrency
        self.topology_events = tuple(topology_events)
        self.thermal_trace = tuple(thermal_trace)
        if len(self.topology_events) > 10000 or len(self.thermal_trace) > 10000:
            raise ValueError('trace bound')
        for row in self.topology_events:
            finite(row['time'])
            if row['state'] not in ('online', 'lost', 'recovering'):
                raise ValueError('invalid replay topology event')
        for row in self.thermal_trace:
            finite(row['time'])
            finite(row['service_multiplier'], minimum=1.)

    def replay(self, tasks, *, ablation=0, full_research=False):
        tasks = tuple(tasks)
        integer(ablation, maximum=11)
        if len(tasks) > (1000000 if full_research else 2048) or not tasks:
            raise ValueError('bounded trace required; large runs need --full-research')
        if len({t.task_id for t in tasks}) != len(tasks):
            raise ValueError('duplicate task denominator')
        workers = [(0., i) for i in range(self.concurrency)]
        heapq.heapify(workers)
        prefix_ready = {}
        topology = sorted(self.topology_events,key=lambda row:row['time'])
        topology_times = [row['time'] for row in topology]
        rows = []
        for task in sorted(tasks, key=lambda t: (t.arrival, t.task_id)):
            available, worker = heapq.heappop(workers)
            start = max(task.arrival, available)
            queue = start-task.arrival
            epoch_start = bisect_right(topology_times,start)
            fallback = bool(epoch_start and topology[epoch_start-1]['state'] != 'online')
            key = (task.user,task.session,task.prefix_identity,epoch_start)
            ready = prefix_ready.get(key)
            reuse = ablation >= 4 and ready is not None and ready <= start and not fallback
            # Each trace supplies measured/scenario durations; no universal speedup factor.
            prefill = 0. if reuse else task.prefill
            overlap = min(task.tool, task.decode) if ablation >= 6 else 0.
            duration = task.retrieval+task.context_assembly+prefill+task.decode+task.tool+task.storage-overlap
            thermal = [r for r in self.thermal_trace if r['time'] <= start]
            multiplier = max(thermal, key=lambda r:r['time'])['service_multiplier'] if thermal else 1.
            duration *= multiplier
            finish = start+duration
            epoch_finish = bisect_right(topology_times,finish)
            if epoch_finish != epoch_start:
                fallback = True
                if reuse:
                    # Epoch changes invalidate in-flight device output and KV.
                    # Recomputing prefill can expose further topology events.
                    reuse = False
                    prefill = task.prefill
                    duration += prefill*multiplier
                    finish = start+duration
                    epoch_finish = bisect_right(topology_times,finish)
            if not fallback:
                # Conservatively publish reusable state only at task completion.
                # Scheduling a producer does not make its future state readable.
                prefix_ready[key] = min(prefix_ready.get(key,finish),finish)
            heapq.heappush(workers, (finish, worker))
            rows.append({'task_id': task.task_id, 'user': task.user, 'session': task.session,
                'queue_wait': queue, 'task_completion_time': finish-task.arrival,
                'TUFR': None, 'TUFR_reason': 'trace lacks explicit useful-output marker',
                'TTFT': queue+(task.retrieval+task.context_assembly+prefill)*multiplier,
                'kv_action': 'reuse' if reuse else 'recompute', 'kv_tier': 'HBM' if reuse else 'recompute',
                'prefix_available_at_start': ready if ready is not None and ready<=start and not fallback else None,
                'start':start,'finish':finish,'topology_epoch_start':epoch_start,'topology_epoch_finish':epoch_finish,
                'topology_events_during_task':epoch_finish-epoch_start,
                'tool_exposed_latency': (task.tool-overlap)*multiplier, 'fallback_count': int(fallback),
                'memory_evidence_recall': task.memory_evidence_recall, 'task_success': task.task_success,
                'tokens': task.tokens, 'energy_per_task': None, 'thermal_multiplier': multiplier})
        elapsed = max(t[0] for t in workers)-min(t.arrival for t in tasks)
        return {'schema': 'thm-agent-systems-simulation/1', 'ablation': 'A'+str(ablation),
            'ablation_name': ABLATIONS[ablation], 'task_denominator_sha256': digest([t.task_id for t in tasks]),
            'task_count': len(tasks), 'trace_sha256': digest([asdict(t) for t in tasks]),
            'evidence': 'simulated', 'hardware_acceptance': False, 'agent_outcome_accepted': False,
            'rows': rows, 'latency': quantiles(r['task_completion_time'] for r in rows),
            'system_throughput': len(tasks)/elapsed if elapsed else None,
            'per_user_progress': {u: sum(r['user'] == u for r in rows) for u in sorted({t.user for t in tasks})},
            'CPU_utilization': None, 'GPU_utilization': None, 'RAM': None, 'VRAM': None, 'storage_io': None,
            'fallback_count': sum(r['fallback_count'] for r in rows), 'failure_count': 0, 'recovery_time': None,
            'applied_components': [name for n, name in enumerate(ABLATIONS) if n <= ablation and n in (0,4,6)],
            'unavailable_or_trace_supplied_components': [name for n, name in enumerate(ABLATIONS) if n <= ablation and n not in (0,4,6)],
            'simulated_scenarios_are_not_measured_speedups': True}

    def ablation_ladder(self, tasks):
        tasks = tuple(tasks)
        runs = [self.replay(tasks, ablation=n) for n in range(12)]
        assert len({r['task_denominator_sha256'] for r in runs}) == 1
        return runs
