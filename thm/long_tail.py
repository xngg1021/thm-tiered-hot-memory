"""Deterministic temporal/event representations and bounded evidence selection.

Track A/0N uses source metadata and explicit relations. No gold enters serving.
Track B/0G permits local discriminative models through a separate adapter.
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import calendar
import math
import re
from typing import Protocol
from thm.systems.contracts import finite, integer, nonempty

GRANULARITIES = ('conversation', 'session', 'turn', 'segment', 'event', 'structured-fact', 'source')


@dataclass(frozen=True)
class TimeInterval:
    start: date
    end: date
    precision: str = 'day'

    def __post_init__(self):
        if self.end < self.start or self.precision not in ('day', 'month', 'year', 'range'):
            raise ValueError('invalid time interval')

    @classmethod
    def parse(cls, text, *, anchor=None):
        text = str(text).strip().lower()
        relative = {'today': 0, 'yesterday': -1, 'tomorrow': 1, '今天': 0, '昨天': -1, '明天': 1}
        if text in relative:
            if anchor is None:
                raise ValueError('relative date requires source anchor')
            value = anchor + timedelta(days=relative[text])
            return cls(value, value)
        match = re.fullmatch(r'(\d+)\s+(days?|weeks?)\s+(ago|later)', text)
        if match:
            if anchor is None:
                raise ValueError('relative date requires source anchor')
            delta = int(match[1])*(7 if match[2].startswith('week') else 1)*(-1 if match[3] == 'ago' else 1)
            value = anchor+timedelta(days=delta)
            return cls(value, value)
        if re.fullmatch(r'\d{4}', text):
            return cls(date(int(text), 1, 1), date(int(text), 12, 31), 'year')
        if re.fullmatch(r'\d{4}-\d{2}', text):
            year, month = map(int, text.split('-'))
            return cls(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), 'month')
        if '/' in text:
            left, right = text.split('/', 1)
            return cls(cls.parse(left, anchor=anchor).start, cls.parse(right, anchor=anchor).end, 'range')
        value = date.fromisoformat(text)
        return cls(value, value)

    def before(self, other):
        return self.end < other.start

    def after(self, other):
        return other.before(self)

    def overlaps(self, other):
        return self.start <= other.end and other.start <= self.end

    def same_day(self, other):
        return self.start == self.end == other.start == other.end


def age_arithmetic(birth, at):
    def age(b, a):
        return a.year-b.year-((a.month, a.day) < (b.month, b.day))
    if at.start < birth.end:
        raise ValueError('age interval precedes possible birth')
    return {'minimum_years': age(birth.end, at.start), 'maximum_years': age(birth.start, at.end),
            'precision': 'interval' if birth.start != birth.end or at.start != at.end else 'exact'}


@dataclass(frozen=True)
class Event:
    identity: str
    scope: str
    source_id: str
    source_sha256: str
    time: TimeInterval
    actors: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    predecessor: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    revoked: bool = False
    granularity: str = 'event'

    def __post_init__(self):
        for value in (self.identity, self.scope, self.source_id):
            nonempty(value)
        if len(self.source_sha256) != 64 or any(x not in '0123456789abcdef' for x in self.source_sha256):
            raise ValueError('source content identity required')
        if self.granularity not in GRANULARITIES:
            raise ValueError('invalid evidence granularity')
        if any(self.identity in values for values in (self.predecessor, self.supersedes, self.contradicts)):
            raise ValueError('self relation')


class EventGraph:
    def __init__(self, scope, events=()):
        self.scope = nonempty(scope)
        self.events = {}
        for event in events:
            self.add(event)

    def add(self, event):
        if event.scope != self.scope or event.identity in self.events or len(self.events) >= 100000:
            raise ValueError('scope/identity/event bound')
        self.events[event.identity] = event
        try:
            self._check_cycles()
        except BaseException:
            self.events.pop(event.identity)
            raise

    def _check_cycles(self):
        for relation in ('predecessor', 'supersedes'):
            indegree = {key: 0 for key in self.events}
            children = {key: [] for key in self.events}
            for key, event in self.events.items():
                for parent in getattr(event, relation):
                    if parent in self.events:
                        indegree[key] += 1
                        children[parent].append(key)
            available = [key for key, n in indegree.items() if not n]
            count = 0
            while available:
                key = available.pop()
                count += 1
                for child in children[key]:
                    indegree[child] -= 1
                    if not indegree[child]:
                        available.append(child)
            if count != len(self.events):
                raise ValueError('cyclic event relation')

    def select(self, operation, reference=None):
        rows = list(self.events.values())
        if operation in ('first', 'last'):
            if not rows:
                return ()
            edge = min(e.time.end for e in rows) if operation == 'first' else max(e.time.start for e in rows)
            rows = [e for e in rows if (e.time.start <= edge if operation == 'first' else e.time.end >= edge)]
        else:
            if reference is None:
                raise ValueError('temporal reference required')
            if operation in ('before', 'closest-before'):
                rows = [e for e in rows if e.time.before(reference)]
                if operation == 'closest-before' and rows:
                    edge = max(e.time.end for e in rows)
                    rows = [e for e in rows if e.time.end == edge]
            elif operation in ('after', 'closest-after'):
                rows = [e for e in rows if e.time.after(reference)]
                if operation == 'closest-after' and rows:
                    edge = min(e.time.start for e in rows)
                    rows = [e for e in rows if e.time.start == edge]
            elif operation in ('interval-overlap', 'date-range'):
                rows = [e for e in rows if e.time.overlaps(reference)]
            elif operation == 'same-day':
                rows = [e for e in rows if e.time.same_day(reference)]
            else:
                raise ValueError('unknown temporal operation')
        return tuple(sorted(rows, key=lambda e: (e.time.start, e.time.end, e.identity)))

    def claims(self):
        superseded = {key for e in self.events.values() for key in e.supersedes}
        return [{'identity': e.identity, 'source_id': e.source_id, 'source_sha256': e.source_sha256,
                 'state': 'revoked' if e.revoked else 'superseded' if e.identity in superseded else
                          'unresolved-conflict' if e.contradicts else 'source-claim',
                 'contradicts': list(e.contradicts), 'source_truth_adjudicated': False} for e in self.events.values()]

    def required_chain(self, identity, limit=64):
        integer(limit, minimum=1, maximum=1024)
        pending, seen = [identity], set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            if key not in self.events:
                raise ValueError('unresolved event relation')
            seen.add(key)
            if len(seen) > limit:
                raise ValueError('evidence chain bound')
            pending.extend(self.events[key].predecessor)
        return tuple(sorted((self.events[key] for key in seen), key=lambda e: (e.time.start, e.identity)))


def classify_query(query):
    rules = [('contradiction', r'contradict|conflict|矛盾|冲突'), ('update', r'correct|latest|instead|更正|最新|改为'),
             ('ordering', r'order|sequence|first|last|先后|顺序|最早|最后'),
             ('temporal', r'before|after|when|days|year|month|何时|之前|之后|多少天'),
             ('multi-hop', r'combine|together|both|总共|综合'), ('preference', r'prefer|usually|喜欢|习惯'),
             ('locator', r'where|file|path|哪个文件|路径'), ('entity', r'who|whose|谁')]
    return next((name for name, pattern in rules if re.search(pattern, query, re.I)), 'implicit')


@dataclass(frozen=True)
class EvidenceCandidate:
    identity: str
    cost: int
    value: float
    units: frozenset[str] = frozenset()
    required_set: frozenset[str] = frozenset()

    def __post_init__(self):
        nonempty(self.identity)
        integer(self.cost, maximum=1048576)
        finite(self.value)


def joint_select(candidates, budget, *, exact_limit=18):
    """Bounded exact subset search, then disclosed coverage-aware greedy fallback.

