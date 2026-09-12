"""Explicitly enabled residency placement transactions; automatic mutation is off.

The placement store is a host-consumable control-plane replica. Original memory
content, activity events and validity are never rewritten by this actuator.
"""
from dataclasses import asdict, dataclass
from datetime import date
import copy
import json
import sqlite3
import threading
import time

from ._residency_common import _entry_current
from .runtime.fabric.contracts import finite, identity


@dataclass(frozen=True)
class ActuatorPolicy:
    automatic_mutation: bool = False
    minimum_tasks: int = 20
    minimum_demands: int = 2
    minimum_gain_tokens: float = 1
    cooldown_seconds: float = 60
    maximum_prefetch_waste: float = .25
    maximum_context_pressure: float = .95

    def __post_init__(self):
        if type(self.automatic_mutation) is not bool:
            raise ValueError('explicit automatic flag required')
        for name in ('minimum_tasks', 'minimum_demands'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError('positive telemetry threshold required')
        for name in ('minimum_gain_tokens', 'cooldown_seconds', 'maximum_prefetch_waste', 'maximum_context_pressure'):
            finite(getattr(self, name), name)
        if self.maximum_prefetch_waste > 1 or self.maximum_context_pressure > 1:
            raise ValueError('fraction exceeds one')


class ResidencyPlacementStore:
    """Atomic versioned placements with a durable rollback journal and CAS."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.RLock()
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS placement_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS placement_audit (plan_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, before_json TEXT NOT NULL, after_sha TEXT NOT NULL, receipt TEXT NOT NULL);
        ''')

    def initialize(self, entries, *, generation):
        entries = copy.deepcopy(list(entries))
        ids = [e['id'] for e in entries]
        if len(ids) != len(set(ids)) or not generation:
            raise ValueError('unique entries and generation required')
        if any(e.get('tier') not in ('T0', 'T1', 'T2', 'T3') for e in entries):
            raise ValueError('invalid THM tier')
        payload = {'generation': generation, 'entries': entries, 'last_change': {}}
        with self.lock:
            self.db.execute('INSERT INTO placement_state VALUES (1,0,?)', (json.dumps(payload, allow_nan=False),))

    def snapshot(self):
        with self.lock:
            row = self.db.execute('SELECT revision,payload FROM placement_state WHERE id=1').fetchone()
            if row is None:
                raise ValueError('placement store not initialized')
            data = json.loads(row[1])
            return {**data, 'revision': row[0], 'snapshot_sha256': identity(data)}

    def commit(self, plan, receipt, *, now, guard):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = self.snapshot()
                if (old['revision'], old['snapshot_sha256']) != (plan['revision'], plan['snapshot_sha256']):
                    raise ValueError('placement snapshot changed')
                guard(old)  # revalidate source/validity while placement is locked
                before = {k: v for k, v in old.items() if k not in ('revision', 'snapshot_sha256')}
                after = copy.deepcopy(before)
                rows = {e['id']: e for e in after['entries']}
                for item, target in plan['moves'].items():
                    rows[item]['tier'] = target
                    after['last_change'][item] = now
                raw = json.dumps(after, sort_keys=True, allow_nan=False)
                self.db.execute('UPDATE placement_state SET revision=revision+1,payload=? WHERE id=1', (raw,))
                self.db.execute('INSERT INTO placement_audit VALUES (?,?,?,?,?)',
                                (plan['plan_id'], old['revision']+1, json.dumps(before), identity(after), json.dumps(receipt)))
                self.db.execute('COMMIT')
            except Exception:
                self.db.execute('ROLLBACK')
                raise

    def rollback(self, plan_id):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT revision,before_json,after_sha FROM placement_audit WHERE plan_id=?', (plan_id,)).fetchone()
                current = self.snapshot()
                if row is None or current['revision'] != row[0] or current['snapshot_sha256'] != row[2]:
                    raise ValueError('rollback would overwrite intervening placement')
                self.db.execute('UPDATE placement_state SET revision=revision+1,payload=? WHERE id=1', (row[1],))
                self.db.execute('COMMIT')
            except Exception:
                self.db.execute('ROLLBACK')
                raise
            return {'status': 'rolled-back', 'plan_id': plan_id, 'revision': current['revision']+1}

    def audit(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute('SELECT receipt FROM placement_audit ORDER BY revision')]

    def close(self):
        self.db.close()


class ResidencyActuator:
    def __init__(self, store, *, policy=ActuatorPolicy(), source_is_current, clock=time.time, today=date.today):
        if not callable(source_is_current):
            raise TypeError('authoritative source validation callback required')
        self.store, self.policy, self.source_is_current, self.clock, self.today = store, policy, source_is_current, clock, today

    def propose(self, shadow, *, context_pressure, prefetch_waste):
        finite(context_pressure, 'context pressure')
        finite(prefetch_waste, 'prefetch waste')
        if max(context_pressure, prefetch_waste) > 1:
            raise ValueError('fraction exceeds one')
        snapshot = self.store.snapshot()
        current = {e['id']: e for e in snapshot['entries']}
        moves = {item: 'T1' for item in shadow.get('evict', [])}
        moves.update({item: 'T0' for item in shadow.get('admit', [])})
        reasons = []
        if shadow.get('status') != 'OK' or shadow.get('tasks_observed', 0) < self.policy.minimum_tasks:
            reasons.append('insufficient-telemetry')
        if shadow.get('review_required'):
            reasons.append('unresolved-shadow-guard')
        if prefetch_waste > self.policy.maximum_prefetch_waste:
            reasons.append('prefetch-pollution')
        if context_pressure > self.policy.maximum_context_pressure and any(t == 'T0' for t in moves.values()):
            reasons.append('context-pressure')
        metrics = {r['item_id']: r for r in shadow.get('rows', [])}
        gain = 0
        for item, target in moves.items():
            entry, row = current.get(item), metrics.get(item)
            if entry is None or row is None:
                reasons.append('unknown-entry-or-cost:' + item)
                continue
            if entry.get('pinned') or not _entry_current(entry, self.today()) or not self.source_is_current(entry):
                reasons.append('source-validity-pin:' + item)
            if self.clock()-snapshot['last_change'].get(item, float('-inf')) < self.policy.cooldown_seconds:
                reasons.append('cooldown:' + item)
            if row.get('stale_resident_failures'):
                reasons.append('stale:' + item)
            if target == 'T0' and row.get('observed_need_events', 0) < self.policy.minimum_demands:
                reasons.append('minimum-demand:' + item)
            value = row.get('net_token_value_horizon')
            if type(value) not in (int, float):
                reasons.append('unknown-objective:' + item)
            else:
                finite(abs(value), 'token objective')
                gain += value if target == 'T0' else -value
        if gain < self.policy.minimum_gain_tokens:
            reasons.append('hysteresis-token-objective')
        costs = {item: row.get('resident_units') for item, row in metrics.items()}
        selected = [item for item, entry in current.items() if moves.get(item, entry['tier']) == 'T0']
        if any(type(costs.get(item)) is not int or costs[item] <= 0 for item in selected):
            reasons.append('unknown-capacity')
        elif type(shadow.get('budget')) is not int or sum(costs[item] for item in selected) > shadow['budget']:
            reasons.append('capacity')
        value = {'schema': 'thm-actuator-plan/1', 'revision': snapshot['revision'], 'snapshot_sha256': snapshot['snapshot_sha256'],
                 'generation': snapshot['generation'], 'moves': moves, 'policy_sha256': identity(asdict(self.policy)),
                 'shadow_sha256': identity(shadow), 'gain_tokens': gain, 'reasons': sorted(set(reasons)),
                 'context_pressure': context_pressure, 'prefetch_waste': prefetch_waste,
                 'approved_to_execute': not reasons, 'source_mutation': False}
        return {**value, 'plan_id': identity(value)}

    def execute(self, plan, shadow, *, mode='dry-run', approved_plan_id=None, accepted_evidence=None):
        if mode not in ('dry-run', 'approval', 'automatic'):
            raise ValueError('invalid actuator mode')
        body = {k: v for k, v in plan.items() if k != 'plan_id'}
        if identity(body) != plan.get('plan_id'):
            raise ValueError('tampered actuator plan')
        fresh = self.propose(shadow, context_pressure=plan['context_pressure'], prefetch_waste=plan['prefetch_waste'])
        if fresh != plan:
            raise ValueError('stale actuator plan')
        if mode != 'dry-run' and not plan['approved_to_execute']:
            raise ValueError('actuator gates rejected')
        if mode == 'approval' and approved_plan_id != plan['plan_id']:
            raise PermissionError('exact plan approval required')
        if mode == 'automatic':
            evidence = accepted_evidence or {}
            if not self.policy.automatic_mutation or evidence.get('policy_sha256') != plan['policy_sha256'] or evidence.get('generation') != plan['generation'] or evidence.get('status') != 'task-outcome-accepted':
                raise PermissionError('automatic actuator requires explicit policy and matching accepted evidence')
        value = {'schema': 'thm-actuator-receipt/1', 'plan_id': plan['plan_id'], 'mode': mode,
                 'changes_applied': mode != 'dry-run', 'moves': plan['moves'], 'source_mutation': False,
                 'activity_mutation': False, 'validity_mutation': False, 'evidence': 'execution-only; no quality claim'}
        receipt = {**value, 'receipt_sha256': identity(value)}
        if mode != 'dry-run':
            def guard(snapshot):
                rows = {e['id']: e for e in snapshot['entries']}
                if any(not _entry_current(rows[i], self.today()) or rows[i].get('pinned') or not self.source_is_current(rows[i]) for i in plan['moves']):
                    raise ValueError('source authority changed at commit')
            self.store.commit(plan, receipt, now=self.clock(), guard=guard)
        return receipt

    def replay(self, scenarios):
        """Evaluate bounded proposals without modifying the real placement store."""
        scenarios = list(scenarios)
        if len(scenarios) > 256:
            raise ValueError('bounded replay required')
        return [self.propose(**scenario) for scenario in scenarios]
