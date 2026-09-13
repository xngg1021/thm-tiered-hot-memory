"""Exposure-specific survival and bounded software aging; never hardware lifetime claims."""
from dataclasses import asdict, dataclass, field
import math
from statistics import NormalDist
from thm.systems.contracts import finite, integer, nonempty

EXPOSURES = ('wall_seconds', 'requests', 'sessions', 'mutations', 'migrations', 'topology_events', 'provider_executions')
FAILURES = {'F0': 'integrity', 'F1': 'semantic', 'F2': 'availability', 'F3': 'performance', 'F4': 'recovery'}
FAULTS = ('session-churn', 'source-mutation', 'migration-storm', 'topology-flap', 'provider-crash',
          'worker-hang', 'short-write', 'disk-full', 'corruption', 'stale-profile', 'clock-jump',
          'out-of-order-events', 'sleep-wake', 'storage-disappearance')


@dataclass(frozen=True)
class LifeObservation:
    run_id: str
    exposure: float
    failed: bool
    exposure_unit: str = 'requests'
    recovery_seconds: float | None = None
    failure_class: str | None = None

    def __post_init__(self):
        nonempty(self.run_id)
        finite(self.exposure)
        if self.exposure_unit not in EXPOSURES or type(self.failed) is not bool:
            raise ValueError('invalid exposure/censoring')
        if self.failed and self.failure_class not in FAILURES:
            raise ValueError('failure classification required')
        if not self.failed and self.failure_class is not None:
            raise ValueError('censored observation cannot carry failure')
        if self.recovery_seconds is not None:
            finite(self.recovery_seconds)
            if not self.failed:
                raise ValueError('recovery requires a failure')


def survival(observations, *, confidence=.95, min_runs=20, min_failures=5, evidence='simulated'):
    observations = tuple(observations)
    if not observations or len(observations) > 1000000:
        raise ValueError('bounded nonempty life observations required')
    if len({r.run_id for r in observations}) != len(observations) or len({r.exposure_unit for r in observations}) != 1:
        raise ValueError('distinct runs and a single exposure clock required')
    if not 0 < confidence < 1 or min_runs < 20 or min_failures < 5:
        raise ValueError('insufficient reporting policy')
    if evidence not in ('simulated', 'hardware-observed', 'production-observed', 'callable-fixture'):
        raise ValueError('evidence class required')
    z = NormalDist().inv_cdf((1+confidence)/2)
    grouped = {}
    for row in observations:
        grouped.setdefault(row.exposure, []).append(row)
    risk, estimate, greenwood, prior, restricted_mean = len(observations), 1., 0., 0., 0.
    curve = []
    for exposure, rows in sorted(grouped.items()):
        failures = sum(row.failed for row in rows)
        censored = len(rows)-failures
        restricted_mean += estimate*(exposure-prior)
        prior = exposure
        hazard = failures/risk
        if failures:
            estimate *= 1-hazard
            if risk > failures:
                greenwood += failures/(risk*(risk-failures))
        if 0 < estimate < 1:
            error = math.sqrt(greenwood)/abs(math.log(estimate))
            center = math.log(-math.log(estimate))
            low = math.exp(-math.exp(min(700, center+z*error)))
            high = math.exp(-math.exp(max(-700, center-z*error)))
        else:
            low = high = estimate
        curve.append({'exposure': exposure, 'at_risk': risk, 'failures': failures, 'censored': censored,
                      'survival': estimate, 'discrete_hazard': hazard, 'pointwise_ci': [low, high]})
        risk -= len(rows)
    count = sum(row.failed for row in observations)
    sufficient = len(observations) >= min_runs and count >= min_failures
    bx = {}
    for name, probability in (('B0.1', .001), ('B1', .01), ('B10', .1), ('B50', .5)):
        crossing = next((row['exposure'] for row in curve if row['survival'] <= 1-probability), None)
        bx[name] = crossing if sufficient else None
    recoveries = [r.recovery_seconds for r in observations if r.recovery_seconds is not None]
    exposure_total = sum(r.exposure for r in observations)
    return {'schema': 'thm-survival/1', 'method': 'Kaplan-Meier', 'evidence': evidence,
        'exposure_unit': observations[0].exposure_unit, 'runs': len(observations), 'failures': count,
        'right_censored_runs': len(observations)-count, 'confidence': confidence, 'curve': curve,
        'life_quantiles': bx, 'quantiles_sufficient': sufficient, 'Weibull': None,
        'MTTF': sum(r.exposure for r in observations)/len(observations) if sufficient and count == len(observations) else None,
        'restricted_mean_lifetime': restricted_mean, 'restriction_horizon': max(grouped),
        'MTBF': None, 'MTBF_reason': 'first-failure runs do not establish a recurrent repair process',
        'MTTR': sum(recoveries)/len(recoveries) if len(recoveries) >= min_failures else None,
        'failure_free_demonstrated_exposure': exposure_total if not count else None,
        'zero_failure_poisson_rate_upper': -math.log(1-confidence)/exposure_total if not count and exposure_total else None,
        'confidence_bound_assumption': 'constant independent Poisson failures; conditional bound, not a fitted lifetime model',
        'hardware_acceptance': False}


