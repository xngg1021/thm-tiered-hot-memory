"""Conservative experimental temporal projection, independent of benchmark labels."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import calendar
import re

MONTHS = {name.lower(): n for n, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): n for n, name in enumerate(calendar.month_abbr) if name})
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7,
      '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}

@dataclass(frozen=True)
class Signal:
    year: int | None = None
    month: int | None = None
    day: int | None = None
    order: str = ''
    relative_unresolved: bool = False


def parse(query, anchor=None):
    """Do nothing on unsupported or ambiguous dates; never consult wall clock."""
    q = query.lower()
    if re.search(r'\b(yesterday|last week|two months ago)\b|昨天|上周|两个月前', q):
        if anchor is None:
            return Signal(relative_unresolved=True)
        if not isinstance(anchor, (date, datetime)):
            raise ValueError('explicit date anchor required')
        d = anchor.date() if isinstance(anchor, datetime) else anchor
        if re.search(r'yesterday|昨天', q):
            d -= timedelta(days=1)
            return Signal(d.year, d.month, d.day)
        if re.search(r'two months ago|两个月前', q):
            month_index = d.year * 12 + d.month - 3
            return Signal(month_index // 12, month_index % 12 + 1)
        return Signal(relative_unresolved=True)  # week range intentionally fail-soft
    order = ''
    if re.search(r'\b(first|earliest)\b|第一次|最早', q): order = 'first'
    if re.search(r'\b(latest|last|previous)\b|最近|上一次', q): order = 'latest'
    y = re.search(r'(?<!\d)([12]\d{3})(?!\d)', q)
    year = int(y[1]) if y else None
    month = day = None
    iso = re.search(r'(?<!\d)([12]\d{3})[-年](\d{1,2})(?:[-月](\d{1,2}))?', q)
    if iso:
        year, month = int(iso[1]), int(iso[2])
        day = int(iso[3]) if iso[3] else None
    else:
        for name, number in MONTHS.items():
            m = re.search(r'\b' + name + r'\b(?:\s+(\d{1,2})(?!\d))?', q)
            if m:
                month = number
                day = int(m[1]) if m[1] else None
                break
        zh = re.search(r'(\d{1,2}|十一|十二|[一二三四五六七八九十])月', q)
        if zh: month = int(zh[1]) if zh[1].isdigit() else CN[zh[1]]
    if month is not None:
        try: date(year or 2000, month, day or 1)
        except ValueError: return Signal()
    # Comparison/range syntax is not silently reinterpreted as date equality.
    if re.search(r'\b(before|after|between|from|earlier|later)\b|之前|之后|以前|到|至|[–—]', q):
        return Signal()
    return Signal(year, month, day, order)


def source_date(value):
    try: return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except ValueError: pass
    # Explicit source format, not an inferred event date.
    m = re.search(r'\b(\d{1,2}) ([A-Za-z]+), (\d{4})\b', value)
    if m and m[2].lower() in MONTHS:
        try: return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
        except ValueError: pass
    return None


def reorder(rows, query, weight=0.25):
    signal = parse(query)
    if signal.relative_unresolved or not any((signal.year, signal.month, signal.day)):
        return rows
    matched = []
    for row in rows:
        d = source_date(row['timestamp'])
        if d and all(v is None or getattr(d, field) == v
                     for field, v in [('year', signal.year), ('month', signal.month), ('day', signal.day)]):
            matched.append(row['rowid'])
    if not matched: return rows
    ranks = {rid: n for n, rid in enumerate(matched, 1)}
    scored = [(1 / (60 + n) + (weight / (60 + ranks[r['rowid']]) if r['rowid'] in ranks else 0), n, r)
              for n, r in enumerate(rows, 1)]
    return [r for _, _, r in sorted(scored, key=lambda x: (-x[0], x[1]))]
