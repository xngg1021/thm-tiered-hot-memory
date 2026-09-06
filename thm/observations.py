"""Mention observations are weak evidence and NEVER become activity hits.

This file does not import or open the main index engine. Source evidence is kept
locally; CLI reports counts only unless detailed output was explicitly requested.
"""
from __future__ import annotations
from collections import Counter
from datetime import timedelta
import re
import sqlite3
from .retrieval import fingerprint
from .sources import epoch
from .sqlite_guard import connect_derived


def visible_text(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('>'))


def scan(records, anchors, *, scope, now, days=7, max_records=50000):
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError('observation scope required')
    now = epoch(now)
    if not 1 <= days <= 90 or max_records < 1:
        raise ValueError('invalid scan bounds')
    cutoff = now-timedelta(days=days)
    observations, skipped, scanned = [], Counter(), 0
    seen = set()
    for record in records:
        if scanned >= max_records:
            return observations, {'partial': True, 'scanned': scanned, 'skipped': dict(skipped)}
        scanned += 1
        if record.get('role') != 'assistant' or record.get('source') in {'cron', 'review', 'test', 'flush', 'subagent'}:
            skipped['role_or_source'] += 1
            continue
        stamp = epoch(record['timestamp'])
        if not cutoff <= stamp <= now:
            skipped['outside_window'] += 1
            continue
        text = visible_text(record['text'])
        if any(marker in text.lower() for marker in ('[thm context]', 'thm scan report', 'memory audit report')):
            skipped['self_echo'] += 1
            continue
        for spec in anchors:
            if not isinstance(spec.get('aliases'), list) or not spec.get('id') or not spec.get('version'):
                raise ValueError('anchor requires id, version and aliases')
            if spec.get('valid_from') and stamp < epoch(spec['valid_from']):
                continue
            if spec.get('valid_until') and stamp >= epoch(spec['valid_until']):
                continue
            matched = []
            for alias in dict.fromkeys(spec['aliases']):
                if not isinstance(alias, str) or len(alias.strip()) < 2:
                    raise ValueError('anchors must be nontrivial literal strings')
                pattern = re.escape(alias)
                if alias[0].isascii() and alias[0].isalnum(): pattern = r'(?<!\w)' + pattern
                if alias[-1].isascii() and alias[-1].isalnum(): pattern += r'(?!\w)'
                flags = re.IGNORECASE if spec.get('case_insensitive', False) else 0
                match = re.search(pattern, text, flags)
                if match:
                    matched.append((alias, match.start(), match.end()))
            required = spec.get('min_anchors', 1)
            if type(required) is not int or required < 1:
                raise ValueError('invalid min_anchors')
            if len(matched) < required:
                continue
            matched.sort(key=lambda m: m[1])
            tight = any(group[-1][2]-group[0][1] <= 200 for i in range(len(matched)-required+1)
                        for group in [matched[i:i+required]])
            if not tight:
                continue
            snapshot = record.get('memory_versions', {}).get(spec['id']) == spec['version']
            # A branch copying identical text remains one observation for that version.
            event_id = fingerprint([scope, spec['id'], spec['version'], text, record['timestamp']])
            if event_id in seen:
                continue
            seen.add(event_id)
            observations.append({'event_id': event_id, 'type': 'mention_observed', 'weight': 0.0,
                                 'scope': scope, 'entry_id': spec['id'], 'entry_version': spec['version'],
                                 'session_id': record['session'], 'message_id': record['id'],
                                 'timestamp': record['timestamp'], 'text_hash': fingerprint(text),
                                 'source_text_hash': fingerprint(record['text']), 'coordinate_space': 'filtered_text',
                                 'matches': [{'anchor': m[0], 'start': m[1], 'end': m[2]} for m in matched],
                                 'exposure': 'snapshot_matched' if snapshot else 'unknown',
                                 'usefulness': 'unverified', 'scanner_version': 1})
    return observations, {'partial': False, 'scanned': scanned, 'skipped': dict(skipped)}


def store_observations(path, observations):
    """Sidecar only. Does not change index.json, validity or residency scores."""
    db = connect_derived(path, {'observations'})
    try:
        db.execute('CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        import json
        before = db.total_changes
        with db:
            db.executemany('INSERT OR IGNORE INTO observations VALUES(?,?)',
                           [(o['event_id'], json.dumps(o, ensure_ascii=False, sort_keys=True)) for o in observations])
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
