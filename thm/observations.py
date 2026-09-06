"""Mention observations are weak evidence and NEVER become activity hits.

This file does not import or open the main index engine. Source evidence is kept
locally; CLI reports counts only unless detailed output was explicitly requested.
"""
from __future__ import annotations
from collections import Counter, deque
from datetime import timedelta
import re
import sqlite3
import time
from pathlib import Path
import json
from .retrieval import fingerprint
from .sources import epoch
from .sqlite_guard import connect_derived


def visible_text(text):
    """Remove quoted lines and both complete and unfinished Markdown fences."""
    if not isinstance(text, str):
        raise ValueError('record text must be a string')
    visible, fence_char, fence_len = [], None, 0
    for line in text.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence_char is None:
                fence_char, fence_len = token[0], len(token)
            elif token[0] == fence_char and len(token) >= fence_len:
                fence_char = None
            continue
        if fence_char is None and not line.lstrip().startswith('>'):
            visible.append(line)
    return '\n'.join(visible)


def _prepare_anchors(anchors):
    if not isinstance(anchors, list) or len(anchors) > 1000:
        raise ValueError('anchors must be a list of at most 1000 entries')
    prepared, ids = [], set()
    for spec in anchors:
        if (not isinstance(spec, dict) or not isinstance(spec.get('id'), str)
                or not spec['id'].strip() or not isinstance(spec.get('version'), str)
                or not spec['version'].strip() or not isinstance(spec.get('aliases'), list)):
            raise ValueError('anchor requires string id/version and a list of aliases')
        key = (spec['id'], spec['version'])
        if key in ids:
            raise ValueError('duplicate anchor identity')
        ids.add(key)
        ignore_case = spec.get('case_insensitive', False)
        if type(ignore_case) is not bool:
            raise ValueError('case_insensitive must be boolean')
        patterns, aliases = [], set()
        if not 1 <= len(spec['aliases']) <= 32:
            raise ValueError('anchor requires 1 to 32 aliases')
        for alias in spec['aliases']:
            if not isinstance(alias, str) or not 2 <= len(alias.strip()) <= 256 or alias != alias.strip():
                raise ValueError('anchors must be nontrivial trimmed literal strings')
            identity = alias.casefold() if ignore_case else alias
            if identity in aliases:
                continue
            aliases.add(identity)
            pattern = re.escape(alias)
            if alias[0].isascii() and alias[0].isalnum():
                pattern = r'(?<!\w)' + pattern
            if alias[-1].isascii() and alias[-1].isalnum():
                pattern += r'(?!\w)'
            patterns.append((alias, re.compile(pattern, re.IGNORECASE if ignore_case else 0)))
        required = spec.get('min_anchors', 1)
        if type(required) is not int or not 1 <= required <= len(patterns):
            raise ValueError('min_anchors must not exceed distinct aliases')
        lower = epoch(spec['valid_from']) if spec.get('valid_from') else None
        upper = epoch(spec['valid_until']) if spec.get('valid_until') else None
        if lower and upper and lower >= upper:
            raise ValueError('invalid anchor validity interval')
        prepared.append((spec, patterns, required, lower, upper))
    return prepared


def _tight_matches(patterns, text, required):
    occurrences, partial = [], False
    for alias, pattern in patterns:
        for number, match in enumerate(pattern.finditer(text)):
            if number >= 256:
                partial = True
                break
            occurrences.append((alias, match.start(), match.end()))
    occurrences.sort(key=lambda m: (m[1], m[2], m[0]))
    # Linear sliding window over bounded occurrences. Nested/repeated matches
    # cannot manufacture two independent anchors from one alias.
    window, counts, ends = deque(), Counter(), deque()
    for item in occurrences:
        if item[2]-item[1] > 200:
            continue
        window.append(item)
        counts[item[0]] += 1
        while ends and ends[-1][2] <= item[2]:
            ends.pop()
        ends.append(item)
        while window and ends[0][2]-window[0][1] > 200:
            old = window.popleft()
            counts[old[0]] -= 1
            if not counts[old[0]]:
                del counts[old[0]]
            if ends[0] == old:
                ends.popleft()
        if len(counts) >= required:
            distinct = {}
            for match in window:
                distinct.setdefault(match[0], match)
                if len(distinct) >= required:
                    return list(distinct.values()), partial
    return [], partial


