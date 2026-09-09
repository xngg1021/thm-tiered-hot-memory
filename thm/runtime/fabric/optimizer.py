"""Bounded deterministic execution decisions, independent of memory algorithms."""
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
import math
import statistics
import threading
import time
from .contracts import RuntimeSample, finite, identity


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values)-1, max(0, math.ceil(fraction*len(values))-1))] if values else None


class PassiveTelemetry:
    def __init__(self, max_samples=128, max_candidates=32):
        if not 3 <= max_samples <= 4096 or not 1 <= max_candidates <= 256:
            raise ValueError('telemetry bounds')
        self.limit = max_samples; self.max_candidates = max_candidates
        self.samples = {}; self.lock = threading.RLock()

    def observe(self, sample):
        if not isinstance(sample, RuntimeSample):
            raise TypeError('normalized sample required')
        key = (sample.candidate, sample.workload)
        with self.lock:
            if key not in self.samples:
                if len(self.samples) >= self.max_candidates:
                    self.samples.pop(next(iter(self.samples)))
                self.samples[key] = deque(maxlen=self.limit)
            self.samples[key].append(sample)

    def summary(self, candidate, workload):
        with self.lock:
            rows = list(self.samples.get((candidate, workload), ()))
        times = [r.latency_ms for r in rows if not r.error]
        if not times:
            return {'sample_count': 0}
        median = statistics.median(times)
        result = {'sample_count': len(times), 'p50': median, 'p95': percentile(times, .95),
                  'p99': percentile(times, .99), 'noise': statistics.median(abs(x-median) for x in times),
                  'failure_probability': sum(bool(r.error) for r in rows)/len(rows)}
        metrics = {'throughput': 'queries_per_second', 'cpu_seconds': 'cpu_seconds', 'gpu_seconds': 'gpu_seconds',
                   'ram': 'ram_peak', 'vram': 'vram_peak', 'transfer': 'host_device_bytes',
                   'io': 'bytes_read', 'startup': 'startup_ms', 'compile': 'compile_ms', 'energy': 'joules'}
        for key, source in metrics.items():
            values = [getattr(r, source) for r in rows]
            result[key] = statistics.median(values) if values and all(v is not None for v in values) else None
        return result


@dataclass(frozen=True)
class Candidate:
    provider: str
    index: str = 'exact-flat'
    device: str = 'cpu'
    precision: str = 'fp32'
    placement: str = 'dram'
    transfer: str = 'host'
    inference_provider: str = 'reference'
    parameters: tuple = ()
    workload: str = 'interactive'
    semantic_class: str = 'strict'

    @property
    def id(self):
        return identity(asdict(self))


class SemanticGuard:
    @staticmethod
    def eligible(candidate, policy):
        if policy in ('reference', 'auto-safe'):
            return candidate.precision == 'fp32' and candidate.semantic_class == 'strict' and candidate.index == 'exact-flat'
        return policy in ('auto-throughput', 'approximate-performance')

    @staticmethod
    def compare(reference, candidate, *, dimension=None):
        # No full text enters the resulting receipt.
        fields = ('generation', 'ranked_ids', 'budget', 'budget_used', 'complete_evidence_ids', 'context')
        same = all(reference.get(k) == candidate.get(k) for k in fields)
        selected = lambda r: [(x.get('id'), x.get('hash'), x.get('source'), x.get('complete')) for x in r.get('selected', ())]
        structure = same and selected(reference) == selected(candidate)
        numeric = None
        if dimension is not None:
            from ..autotune import numeric_guard
            left = reference.get('dense_scores'); right = candidate.get('dense_scores')
            valid = isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and bool(left)
            valid = valid and all(type(x) in (int, float) and math.isfinite(x) for x in left+right)
            delta = max((abs(a-b) for a,b in zip(left,right)), default=0) if valid else None
            tolerance = numeric_guard(dimension)
            numeric = {'max_score_abs_diff': delta, 'numeric_tolerance': tolerance,
                       'within_numeric_guard': bool(valid and delta <= tolerance)}
        return {'structural_retrieval_parity': structure,
                'semantic_admission': structure and (numeric is None or numeric['within_numeric_guard']),
                'numeric_parity': numeric, 'aggregate_quality_parity': None, 'comparison': 'observed-request-only'}


class MaterialGainGate:
    def __init__(self, *, relative_min=.05, absolute_min_ms=.25, min_samples=5, max_samples=64,
                 cooldown_seconds=60, hysteresis=.02, clock=time.monotonic):
        for value in (relative_min, absolute_min_ms, cooldown_seconds, hysteresis):
            finite(value, 'gain threshold')
        if not 3 <= min_samples <= max_samples <= 256:
            raise ValueError('bounded repeat count required')
        self.relative_min = relative_min; self.absolute_min = absolute_min_ms
        self.min_samples = min_samples; self.max_samples = max_samples
        self.cooldown = cooldown_seconds; self.hysteresis = hysteresis; self.clock = clock
        self.last_switch = None

    def evaluate(self, baseline, candidate, *, semantic=True, resources=None, limits=None):
        b = list(baseline)[-self.max_samples:]; c = list(candidate)[-self.max_samples:]
        for value in b+c:
            finite(value, 'latency', 0.000000001)
        if not b or not c:
            return {'decision': 'retain-current', 'materially_faster': False, 'reason': 'insufficient-samples'}
        bm = statistics.median(b); cm = statistics.median(c)
        # A deterministic dispersion envelope, not a statistical confidence interval.
        bm_noise = 1.4826 * statistics.median(abs(x-bm) for x in b)
        cm_noise = 1.4826 * statistics.median(abs(x-cm) for x in c)
        noise = 3 * (bm_noise + cm_noise)
        absolute = bm-cm; relative = absolute/bm; conservative = absolute-noise
        breaches = [k for k, v in (limits or {}).items()
                    if (resources or {}).get(k) is None or resources[k] > v]
        threshold = max(self.absolute_min, bm*(self.relative_min + (self.hysteresis if self.last_switch is not None else 0)))
        enough = min(len(b), len(c)) >= self.min_samples
        cooling = self.last_switch is not None and self.clock()-self.last_switch < self.cooldown
        admitted = semantic and enough and not breaches and not cooling and conservative > max(noise, threshold)
        return {'measured_faster': absolute > 0, 'relative_gain': relative, 'absolute_gain': absolute,
                'noise_floor': noise, 'conservative_gain': conservative,
                'confidence': 'deterministic-median-MAD-envelope', 'sample_count': min(len(b), len(c)),
                'materially_faster': bool(admitted), 'resource_tradeoff': breaches,
                'decision': 'accepted' if admitted else 'retain-current',
                'reason': 'semantic' if not semantic else 'resources' if breaches else
                'insufficient-samples' if not enough else 'hysteresis' if cooling else 'material-gain' if admitted else 'noise-or-trivial-gain'}

    def switched(self):
        self.last_switch = self.clock()