Costs include complete source wrappers. Required sets prevent incomplete groups
from silently receiving full credit. Values/units are serving features, not gold.
"""
    candidates = tuple(candidates)
    integer(budget, maximum=1048576)
    integer(exact_limit, maximum=18)
    if len(candidates) > 1000 or len({x.identity for x in candidates}) != len(candidates):
        raise ValueError('candidate bound or duplicate')
    def utility(rows):
        ids = {r.identity for r in rows}
        if any(not r.required_set <= ids for r in rows):
            return -1.
        return sum(r.value for r in rows) + len(set().union(*(r.units for r in rows)))
    if len(candidates) <= exact_limit:
        best, best_score, best_cost = (), 0., 0
        def visit(index, rows, cost):
            nonlocal best, best_score, best_cost
            score = utility(rows)
            if score > best_score or (score == best_score and cost < best_cost):
                best, best_score, best_cost = rows, score, cost
            if index == len(candidates):
                return
            visit(index+1, rows, cost)
            item = candidates[index]
            if cost+item.cost <= budget:
                visit(index+1, rows+(item,), cost+item.cost)
        visit(0, (), 0)
        return {'ids': tuple(r.identity for r in best), 'cost': best_cost, 'method': 'exact', 'value': best_score}
    chosen, cost = [], 0
    by_id = {r.identity: r for r in candidates}
    remaining = sorted(candidates, key=lambda r: (-r.value/max(1, r.cost), r.identity))
    for item in remaining:
        ids = {r.identity for r in chosen}
        pending, group = [item.identity], {}
        while pending:
            key = pending.pop()
            if key in ids or key in group:
                continue
            if key not in by_id:
                group = None
                break
            group[key] = by_id[key]
            pending.extend(by_id[key].required_set)
        if group and cost+sum(r.cost for r in group.values()) <= budget:
            chosen.extend(group.values())
            cost += sum(r.cost for r in group.values())
    return {'ids': tuple(r.identity for r in chosen), 'cost': cost, 'method': 'heuristic', 'value': utility(chosen)}


class DiscriminativeReranker(Protocol):
    """Track B/0G/0API contract; no generative extraction, rewrite or judge."""
    model_sha256: str
    family: str  # cross-encoder / late-interaction / learned-sparse
    def score(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]: ...
    def close(self): ...


def rerank_local(adapter, query, texts):
    if adapter.family not in ('cross-encoder', 'late-interaction', 'learned-sparse') or len(adapter.model_sha256) != 64:
        raise ValueError('invalid discriminative identity')
    if len(texts) > 256 or sum(len(s.encode()) for s in texts) > 1048576:
        raise ValueError('reranking bound')
    scores = tuple(adapter.score(query, tuple(texts)))
    if len(scores) != len(texts) or any(not math.isfinite(x) for x in scores):
        raise ValueError('invalid scores')
    return tuple(sorted(range(len(texts)), key=lambda i: (-scores[i], i)))


def ordering_metrics(expected, observed):
    expected, observed = tuple(expected), tuple(observed)
    if len(set(expected)) != len(expected) or len(set(observed)) != len(observed):
        raise ValueError('event ordering must contain unique identities')
    common = set(expected) & set(observed)
    gold = {key: i for i, key in enumerate(expected)}
    sequence = [gold[key] for key in observed if key in common]
    pairs = len(sequence)*(len(sequence)-1)//2
    concordant = sum(sequence[i] < sequence[j] for i in range(len(sequence)) for j in range(i+1, len(sequence)))
    return {'set_recall': len(common)/len(expected) if expected else None,
            'ordering_accuracy': concordant/pairs if pairs else None,
            'kendall_tau': 2*concordant/pairs-1 if pairs else None,
            'missing': sorted(set(expected)-common), 'extra': sorted(set(observed)-common), 'comparable_pairs': pairs}
