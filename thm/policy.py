"""Measured alternatives to the legacy activity curve; no silent policy migration.

Old evidence stays retrievable regardless of age. These curves affect residency
proposals only. Mention/display/retrieval events never become successful uses.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date
import math
import random
import re

WEIGHTS = {'hit': 2.0, 'confirm': 1.5, 'create': 1.0,
           'display': 0.0, 'retrieve': 0.0, 'promote': 0.0,
           'demote': 0.0, 'mention_observed': 0.0}


@dataclass(frozen=True)
class Policy:
    kernel: str = 'bounded_power'
    half_life: float = 30.0
    exponent: float = 0.5
    window_days: int = 180
    daily_cap: float = 2.0

    def __post_init__(self):
        if self.kernel not in ('legacy', 'power', 'exponential', 'mixture', 'bounded_power', 'lru', 'lfu'):
            raise ValueError('unknown decay policy')
        if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0
               for x in (self.half_life, self.exponent, self.daily_cap)):
            raise ValueError('curve parameters must be finite and positive')
        if (self.half_life > 36500 or not .1 <= self.exponent <= 4
                or type(self.window_days) is not int or not 1 <= self.window_days <= 36500):
            raise ValueError('curve parameters outside supported range')


def kernel(age, policy):
    if not math.isfinite(age) or age < 0:
        raise ValueError('negative/nonfinite age')
    if policy.kernel == 'legacy':
        return (age+1) ** -.5
    if policy.kernel == 'exponential':
        return 2 ** (-age/policy.half_life)
    if policy.kernel == 'mixture':
        return .7 * 2 ** (-age/policy.half_life) + .3 * 2 ** (-age/(policy.half_life*4))
    if policy.kernel == 'bounded_power' and age > policy.window_days:
        return 0.0
    tau = policy.half_life / (2 ** (1/policy.exponent)-1)
    return (1+age/tau) ** (-policy.exponent)


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('dates must use YYYY-MM-DD')
    return date.fromisoformat(value)


def activity(entry, now: date, policy: Policy):
    if not isinstance(entry, dict) or not isinstance(entry.get('events', []), list):
        raise ValueError('events must be a list')
    daily, seen = {}, set()
    for event in entry.get('events', []):
        if not isinstance(event, dict):
            raise ValueError('invalid event object')
        kind = event.get('type')
        if not isinstance(kind, str) or kind not in WEIGHTS:
            raise ValueError('unknown event type')
        stamp = _day(event.get('t'))
        age = (now-stamp).days
        if age < 0:
            raise ValueError('future event')
        key = event.get('event_id')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('missing/duplicate event ID')
        seen.add(key)
        evidence = event.get('evidence')
        if kind == 'confirm' and (not isinstance(evidence, str) or not evidence.strip()):
            if event.get('legacy_unverified') is True:
                continue
            raise ValueError('confirmation requires evidence')
        if WEIGHTS[kind]:
            daily[age] = daily.get(age, 0)+WEIGHTS[kind]
    if policy.kernel == 'lru':
        return 1/(1+min(daily)) if daily else 0.0
    if policy.kernel == 'lfu':
        return sum(daily.values())
    if policy.kernel in ('legacy', 'power', 'exponential', 'mixture'):
        return sum(weight*kernel(age, policy) for age, weight in daily.items())
    return sum(min(weight, policy.daily_cap)*kernel(age, policy) for age, weight in daily.items())


def plan(entries, now: date, budget: int, policy: Policy, cost: callable):
    """Deterministic greedy value/cost packing, not a claimed knapsack optimum."""
    if type(budget) is not int or budget < 0:
        raise ValueError('invalid residency budget')
    eligible, excluded, seen = [], [], set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not entry['id'].strip():
            raise ValueError('valid entry ID required')
        key = entry['id']
        if key in seen:
            raise ValueError('duplicate entry ID')
        seen.add(key)
        if type(entry.get('pinned', False)) is not bool:
            raise ValueError('pinned must be boolean')
        if entry.get('cost_class', 'med') not in ('low', 'med', 'high'):
            raise ValueError('invalid cost class')
        if entry.get('status') not in ('active', 'invalid', 'deleted', 'unresolved_legacy'):
            raise ValueError('invalid entry status')
        if (entry.get('valid_from') and entry.get('valid_until')
                and _day(entry['valid_from']) >= _day(entry['valid_until'])):
            raise ValueError('invalid validity interval')
        if (entry.get('status') != 'active'
            or (entry.get('valid_from') and now < _day(entry['valid_from']))
            or (entry.get('valid_until') and now >= _day(entry['valid_until']))):
            excluded.append(key)
            continue
        units = cost(entry)
        if type(units) is not int or units < 1:
            raise ValueError('cost must be a positive integer')
        score = activity(entry, now, policy)
        # Bounded cost-class preference; it cannot confer truth or permanent residency.
        multiplier = {'low': 1, 'med': 1.25, 'high': 1.5}[entry.get('cost_class', 'med')]
        eligible.append((entry, units, score*multiplier))
    fixed = [x for x in eligible if x[0].get('pinned')]
    used = sum(x[1] for x in fixed)
    if used > budget:
        return {'status': 'PINNED_OVER_BUDGET', 'required': used, 'budget': budget,
                'selected': [], 'excluded': excluded, 'changes_applied': False}
    selected = [x[0]['id'] for x in sorted(fixed, key=lambda x: x[0]['id'])]
    for entry, units, score in sorted((x for x in eligible if not x[0].get('pinned')),
                                     key=lambda x: (-x[2]/x[1], x[0]['id'])):
        if score > 0 and used+units <= budget:
            selected.append(entry['id']); used += units
    return {'status': 'OK', 'selected': selected, 'excluded': excluded, 'budget': budget,
            'budget_used': used, 'policy': asdict(policy), 'changes_applied': False}


def replay(events, entries, policy, budget, cost):
    """Score before observing each use. Input is a real chronology, not QA evidence order."""
    import copy
    history = copy.deepcopy(entries)
    by_id = {e['id']: e for e in history}
    hits, total = 0, 0
    previous = None
    for ordinal, event in enumerate(events):
        stamp = _day(event.get('t'))
        if previous and stamp < previous:
            raise ValueError('replay must be chronological')
        previous = stamp
        entry = by_id[event['id']]
        result = plan(history, stamp, budget, policy, cost)
        if entry['id'] in result['selected']:
            hits += 1
        total += 1
        entry.setdefault('events', []).append({'type': 'hit', 't': stamp.isoformat(),
                                               'event_id': 'replay:'+str(ordinal)})
    return {'requests': total, 'residency_hits': hits, 'residency_hit_rate': hits/total if total else None}


def curve_report():
    ages = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]
    policies = [Policy(kernel=k) for k in ('legacy','power','exponential','mixture','bounded_power')]
    return {'ages_days': ages, 'curves': {p.kernel: [kernel(a,p) for a in ages] for p in policies},
            'parameters': [asdict(p) for p in policies],
            'note': 'Curves are normalized per event; policy is not selected from LoCoMo QA order.'}