class ParetoFrontier:
    MINIMIZE = ('p50', 'p95', 'p99', 'cpu_seconds', 'gpu_seconds', 'ram', 'vram', 'transfer',
                'io', 'startup', 'compile', 'energy', 'failure_probability')

    @staticmethod
    def admissible(point, constraints):
        if not point.get('available', True) or not point.get('semantic_safe', False) or not point.get('local', True):
            return False
        return all(point.get(k) is not None and point[k] <= v for k, v in constraints.items())

    @classmethod
    def dominates(cls, a, b):
        if a.get('semantic_class') != b.get('semantic_class') or a.get('workload') != b.get('workload'):
            return False
        strict = False
        for metric in cls.MINIMIZE + ('throughput',):
            av, bv = a.get(metric), b.get(metric)
            if av is None and bv is None:
                continue
            if av is None or bv is None:
                return False  # Unknown cannot be converted into a free resource.
            if metric == 'throughput':
                av, bv = -av, -bv
            if av > bv:
                return False
            strict |= av < bv
        return strict

    def build(self, points, *, constraints=None, workload='interactive'):
        points = [p for p in points if p.get('workload') == workload and self.admissible(p, constraints or {})]
        return sorted([p for p in points if not any(self.dominates(q, p) for q in points)], key=lambda p: p['id'])


class PolicySelector:
    def predict(self, point, state):
        p95 = point.get('p95')
        if p95 is None:
            return None
        queue = max(0, state.get('queue_depth', 0)) * p95 / max(1, state.get('concurrency', 1))
        cold = (point.get('startup') or 0) if not state.get('model_warm', True) else 0
        compile_ms = (point.get('compile') or 0) if not state.get('provider_ready', True) else 0
        transfer = 0 if state.get('index_resident', True) else state.get('stage_ms')
        if transfer is None:
            return None
        return p95 + queue + cold + compile_ms + transfer

    def select(self, points, workload, state, *, constraints=None):
        eligible = []
        for p in ParetoFrontier().build(points, constraints=constraints, workload=workload):
            finish = self.predict(p, state.get(p['id'], {}))
            if finish is None or finish > state.get('slo_ms', float('inf')):
                continue
            eligible.append((p, finish))
        if not eligible:
            return None
        if workload == 'interactive':
            return min(eligible, key=lambda x: (x[1], x[0].get('cpu_seconds') or 0, x[0]['id']))[0]
        if workload == 'bulk':
            return min(eligible, key=lambda x: (-(x[0].get('throughput') or 0), x[1], x[0]['id']))[0]
        return min(eligible, key=lambda x: (x[0].get('energy', float('inf')) if x[0].get('energy') is not None else float('inf'),
                                            x[0].get('cpu_seconds') if x[0].get('cpu_seconds') is not None else float('inf'),
                                            -(x[0].get('throughput') or 0), x[0]['id']))[0]


class CandidatePlanner:
    def plan(self, candidates, *, policy, workload, required_bytes, memory_budget,
             observations=(), limit=2, update_rate=0):
        if not 1 <= limit <= 8:
            raise ValueError('exploration bound')
        known = {p['candidate']: p for p in observations}
        eligible = [c for c in candidates if c.workload == workload and SemanticGuard.eligible(c, policy)]
        def rank(c):
            fit = required_bytes <= memory_budget.get(c.device, 0)
            prior = known.get(identity(c.id), {})
            return (not fit, prior.get('material_gain_status') != 'accepted',
                    update_rate > 0 and c.index != 'exact-flat', c.index != 'exact-flat', c.id)
        ranked = sorted(eligible, key=rank)
        return [c for c in ranked if required_bytes <= memory_budget.get(c.device, 0)][:limit]


class RetrievalBudgetAdvisor:
    def advise(self, *, baseline_ms, optimized_ms, slo_ms, candidate_fanout):
        for value in (baseline_ms, optimized_ms, slo_ms, candidate_fanout):
            finite(value, 'advisor input')
        return {'shadow_only': True, 'automatic_policy_change': False,
                'headroom_ms': max(0, slo_ms-optimized_ms),
                'measured_runtime_dividend_ms': baseline_ms-optimized_ms,
                'current_candidate_fanout': candidate_fanout,
                'quality_at_fixed_latency': None,
                'required_evidence': 'independent same-protocol retrieval experiment'}
