"""Explicit source adapters. Gold QA labels never enter retrieval documents."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import time
from .retrieval import Document, fingerprint


def locomo_documents(sample):
    scope = str(sample['sample_id'])
    conversation = sample['conversation']
    for session, turns in conversation.items():
        if not re.fullmatch(r'session_\d+', session) or not isinstance(turns, list):
            continue
        timestamp = str(conversation.get(session + '_date_time', ''))
        for order, turn in enumerate(turns):
            text = turn.get('text', '')
            if not isinstance(text, str) or not text.strip():
                continue
            yield Document(str(turn['dia_id']), scope, session, order, text,
                           str(turn.get('speaker', '')), timestamp,
                           'locomo:' + scope + ':' + str(turn['dia_id']))
    # Deliberately do not read qa, evidence, answer, observation, or session_summary.


def jsonl_documents(path, scope):
    with Path(path).open(encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('scope') != scope:
                raise ValueError(f'JSONL scope mismatch at line {number}')
            yield Document(**row)


def file_documents(root, scope, tier='T1'):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or tier not in ('T0', 'T1', 'T3'):
        raise ValueError('existing directory and local-file tier required')
    for path in sorted(root.rglob('*.md')):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('symlink/outside source refused')
        if path.stat().st_size > 2_000_000:
            raise ValueError('source larger than 2 MB; split before import')
        text = path.read_text(encoding='utf-8')
        relative = path.relative_to(root).as_posix()
        # Sections become independently retrievable chunks; original text is retained.
        sections = re.split(r'\n(?=#{1,6} )|\n§\n', text)
        for ordinal, part in enumerate(sections):
            if part.strip():
                yield Document(f'file:{relative}#{ordinal}', scope, relative, ordinal, part.strip(),
                               source='file:'+relative, tier=tier)


def epoch(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('timestamps must have timezone')
        return date.astimezone(timezone.utc)
    raise ValueError('invalid timestamp')


def read_hermes(path, scope, *, since=None, max_rows=50000, timeout=10.0):
    """Read-only schema-checked snapshot, never import live SessionDB/migrations.

    Unknown schemas fail. Partial reads explicitly disclose the cap. Native WAL
    read-only behavior applies; immutable=1 is intentionally NOT used on a live DB.
    """
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError('existing non-symlink state DB required')
    path = path.resolve()
    start = time.perf_counter()
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    records = []
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(time.perf_counter()-start > timeout), 1000)
        columns = {r[1] for r in db.execute('PRAGMA table_info(messages)')}
        required = {'id', 'session_id', 'role', 'content', 'timestamp', 'active', '_compressed_summary'}
        if not required <= columns:
            raise ValueError('unsupported Hermes messages schema: missing ' + ','.join(sorted(required-columns)))
        session_cols = {r[1] for r in db.execute('PRAGMA table_info(sessions)')}
        if not {'id', 'source', 'hidden', 'profile_name'} <= session_cols:
            raise ValueError('session source labels required for exclusion')
        profiles = {r[0] or '' for r in db.execute('SELECT DISTINCT profile_name FROM sessions WHERE hidden=0')}
        if len(profiles) > 1:
            raise ValueError('multi-profile DB refused; export one profile before indexing')
        predicate, params = '', []
        if since is not None:
            predicate = ' AND m.timestamp >= ?'
            params.append(epoch(since).timestamp())
        # Only conversational messages. No tool blobs, system prompts or review outputs.
        sql = '''SELECT m.id,m.session_id,m.role,m.content,m.timestamp,s.source
                 FROM messages m JOIN sessions s ON s.id=m.session_id
                 WHERE m.role IN ('user','assistant') AND m.active=1
                   AND m._compressed_summary=0 AND s.hidden=0''' + predicate + '''
                 ORDER BY m.timestamp,m.id LIMIT ?'''
        rows = db.execute(sql, (*params, max_rows + 1)).fetchall()
        partial = len(rows) > max_rows
        for row in rows[:max_rows]:
            if str(row['source']).lower() in {'cron', 'flush', 'subagent', 'background', 'test', 'review'}:
                continue
            text = row['content']
            if not isinstance(text, str) or not text.strip():
                continue
            records.append({'id': str(row['id']), 'session': str(row['session_id']),
                            'role': row['role'], 'text': text,
                            'timestamp': epoch(row['timestamp']).isoformat(), 'source': str(row['source'])})
        return records, {'partial': partial, 'scanned_rows': min(len(rows), max_rows),
                         'accepted_rows': len(records), 'read_only': True,
                         'schema': sorted(required), 'elapsed_ms': (time.perf_counter()-start)*1000}
    finally:
        db.close()


def hermes_documents(records, scope):
    from collections import Counter
    positions = Counter()
    for row in records:
        order = positions[row['session']]
        positions[row['session']] += 1
        yield Document('hermes:'+row['id'], scope, row['session'], order, row['text'],
                       row['role'], row['timestamp'], 'hermes-message:' + row['id'])