def scan(records, anchors, *, scope, now, days=7, max_records=50000, max_bytes=25*1024*1024, timeout=10.0):
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError('observation scope required')
    now = epoch(now)
    if (type(days) is not int or not 1 <= days <= 90 or type(max_records) is not int
            or max_records < 1 or type(max_bytes) is not int or max_bytes < 1
            or type(timeout) not in (int, float) or not 0 < timeout <= 300):
        raise ValueError('invalid scan bounds')
    prepared = _prepare_anchors(anchors)
    cutoff = now-timedelta(days=days)
    deadline = time.monotonic()+timeout
    bytes_seen, partial_matching = 0, False
    observations, skipped, scanned = [], Counter(), 0
    seen = set()
    for record in records:
        if scanned >= max_records or time.monotonic() >= deadline:
            return observations, {'partial': True, 'scanned': scanned, 'skipped': dict(skipped), 'reason': 'record_or_time_limit'}
        scanned += 1
        if not isinstance(record, dict):
            raise ValueError('record must be a mapping')
        if record.get('role') != 'assistant' or str(record.get('source', '')).lower() in {'cron', 'review', 'test', 'flush', 'subagent', 'background'}:
            skipped['role_or_source'] += 1
            continue
        stamp = epoch(record['timestamp'])
        if not cutoff <= stamp <= now:
            skipped['outside_window'] += 1
            continue
        if not isinstance(record.get('text'), str):
            raise ValueError('record text must be a string')
        bytes_seen += len(record['text'].encode('utf-8'))
        if bytes_seen > max_bytes:
            return observations, {'partial': True, 'scanned': scanned, 'skipped': dict(skipped), 'reason': 'byte_limit'}
        text = visible_text(record['text'])
        if any(marker in text.lower() for marker in ('[thm context]', 'thm scan report', 'memory audit report')):
            skipped['self_echo'] += 1
            continue
        for spec, patterns, required, lower, upper in prepared:
            if time.monotonic() >= deadline:
                return observations, {'partial': True, 'scanned': scanned, 'skipped': dict(skipped), 'reason': 'time_limit'}
            if lower and stamp < lower or upper and stamp >= upper:
                continue
            matched, capped = _tight_matches(patterns, text, required)
            partial_matching = partial_matching or capped
            if not matched:
                continue
            versions = record.get('memory_versions', {})
            if not isinstance(versions, dict):
                raise ValueError('memory_versions must be a mapping')
            snapshot = versions.get(spec['id']) == spec['version']
            # A branch copying identical text remains one observation for that version.
            event_id = fingerprint([scope, spec['id'], spec['version'], text, stamp.isoformat()])
            if event_id in seen:
                continue
            seen.add(event_id)
            observations.append({'event_id': event_id, 'type': 'mention_observed', 'weight': 0.0,
                                 'scope': scope, 'entry_id': spec['id'], 'entry_version': spec['version'],
                                 'session_id': record['session'], 'message_id': record['id'],
                                 'timestamp': stamp.isoformat(), 'text_hash': fingerprint(text),
                                 'source_text_hash': fingerprint(record['text']), 'coordinate_space': 'filtered_text',
                                 'matches': [{'anchor': m[0], 'start': m[1], 'end': m[2]} for m in matched],
                                 'exposure': 'snapshot_matched' if snapshot else 'unknown',
                                 'usefulness': 'unverified', 'scanner_version': 2})
    return observations, {'partial': partial_matching, 'scanned': scanned, 'skipped': dict(skipped),
                          'bytes_scanned': bytes_seen, 'occurrence_limit_reached': partial_matching}


def store_observations(path, observations):
    """Validated zero-weight records in a dedicated sidecar; never adopt a source DB."""
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ValueError('symlink observation store refused')
    encoded = []
    for obs in observations:
        if (not isinstance(obs, dict) or obs.get('type') != 'mention_observed'
                or type(obs.get('weight')) not in (int, float) or obs['weight'] != 0
                or not isinstance(obs.get('event_id'), str) or not obs['event_id']):
            raise ValueError('only identified zero-weight mention observations can be stored')
        encoded.append((obs['event_id'], json.dumps(obs, ensure_ascii=False, sort_keys=True, allow_nan=False)))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect_derived(path, {'observations'})
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {'observations', 'sqlite_sequence'}:
            raise ValueError('observation output must be a dedicated database, not a source/index database')
        db.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        before = db.total_changes
        with db:
            db.executemany('INSERT OR IGNORE INTO observations VALUES(?,?)', encoded)
        return db.total_changes-before
    finally:
        db.close()


def summarize(observations):
    grouped = {}
    for obs in observations:
        item = grouped.setdefault((obs['entry_id'], obs['entry_version']), {'sessions': set(), 'days': set(), 'count': 0})
        item['sessions'].add(obs['session_id'])
        item['days'].add(epoch(obs['timestamp']).date().isoformat())
        item['count'] += 1
    return [{'id': key[0], 'version': key[1], 'mentions': val['count'],
             'sessions': len(val['sessions']), 'days': len(val['days']),
             'review_candidate': len(val['sessions']) >= 2 and len(val['days']) >= 2,
             'activity_change': 0.0} for key, val in sorted(grouped.items())]
