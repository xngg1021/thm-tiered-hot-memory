"""Scoped, budgeted retrieval. No QA labels, automatic downloads or memory writes.

SQLite FTS5 supplies two lexical paths. Optional local sentence embeddings are
fused by reciprocal rank, never presented as evidence of correctness. Returned
context includes only actual source spans; candidate IDs are not counted as read.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable, Iterable

STOP = frozenset('a an the is are was were be been being do does did have has had '
                 'what when where which who whom whose how why would could should '
                 'can will may might must to of for from in on at by with about '
                 'and or as than that this these those it its their they them he '
                 'she his her i me my we our you your not no'.split())
# Negations are excluded only from candidate queries, never removed from source text.
WORD = re.compile(r"[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*|[\u3400-\u9fff]+", re.UNICODE)
CJK = re.compile(r'[\u3400-\u9fff]+')


def terms(text: str) -> list[str]:
    out = []
    for token in WORD.findall(text):
        if CJK.fullmatch(token):
            out.extend(token[i:i + 2] for i in range(max(1, len(token) - 1)))
        else:
            out.append(token.lower())
    return list(dict.fromkeys(out))


def index_text(text: str) -> str:
    return text + ' ' + ' '.join(t for t in terms(text) if CJK.fullmatch(t))


def match_query(tokens: Iterable[str]) -> str:
    return ' OR '.join('"' + t.replace('"', '""') + '"' for t in tokens)


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Document:
    id: str
    scope: str
    session: str
    order: int
    text: str
    speaker: str = ''
    timestamp: str = ''
    source: str = ''
    tier: str = 'T2'

    def validate(self):
        for field in ('id', 'scope', 'session', 'text', 'speaker', 'timestamp', 'source', 'tier'):
            if not isinstance(getattr(self, field), str):
                raise ValueError('document fields must be strings: ' + field)
        if not self.id or not self.scope or not self.session or not self.text.strip():
            raise ValueError('id, scope, session and text are required')
        if type(self.order) is not int or self.order < 0 or self.tier not in ('T0', 'T1', 'T2', 'T3'):
            raise ValueError('invalid document order/tier')
        if len(self.text.encode('utf-8')) > 2_000_000:
            raise ValueError('document exceeds 2 MB; split it explicitly')


class TokenCounter:
    """Explicit measurement. UTF-8 byte fallback is NOT a model token count."""
    def __init__(self, encoding: str = 'utf8_bytes'):
        self.name = encoding
        self.encode = None
        if encoding != 'utf8_bytes':
            import tiktoken  # Optional; vocabulary cache may be populated by tiktoken on first use.
            self.encode = tiktoken.get_encoding(encoding).encode_ordinary

    def __call__(self, text: str) -> int:
        return len(self.encode(text)) if self.encode else len(text.encode('utf-8'))


class SentenceEncoder:
    """User-selected on-disk sentence-transformer; no remote code or downloads."""
    def __init__(self, path: str, model_id: str, threads: int = 2):
        if not Path(path).is_dir() or not model_id.strip():
            raise ValueError('an existing model directory and immutable model_id are required')
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(max(1, threads))
        self.model = SentenceTransformer(path, device='cpu', local_files_only=True,
                                         trust_remote_code=False)
        self.model_id = model_id

    def __call__(self, texts):
        return self.model.encode(list(texts), batch_size=64, normalize_embeddings=True,
                                 show_progress_bar=False).tolist()


def normalize_vectors(vectors, expected: int):
    if len(vectors) != expected:
        raise ValueError('embedding result count mismatch')
    result, dim = [], None
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or not vector:
            raise ValueError('empty/invalid vector')
        if dim is None:
            dim = len(vector)
        if len(vector) != dim or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ValueError('embedding dimensions or finite values invalid')
        norm = math.sqrt(sum(v * v for v in vector))
        if norm <= 0:
            raise ValueError('zero embedding')
        result.append([v / norm for v in vector])
    return result


class SearchIndex:
    def __init__(self, path, counter: Callable[[str], int] | None = None):
        path = Path(path)
        if path.is_symlink():
            raise ValueError('symlink index refused')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS docs(
          rowid INTEGER PRIMARY KEY, id TEXT NOT NULL, scope TEXT NOT NULL,
          session TEXT NOT NULL, ord INTEGER NOT NULL, text TEXT NOT NULL,
          speaker TEXT NOT NULL, timestamp TEXT NOT NULL, source TEXT NOT NULL,
          tier TEXT NOT NULL, hash TEXT NOT NULL, UNIQUE(scope,id));
        CREATE INDEX IF NOT EXISTS docs_scope_session ON docs(scope,session,ord);
        CREATE VIRTUAL TABLE IF NOT EXISTS literal USING fts5(body,meta,tokenize='unicode61');
        CREATE VIRTUAL TABLE IF NOT EXISTS lexical USING fts5(body,context,meta,tokenize='porter unicode61');
        CREATE TABLE IF NOT EXISTS scopes(scope TEXT PRIMARY KEY,generation TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS vectors(scope TEXT,id TEXT,hash TEXT,model TEXT,vector TEXT,
          PRIMARY KEY(scope,id,model));
        ''')
        self.counter = counter or TokenCounter()
        self._cache, self._dense = OrderedDict(), {}

    def close(self):
        self.db.close()

    def replace_scope(self, scope: str, documents: Iterable[Document]) -> dict:
        """Replace one explicit derived scope transactionally; no input files changed."""
        docs = list(documents)
        if not scope.strip():
            raise ValueError('scope is mandatory')
        ids = set()
        for d in docs:
            d.validate()
            if d.scope != scope or d.id in ids:
                raise ValueError('scope mismatch or duplicate document ID')
            ids.add(d.id)
        docs.sort(key=lambda d: (d.session, d.order, d.id))
        generation = fingerprint([asdict(d) for d in docs])
        previous = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
        if previous and previous[0] == generation:
            return {'changed': False, 'documents': len(docs), 'generation': generation}
        with self.db:
            old = [r[0] for r in self.db.execute('SELECT rowid FROM docs WHERE scope=?', (scope,))]
            for rid in old:
                self.db.execute('DELETE FROM literal WHERE rowid=?', (rid,))
                self.db.execute('DELETE FROM lexical WHERE rowid=?', (rid,))
            self.db.execute('DELETE FROM docs WHERE scope=?', (scope,))
            self.db.execute('DELETE FROM vectors WHERE scope=?', (scope,))
            for pos, d in enumerate(docs):
                # Unsupervised adjacent-turn context; no labels or generated summaries.
                context = ' '.join(x.text for x in docs[max(0, pos - 1):pos + 2]
                                   if x.session == d.session and x.id != d.id)
                meta = f'{d.speaker} {d.timestamp}'
                rid = self.db.execute('''INSERT INTO docs
                    (id,scope,session,ord,text,speaker,timestamp,source,tier,hash)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',
                    (d.id, d.scope, d.session, d.order, d.text, d.speaker, d.timestamp,
                     d.source, d.tier, fingerprint(asdict(d)))).lastrowid
                self.db.execute('INSERT INTO literal(rowid,body,meta) VALUES(?,?,?)', (rid, d.text, meta))
                self.db.execute('INSERT INTO lexical(rowid,body,context,meta) VALUES(?,?,?,?)',
                                (rid, index_text(d.text), index_text(context), index_text(meta)))
            self.db.execute('INSERT OR REPLACE INTO scopes VALUES(?,?)', (scope, generation))
        self._cache.clear()
        self._dense.clear()
        return {'changed': True, 'documents': len(docs), 'generation': generation}

    def sync_kind(self, scope, documents, prefix):
        """Refresh one explicit source kind without discarding the other tiers."""
        docs = list(documents)
        if prefix not in ('file:', 'hermes-message:') or any(not d.source.startswith(prefix) for d in docs):
            raise ValueError('source kind mismatch')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = [Document(r['id'], r['scope'], r['session'], r['ord'], r['text'], r['speaker'],
                            r['timestamp'], r['source'], r['tier']) for r in self.rows(scope)
                   if not r['source'].startswith(prefix)]
            return self.replace_scope(scope, old + docs)
        finally:
            # replace_scope commits changed data; unchanged/error paths release the lock.
            self.db.rollback()

    def rows(self, scope):
        return [dict(r) for r in self.db.execute('SELECT * FROM docs WHERE scope=? ORDER BY rowid', (scope,))]

    def embed(self, scope, encoder, model_id):
        if not model_id.strip():
            raise ValueError('immutable model identity required')
        rows = self.rows(scope)
        existing = {r['id']: r['hash'] for r in self.db.execute(
            'SELECT id,hash FROM vectors WHERE scope=? AND model=?', (scope, model_id))}
        missing = [r for r in rows if existing.get(r['id']) != r['hash']]
        start = time.perf_counter()
        if missing:
            vectors = normalize_vectors(encoder([f"{r['speaker']}: {r['text']}" for r in missing]), len(missing))
            with self.db:
                self.db.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?,?,?)',
                    [(scope, r['id'], r['hash'], model_id, json.dumps(v)) for r, v in zip(missing, vectors)])
        self._dense.clear()
        return {'embedded': len(missing), 'seconds': time.perf_counter() - start, 'model': model_id}

    def _dense_search(self, scope, query, encoder, model_id, limit):
        import numpy as np  # Optional dense execution only.
        key = (scope, model_id, self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()[0])
        if key not in self._dense:
            rows = list(self.db.execute('''SELECT d.rowid,v.vector FROM docs d JOIN vectors v
              ON v.scope=d.scope AND v.id=d.id AND v.hash=d.hash WHERE d.scope=? AND v.model=?
              ORDER BY d.rowid''', (scope, model_id)))
            count = self.db.execute('SELECT COUNT(*) FROM docs WHERE scope=?', (scope,)).fetchone()[0]
            if not rows or len(rows) != count:
                raise ValueError('embedding index missing/stale; run embed for this model and scope')
            vectors = normalize_vectors([json.loads(r[1]) for r in rows], len(rows))
            self._dense[key] = ([r[0] for r in rows], np.asarray(vectors, dtype=np.float32))
        ids, matrix = self._dense[key]
        cached = (model_id, query)
        start = time.perf_counter()
        was_cached = cached in self._cache
        if not was_cached:
            self._cache[cached] = normalize_vectors(encoder([query]), 1)[0]
            if len(self._cache) > 256:
                self._cache.popitem(last=False)
        vector = np.asarray(self._cache[cached], dtype=np.float32)
        if vector.shape[0] != matrix.shape[1]:
            raise ValueError('query/document embedding dimension mismatch')
        embed_ms = (time.perf_counter() - start) * 1000
        scores = matrix @ vector
        order = np.argsort(-scores, kind='stable')[:limit]
        return [ids[int(i)] for i in order], embed_ms, was_cached

    def _fts(self, table, scope, tokens, limit, contextual=False):
        if not tokens:
            return []
        if table not in ('literal', 'lexical'):
            raise ValueError('invalid FTS table')
        weights = '1.0,0.12,0.05' if contextual else ('1.0,0.0,0.02' if table == 'lexical' else '1.0,0.0')
        sql = f'''SELECT d.rowid FROM {table} JOIN docs d ON d.rowid={table}.rowid
          WHERE {table} MATCH ? AND d.scope=? ORDER BY bm25({table},{weights}),d.id LIMIT ?'''
        return [r[0] for r in self.db.execute(sql, (match_query(tokens), scope, limit)).fetchall()]

    def _search(self, scope: str, query: str, *, budget=600, mode='sparse', candidate_limit=100,
               neighbor_turns=0, encoder=None, model_id=None) -> dict:
        start = time.perf_counter()
        if not scope or not isinstance(query, str) or not query.strip():
            raise ValueError('nonempty scope and query required')
        if type(budget) is not int or not 0 <= budget <= 32768:
            raise ValueError('budget must be an integer from 0 to 32768')
        if mode not in ('literal', 'sparse', 'hybrid', 'dense') or not 1 <= candidate_limit <= 1000 or neighbor_turns not in (0, 1, 2):
            raise ValueError('invalid retrieval settings')
        if len(query) > 16000:
            raise ValueError('query too long')
        generation = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
        if generation is None:
            raise ValueError('scope not indexed')
        tokens = terms(query)[:64]
        speakers = set()
        for row in self.db.execute('SELECT DISTINCT speaker FROM docs WHERE scope=?', (scope,)):
            speakers.update(terms(row[0]))
        focus = [t for t in tokens if t not in STOP and t not in speakers]
        focus = focus or [t for t in tokens if t not in STOP]
        channels = []
        if mode == 'literal':
            channels.append(self._fts('literal', scope, tokens, candidate_limit))
        elif mode != 'dense':
            channels.append(self._fts('lexical', scope, focus, candidate_limit))
            channels.append(self._fts('lexical', scope, [t for t in tokens if t not in STOP], candidate_limit, True))
        sparse_ms = (time.perf_counter() - start) * 1000
        embedding_ms, query_cached = 0.0, False
        if mode in ('hybrid', 'dense'):
            if encoder is None or not model_id:
                raise ValueError('dense mode requires an explicit local encoder and model identity')
            dense, embedding_ms, query_cached = self._dense_search(scope, query, encoder, model_id, candidate_limit)
            channels.append(dense)
        scores = {}
        for channel in channels:
            for rank, rid in enumerate(dict.fromkeys(channel), 1):
                scores[rid] = scores.get(rid, 0.0) + 1.0 / (60.0 + rank)
        ordered = sorted(scores, key=lambda rid: (-scores[rid], rid))
        ranked = []
        for rid in ordered:
            ranked.append(dict(self.db.execute('SELECT * FROM docs WHERE rowid=? AND scope=?', (rid, scope)).fetchone()))
        ranked_ids = [r['id'] for r in ranked]
        retrieval_ms = (time.perf_counter() - start) * 1000
        # Optional adjacent context is actual text, not automatic credit for unseen IDs.
        expanded, seen = [], set()
        for row in ranked:
            candidates = [row]
            if neighbor_turns:
                candidates += [dict(r) for r in self.db.execute('''SELECT * FROM docs
                   WHERE scope=? AND session=? AND ord BETWEEN ? AND ? AND rowid!=?
                   ORDER BY ABS(ord-?),ord,id''', (scope, row['session'], row['ord']-neighbor_turns,
                   row['ord']+neighbor_turns, row['rowid'], row['ord']))]
            for item in candidates:
                if item['rowid'] not in seen:
                    seen.add(item['rowid'])
                    expanded.append(item)
        blocks, selected = [], []
        for row in expanded:
            label = json.dumps({'id': row['id'], 'speaker': row['speaker'], 'date': row['timestamp']}, ensure_ascii=False)
            block = f"[source {label}]\n{row['text']}"
            trial = '\n\n'.join(blocks + [block])
            if self.counter(trial) <= budget:
                blocks.append(block)
                selected.append({'id': row['id'], 'hash': row['hash'], 'source': row['source'],
                                 'complete': True, 'text': row['text']})
            # Oversized turns are skipped rather than terminating the packing pass.
        context = '\n\n'.join(blocks)
        total_ms = (time.perf_counter()-start)*1000
        return {'scope': scope, 'generation': generation[0], 'mode': mode, 'context': context,
                'selected': selected, 'ranked_ids': ranked_ids, 'candidate_count': len(ranked),
                'budget': budget, 'budget_used': self.counter(context),
                'counter': getattr(self.counter, 'name', 'caller_supplied'),
                'timing_ms': {'sparse': sparse_ms, 'query_embedding': embedding_ms,
                              'retrieval_total': retrieval_ms, 'pack': total_ms-retrieval_ms,
                              'total': total_ms},
                'query_embedding_cache_hit': query_cached,
                'semantic_encoder_used': mode in ('hybrid', 'dense'),
                'answer_generated': False}

    def search(self, scope, query, **kwargs):
        """One consistent read snapshot. Callers sharing an instance must serialize calls."""
        self.db.execute('BEGIN')
        try:
            return self._search(scope, query, **kwargs)
        finally:
            self.db.rollback()