@dataclass(frozen=True)
class ReliabilityReceipt:
    commit: str
    tree: str
    platform: str
    hardware: dict
    workload: str
    fault_model: tuple[str, ...]
    seed: int
    exposure: dict
    failures: tuple[dict, ...]
    censored_runs: int
    confidence: float = .95
    evidence: str = 'simulated'

    def public(self):
        for value in (self.commit, self.tree):
            if len(value) != 40 or any(x not in '0123456789abcdef' for x in value):
                raise ValueError('exact Git identities required')
        if not set(self.exposure) <= set(EXPOSURES) or not set(self.fault_model) <= set(FAULTS):
            raise ValueError('unknown exposure/fault model')
        for value in self.exposure.values():
            finite(value)
        for failure in self.failures:
            if failure.get('class') not in FAILURES:
                raise ValueError('unknown failure class')
        return {'schema': 'thm-reliability/1', **asdict(self), 'hardware_acceptance': False}


class SelfVerificationEpochs:
    KINDS = ('request', 'session', 'mutation', 'topology', 'soak', 'release')

    def __init__(self, *, cadence=64):
        integer(cadence, minimum=1, maximum=10000)
        self.cadence = cadence
        self.counts = {kind: 0 for kind in self.KINDS}

    def check(self, kind, invariants):
        if kind not in self.counts:
            raise ValueError('unknown verification epoch')
        self.counts[kind] += 1
        if len(invariants)>64:
            raise ValueError('self-check invariant bound')
        due = True
        failures = [name for name, check in invariants.items() if not check()] if due else []
        return {'epoch': kind, 'count': self.counts[kind], 'checked': due, 'failures': failures, 'passed': not failures,
                'deep_check_due':kind!='request' or self.counts[kind]%self.cadence==0}

    def adapt(self, report):
        if report.get('runs', 0) >= 20 and report.get('failures', 0) >= 5:
            recent = report['curve'][-5:]
            self.cadence = 16 if any(row['discrete_hazard'] > .1 for row in recent) else 64
        return self.cadence


def recurrent_metrics(*, uptime, failures, recoveries, exposure_unit='wall_seconds', evidence='simulated'):
    finite(uptime)
    integer(failures)
    if exposure_unit not in EXPOSURES or evidence not in ('simulated','hardware-observed','production-observed'):
        raise ValueError('explicit exposure and evidence class required')
    recoveries=tuple(finite(v) for v in recoveries)
    if len(recoveries)>failures:
        raise ValueError('more recoveries than failures')
    return {'MTBF':uptime/failures if failures>=5 else None,
            'MTTR':sum(recoveries)/len(recoveries) if len(recoveries)>=5 else None,
            'uptime':uptime,'failures':failures,'exposure_unit':exposure_unit,'evidence':evidence,
            'repair_process':'recurrent','hardware_acceptance':False}


def accelerated_life(workload, *, events=128, seed=0, full_research=False):
    """Inject faults through the real workload's contract; record failed invariants."""
    import random
    integer(events, minimum=1, maximum=10000000 if full_research else 2048)
    integer(seed)
    rng = random.Random(seed)
    rows, failures = [], []
    for index in range(events):
        fault = FAULTS[index % len(FAULTS)] if index < len(FAULTS) else rng.choice(FAULTS)
        result = workload(fault, index, rng)
        if not isinstance(result, dict) or type(result.get('recovered')) is not bool:
            raise ValueError('workload must return recovery evidence')
        row = {'sequence': index, 'fault': fault, **result}
        rows.append(row)
        if not result['recovered']:
            failures.append({'class': result.get('class', 'F4'), 'sequence': index, 'fault': fault})
    return {'schema': 'thm-accelerated-life/1', 'evidence': 'simulated', 'seed': seed,
            'events': events, 'fault_model': list(FAULTS), 'invariant_failures': failures,
            'rows': rows, 'hardware_acceptance': False, 'production_MTBF': None}
