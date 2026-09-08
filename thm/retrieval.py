"""Scoped, budgeted retrieval. No QA labels, automatic downloads or memory writes.

SQLite FTS5 supplies two lexical paths. Optional local sentence embeddings are
fused by reciprocal rank, never presented as evidence of correctness. Returned
context includes only actual source spans; candidate IDs are not counted as read.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, asdict
import hashlib
import copy
import threading
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable, Iterable
from .sqlite_guard import connect_derived

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
    """Backward-compatible facade over the optional local reference backend.

    Library calls inherit host thread policy. Explicit thread control belongs
    in an isolated runtime worker, never in an agent's host process.
    """
    def __init__(self, path, model_id, threads=None, device='cpu', batch_size=64,
                 *, isolated=False, backend='torch_fp32'):
        from .runtime.backends import create
        self._backend = create(path, model_id, backend=backend, device=device,
                               threads=threads, document_batch_size=batch_size, isolated=isolated)
        self.__dict__.update({k:getattr(self._backend,k) for k in
                             ('model_id','device','batch_size','document_batch_size','query_batch_size','profile')})
    def __call__(self,texts): return self._backend.encode_many(texts)
    def encode_many(self,texts): return self._backend.encode_many(texts)
    def encode_one(self,text): return self._backend.encode_one(text)
    def identity(self): return self._backend.identity()
    def capabilities(self): return self._backend.capabilities()
    def close(self): self._backend.close()


def normalize_vectors(vectors, expected: int):
    if (not isinstance(vectors, (list, tuple)) or type(expected) is not int
            or expected < 0 or len(vectors) != expected):
        raise ValueError('embedding result count mismatch')
    result, dim = [], None
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or not vector:
            raise ValueError('empty/invalid vector')
        if dim is None:
            dim = len(vector)
        if len(vector) != dim or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ValueError('embedding dimensions or finite values invalid')
        scale = max(abs(v) for v in vector)
        if scale == 0:
            raise ValueError('zero embedding')
        scaled = [v / scale for v in vector]
        norm = math.sqrt(sum(v * v for v in scaled))
        result.append([v / norm for v in scaled])
    return result


class SearchIndex:
    def __init__(self, path, counter: Callable[[str], int] | None = None, *, readonly=False):
        self.readonly = readonly
        self._lock = threading.RLock()
        path = Path(path).expanduser()
        if path.is_symlink():
            raise ValueError('symlink index refused')
        if readonly:
            if not path.is_file():
                raise ValueError('read-only search index does not exist')
            self.db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True,
                                      timeout=5, check_same_thread=False)
            self.db.execute('PRAGMA query_only=ON')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = connect_derived(path, {'docs', 'scopes', 'vectors', 'literal', 'lexical'}, shared_thread=True)
        self.db.row_factory = sqlite3.Row
        try:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected = {'docs', 'literal', 'lexical', 'scopes', 'vectors'}
            if tables and (not expected <= tables or any(
                    t not in expected | {'embedding_profiles','vector_generations','vectors_v2'} and not t.startswith(('literal_', 'lexical_', 'sqlite_')) for t in tables)):
                raise ValueError('not a THM retrieval database; native or unrelated databases are refused')
            if readonly and not tables:
                raise ValueError('empty read-only retrieval database')
            if not readonly:
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
            if not readonly:
                from .runtime.storage import SCHEMA
                self.db.executescript(SCHEMA)
            required_columns = {
                'docs': {'rowid','id','scope','session','ord','text','speaker','timestamp','source','tier','hash'},
                'scopes': {'scope','generation'}, 'vectors': {'scope','id','hash','model','vector'}}
            for table, required in required_columns.items():
                if not required <= {r[1] for r in self.db.execute(f'PRAGMA table_info({table})')}:
                    raise ValueError('unsupported retrieval database schema')
        except Exception:
            self.db.close()
            raise
        self.counter = counter or TokenCounter()
        self._cache, self._dense = OrderedDict(), {}
        self._results = OrderedDict()
        self._batch_dense = None
        self._query_future = None
        self._last_dense_diagnostics = {}
        self._data_version = self.db.execute('PRAGMA data_version').fetchone()[0]

    def _writable(self):
        if self.readonly:
            raise ValueError('read-only search index')

    def _clear_caches(self):
        self._cache.clear()
        self._dense.clear()
        self._results.clear()

    def _refresh_caches(self):
        version = self.db.execute('PRAGMA data_version').fetchone()[0]
        if version != self._data_version:
            self._clear_caches()
            self._data_version = version

    def _count(self, text):
        count = self.counter(text)
        if type(count) is not int or count < 0 or (text and count == 0):
            raise ValueError('counter must return a positive integer for nonempty context')
        return count

    def close(self):
        with self._lock:
            self._clear_caches()
            self.db.close()

    def replace_scope(self, scope: str, documents: Iterable[Document]) -> dict:
        self._writable()
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                result = self._replace_scope(scope, documents)
                self.db.commit()
                return result
            except Exception:
                self.db.rollback()
                raise

    def _replace_scope(self, scope: str, documents: Iterable[Document]) -> dict:
        """Replace one explicit derived scope transactionally; no input files changed."""
        docs = list(documents)
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError('scope is mandatory')
        ids, positions = set(), set()
        for d in docs:
            d.validate()
            if d.scope != scope or d.id in ids:
                raise ValueError('scope mismatch or duplicate document ID')
            if (d.session, d.order) in positions:
                raise ValueError('duplicate document position within a session')
            positions.add((d.session, d.order))
            ids.add(d.id)
        docs.sort(key=lambda d: (d.session, d.order, d.id))
        generation = fingerprint([asdict(d) for d in docs])
        previous = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
        if previous and previous[0] == generation:
            return {'changed': False, 'documents': len(docs), 'generation': generation}
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
        self._clear_caches()
        return {'changed': True, 'documents': len(docs), 'generation': generation}

    def sync_kind(self, scope, documents, prefix):
        """Refresh one explicit source kind in one serialized write transaction."""
        self._writable()
        docs = list(documents)
        if prefix not in ('file:', 'hermes-message:') or any(not d.source.startswith(prefix) for d in docs):
            raise ValueError('source kind mismatch')
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = [Document(r['id'], r['scope'], r['session'], r['ord'], r['text'], r['speaker'],
                                r['timestamp'], r['source'], r['tier']) for r in self.rows(scope)
                       if not r['source'].startswith(prefix)]
                result = self._replace_scope(scope, old + docs)
                self.db.commit()
                return result
            except Exception:
                self.db.rollback()
                raise

    def rows(self, scope):
        return [dict(r) for r in self.db.execute('SELECT * FROM docs WHERE scope=? ORDER BY rowid', (scope,))]

    def embed(self, scope, encoder, model_id, *, document_batch_size=None, vector_storage="json", embedding_cache=None):
        """Encode outside the write transaction, then verify its source generation."""
        self._writable()
        from .runtime.identity import bounded_int
        batch_size = bounded_int(document_batch_size if document_batch_size is not None else getattr(encoder,'document_batch_size',64),'document batch',256)
        if vector_storage not in ('json','blob'): raise ValueError('unsupported vector storage')
        if getattr(encoder,'profile',None) is not None:
            return self._embed_profile(scope,encoder,model_id,batch_size,vector_storage,embedding_cache)
        if embedding_cache is not None or vector_storage != 'json':
            raise ValueError('cache/BLOB storage requires explicit embedding profile')
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError('immutable model identity required')
        if getattr(encoder, 'model_id', model_id) != model_id:
            raise ValueError('encoder identity mismatch')
        with self._lock:
            self.db.execute('BEGIN')
            try:
                generation = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
                if generation is None:
                    raise ValueError('scope not indexed')
                rows = self.rows(scope)
                existing = {r['id']: r['hash'] for r in self.db.execute(
                    'SELECT id,hash FROM vectors WHERE scope=? AND model=?', (scope, model_id))}
            finally:
                self.db.rollback()
            missing = [r for r in rows if existing.get(r['id']) != r['hash']]
            start = time.perf_counter()
            vectors = []
            for offset in range(0, len(missing), batch_size):
                batch = missing[offset:offset+batch_size]
                vectors.extend(normalize_vectors(encoder([f"{r['speaker']}: {r['text']}" for r in batch]), len(batch)))
            if vectors:
                vectors = normalize_vectors(vectors, len(missing))
            self.db.execute('BEGIN IMMEDIATE')
            try:
                current = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
                if current is None or current[0] != generation[0]:
                    raise ValueError('source generation changed during embedding; retry on current sources')
                self.db.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?,?,?)',
                    [(scope, r['id'], r['hash'], model_id, json.dumps(v, allow_nan=False))
                     for r, v in zip(missing, vectors)])
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            self._clear_caches()
            return {'embedded': len(missing), 'seconds': time.perf_counter() - start,
                    'model': model_id, 'generation': generation[0], 'document_batch_size':batch_size}

    def _embed_profile(self, scope, encoder, model_id, batch_size, storage, cache):
        from .runtime.storage import pack
        from .runtime.identity import validate_vectors
        if encoder.model_id != model_id: raise ValueError('encoder identity mismatch')
        profile=encoder.profile; started=time.perf_counter()
        with self._lock:
            self.db.execute('BEGIN')
            try:
                generation=self.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
                if not generation: raise ValueError('scope not indexed')
                rows=self.rows(scope)
            finally: self.db.rollback()
        # No SQLite lock/transaction during model execution. Publish all or none.
        from concurrent.futures import ThreadPoolExecutor
        vectors=[]
        def encode_batch(texts):return cache.encode(encoder,texts) if cache else encoder.encode_many(texts)
        with ThreadPoolExecutor(max_workers=1,thread_name_prefix='thm-build') as pool:
            pending=None;pending_count=0
            for offset in range(0,len(rows),batch_size):
                batch=rows[offset:offset+batch_size]
                # CPU prepares the next exact inputs while the previous encoder batch runs.
                texts=[f"{r['speaker']}: {r['text']}" for r in batch]
                if pending is not None:vectors.extend(validate_vectors(pending.result(),profile,pending_count))
                pending=pool.submit(encode_batch,texts);pending_count=len(batch)
            if pending is not None:vectors.extend(validate_vectors(pending.result(),profile,pending_count))
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                current=self.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
                if not current or current[0]!=generation[0]: raise ValueError('source generation changed during embedding')
                identity=json.dumps(profile.identity(),sort_keys=True)
                previous=self.db.execute('SELECT identity FROM embedding_profiles WHERE profile=?',(profile.id,)).fetchone()
                if previous and previous[0]!=identity: raise ValueError('embedding profile collision')
                self.db.execute('INSERT OR IGNORE INTO embedding_profiles VALUES(?,?)',(profile.id,identity))
                self.db.execute('DELETE FROM vectors_v2 WHERE scope=? AND profile=?',(scope,profile.id))
                self.db.executemany('INSERT INTO vectors_v2 VALUES(?,?,?,?,?,?,?)',
                    [(scope,r['id'],r['hash'],profile.id,profile.dimension,'f32le' if storage=='blob' else 'json',
                      pack(v) if storage=='blob' else json.dumps(v,allow_nan=False)) for r,v in zip(rows,vectors)])
                self.db.execute('INSERT OR REPLACE INTO vector_generations VALUES(?,?,?,?)',(scope,profile.id,generation[0],len(rows)))
                self.db.commit();self._clear_caches()
            except Exception: self.db.rollback();raise
        return {'embedded':len(rows),'seconds':time.perf_counter()-started,'model':model_id,
                'generation':generation[0],'embedding_profile':profile.identity(),'document_batch_size':batch_size,
                'storage':storage,'pipeline':{'encoder_inflight_limit':1,'cpu_preparation_ahead':1,'atomic_publication':True},'cache':{'hits':cache.hits,'misses':cache.misses} if cache else None}

    def _dense_matrix(self,scope,encoder,model_id):
        import numpy as np
        from .runtime.storage import unpack
        profile=getattr(encoder,'profile',None)
        identity=profile.id if profile else model_id
        generation=self.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
        if not generation: raise ValueError('scope not indexed')
        key=(scope,identity,generation[0])
        if key not in self._dense:
            count=self.db.execute('SELECT COUNT(*) FROM docs WHERE scope=?',(scope,)).fetchone()[0]
            if profile:
                try:
                    complete=self.db.execute('SELECT generation,count FROM vector_generations WHERE scope=? AND profile=?',(scope,identity)).fetchone()
                    stored=self.db.execute('SELECT identity FROM embedding_profiles WHERE profile=?',(identity,)).fetchone()
                    if not complete or tuple(complete)!=(generation[0],count) or not stored or json.loads(stored[0])!=profile.identity():
                        raise ValueError('profile index missing/stale; embed or explicitly migrate legacy vectors')
                    rows=list(self.db.execute('SELECT d.rowid,v.vector,v.dimension,v.dtype FROM docs d JOIN vectors_v2 v ON v.scope=d.scope AND v.id=d.id AND v.hash=d.hash WHERE d.scope=? AND v.profile=? ORDER BY d.rowid',(scope,identity)))
                except sqlite3.OperationalError as e: raise ValueError('legacy index needs explicit embedding profile migration') from e
                vectors=[unpack(r[1],r[2],r[3]) if r[3]=='f32le' else json.loads(r[1]) if r[3]=='json' else [] for r in rows]
                if any(r[2]!=profile.dimension for r in rows): raise ValueError('profile dimension mismatch')
            else:
                rows=list(self.db.execute('SELECT d.rowid,v.vector FROM docs d JOIN vectors v ON v.scope=d.scope AND v.id=d.id AND v.hash=d.hash WHERE d.scope=? AND v.model=? ORDER BY d.rowid',(scope,model_id)))
                vectors=[json.loads(r[1]) for r in rows]
            if not rows or len(rows)!=count: raise ValueError('embedding index missing/stale; run embed for this model and scope')
            if profile:
                from .runtime.identity import validate_vectors
                validate_vectors(vectors,profile,len(rows))
            vectors=normalize_vectors(vectors,len(rows))
            self._dense[key]=([r[0] for r in rows],np.asarray(vectors,dtype=np.float32))
        return self._dense[key]

    def _dense_search(self, scope, query, encoder, model_id, limit, scorer='numpy_reference'):
        import numpy as np
        start=time.perf_counter()
        if self._batch_dense is not None and query in self._batch_dense:
            return self._batch_dense[query]
        ids,matrix=self._dense_matrix(scope,encoder,model_id)
        load_ms=(time.perf_counter()-start)*1000
        profile=getattr(encoder,'profile',None);identity=profile.id if profile else model_id
        cached=(identity,query);was_cached=cached in self._cache;start=time.perf_counter()
        if not was_cached:
            raw=self._query_future.result() if self._query_future is not None else encoder([query])
            if profile:
                from .runtime.identity import validate_vectors
                validate_vectors(raw,profile,1)
            self._cache[cached]=normalize_vectors(raw,1)[0]
            if len(self._cache)>256:self._cache.popitem(last=False)
        vector=np.asarray(self._cache[cached],dtype=np.float32)
        if vector.shape[0]!=matrix.shape[1]:raise ValueError('query/document embedding dimension mismatch')
        embed_ms=(time.perf_counter()-start)*1000;started=time.perf_counter()
        transfer=0.0
        if scorer=='numpy_reference':scores=matrix @ vector
        else:
            from .runtime.scorers import score
            values,placement=score(matrix,[vector],scorer);scores=values[:,0];transfer=placement['transfer']
        order=np.argsort(-scores,kind='stable')[:limit]
        self._last_dense_diagnostics={'dense_matrix_load':load_ms,'dense_scoring':(time.perf_counter()-started)*1000,
            'scorer':scorer,'transfer':transfer,'embedding_profile_id':identity,'candidate_rowids':[ids[int(i)] for i in order],
            'scores':[float(scores[int(i)]) for i in order]}
        return [ids[int(i)] for i in order],embed_ms,was_cached

    def search_many(self,scope,queries,*,query_batch_size=32,scorer='numpy_reference',overlap=False,**kwargs):
        """Production batch API: one scope snapshot, bounded encode_many and GEMM."""
        from .runtime.identity import bounded_int
        from .runtime.scorers import score
        import itertools
        if type(overlap) is not bool:raise ValueError('overlap must be boolean')
        batch=bounded_int(query_batch_size,'query batch',256)
        queries=list(itertools.islice(queries,4097))
        if len(queries)>4096 or any(not isinstance(q,str) or not q.strip() or len(q)>16000 for q in queries):raise ValueError('invalid bounded query batch')
        if not queries:return []
        if kwargs.get('budget')==0 or kwargs.get('mode','sparse') not in ('dense','hybrid'):
            return [self.search(scope,q,scorer=scorer,**kwargs) for q in queries]
        encoder=kwargs.get('encoder');model_id=kwargs.get('model_id');limit=kwargs.get('candidate_limit',100)
        bounded_int(limit,'candidate limit',1000)
        if encoder is None or not model_id or getattr(encoder,'model_id',model_id)!=model_id:raise ValueError('explicit matching encoder required')
        import numpy as np
        with self._lock:
            self.db.execute('BEGIN')
            try:
                self._refresh_caches();start=time.perf_counter()
                ids,matrix=self._dense_matrix(scope,encoder,model_id)
                candidate_ids={r['rowid']:r['id'] for r in self.rows(scope)}
                load_ms=(time.perf_counter()-start)*1000;out=[]
                for offset in range(0,len(queries),batch):
                    chunk=queries[offset:offset+batch];started=time.perf_counter()
                    profile=getattr(encoder,'profile',None);identity=profile.id if profile else model_id
                    cached={q:self._cache[(identity,q)] for q in chunk if (identity,q) in self._cache}
                    misses=list(dict.fromkeys(q for q in chunk if q not in cached))
                    vectors_by_query=dict(cached);self._batch_lexical={}
                    overlap_active=overlap and bool(misses) and kwargs.get('mode')=='hybrid'
                    encoder_ms=0.0;lexical_ms=0.0
                    if misses:
                        if overlap_active:
                            from concurrent.futures import ThreadPoolExecutor
                            def encode_batch():
                                at=time.perf_counter();raw=encoder(misses)
                                return raw,(time.perf_counter()-at)*1000
                            with ThreadPoolExecutor(max_workers=1,thread_name_prefix='thm-batch-encoder') as pool:
                                future=pool.submit(encode_batch);lexical_start=time.perf_counter()
                                for query in dict.fromkeys(chunk):self._batch_lexical[query]=self._lexical_channels(scope,query,'hybrid',limit)
                                lexical_ms=(time.perf_counter()-lexical_start)*1000
                                raw,encoder_ms=future.result()
                        else:
                            at=time.perf_counter();raw=encoder(misses);encoder_ms=(time.perf_counter()-at)*1000
                        if profile:
                            from .runtime.identity import validate_vectors
                            validate_vectors(raw,profile,len(misses))
                        fresh=normalize_vectors(raw,len(misses));vectors_by_query.update(zip(misses,fresh))
                        for q,v in zip(misses,fresh):
                            self._cache[(identity,q)]=v
                            if len(self._cache)>256:self._cache.popitem(last=False)
                    vectors=[vectors_by_query[q] for q in chunk];preparation_ms=(time.perf_counter()-started)*1000;embed_ms=encoder_ms
                    values,timing=score(matrix,vectors,scorer);self._batch_dense={}
                    for column,q in enumerate(chunk):
                        row_start=time.perf_counter();ranking_start=row_start
                        order=np.argsort(-values[:,column],kind='stable')[:limit]
                        ranking_ms=(time.perf_counter()-ranking_start)*1000
                        self._batch_dense={q:([ids[int(i)] for i in order],embed_ms/len(chunk),q in cached)}
                        result=self._search(scope,q,**kwargs)
                        result['timing_kind']='post-batch-search; embedding/scoring measured once in batch_receipt'
                        result['batch_receipt']={'query_batch_size':len(chunk),'embedding_ms':embed_ms,'batch_preparation_ms':preparation_ms,'lexical_preparation_ms':lexical_ms,'overlap_requested':overlap,'overlap_active':overlap_active,'encoded_queries':len(misses),'cached_queries':len(chunk)-sum(q not in cached for q in chunk),'dense_matrix_load':load_ms,**timing}
                        result['result_cache_hit']=False;result['runtime_diagnostics']={'embedding_profile_id':getattr(getattr(encoder,'profile',None),'id',model_id),
                            'scorer':scorer,'candidate_rowids':[ids[int(i)] for i in order],'candidate_ids':[candidate_ids[ids[int(i)]] for i in order],
                            'selected_ids':[r['id'] for r in result['selected']],'budget_cutoff':result['budget'],'budget_used':result['budget_used'],
                            'feature_components':result.get('features'),'scores':[float(values[int(i),column]) for i in order]}
                        row_ms=(time.perf_counter()-row_start)*1000
                        result['timing_ms']['dense_ranking']=ranking_ms
                        result['timing_ms']['batch_row_overhead']=max(0.0,row_ms-result['timing_ms']['total'])
                        result['timing_ms']['amortized_total']=row_ms+(preparation_ms+timing['dense_scoring'])/len(chunk)+load_ms/len(queries)
                        if overlap:result['overlap']={'requested':True,'active':overlap_active,'cpu':'caller-thread SQLite/FTS','accelerator':'batched query embedding','microbatch_delay_ms':0}
                        out.append(result)
                return out
            finally:self._batch_dense=None;self._batch_lexical=None;self.db.rollback()

    def search_overlap(self,scope,query,**kwargs):
        """Encoder worker overlaps caller-thread SQLite FTS; no cross-thread DB use."""
        from concurrent.futures import ThreadPoolExecutor
        encoder=kwargs.get('encoder')
        if kwargs.get('budget')==0 or kwargs.get('mode')!='hybrid' or encoder is None:return self.search(scope,query,**kwargs)
        with self._lock:
            self._refresh_caches()
            key=self._result_cache_key(scope,query,kwargs)
            if key is not None and key in self._results:
                result=self.search(scope,query,**kwargs)
                result['overlap']={'skipped':'result-cache-hit','microbatch_delay_ms':0}
                return result
            identity=getattr(getattr(encoder,'profile',None),'id',kwargs.get('model_id'))
            if (identity,query) in self._cache:
                result=self.search(scope,query,**kwargs)
                result['overlap']={'skipped':'query-vector-cache-hit','microbatch_delay_ms':0}
                return result
            with ThreadPoolExecutor(max_workers=1,thread_name_prefix='thm-encoder') as pool:
                future=pool.submit(encoder,[query]);self._query_future=future
                try:
                    result=self.search(scope,query,**kwargs)
                    result['overlap']={'cpu':'SQLite/FTS','accelerator':'query_embedding','scoring':kwargs.get('scorer','numpy_reference'),'microbatch_delay_ms':0}
                    return result
                finally:
                    self._query_future=None;future.cancel()

    def _fts(self, table, scope, tokens, limit, contextual=False):
        if not tokens:
            return []
        if table not in ('literal', 'lexical'):
            raise ValueError('invalid FTS table')
        weights = '1.0,0.12,0.05' if contextual else ('1.0,0.0,0.02' if table == 'lexical' else '1.0,0.0')
        sql = f'''SELECT d.rowid FROM {table} JOIN docs d ON d.rowid={table}.rowid
          WHERE {table} MATCH ? AND d.scope=? ORDER BY bm25({table},{weights}),d.id LIMIT ?'''
        start=time.perf_counter()
        result=[r[0] for r in self.db.execute(sql, (match_query(tokens), scope, limit)).fetchall()]
        self._fts_elapsed_ms=getattr(self,'_fts_elapsed_ms',0.0)+(time.perf_counter()-start)*1000
        return result

    def _rank_candidates(self, scope, query, ranked):
        """Identity projection; research subclasses may ablate derived ranking."""
        return ranked

    def _pack_candidates(self, expanded, budget, query):
        blocks, selected = [], []
        used = 0
        byte_counter = type(self.counter) is TokenCounter and self.counter.encode is None
        for row in expanded:
            label = json.dumps({'id': row['id'], 'speaker': row['speaker'], 'date': row['timestamp']}, ensure_ascii=False)
            block = f"[source {label}]\n{row['text']}"
            if byte_counter:
                units = used + len(block.encode('utf-8')) + (2 if blocks else 0)
            else:
                units = self._count('\n\n'.join(blocks + [block]))
            if units <= budget:
                used = units
                blocks.append(block)
                selected.append({'id': row['id'], 'hash': row['hash'], 'source': row['source'],
                                 'complete': True, 'text': row['text']})
            # Oversized turns are skipped rather than terminating the packing pass.
        context = '\n\n'.join(blocks)
        final_units = self._count(context)
        if final_units > budget:
            raise ValueError('counter changed while packing; final context exceeds budget')
        return context, selected, final_units

    def _lexical_channels(self,scope,query,mode,candidate_limit):
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
        return channels

    def _search(self, scope: str, query: str, *, budget=600, mode='sparse', candidate_limit=100,
               neighbor_turns=0, encoder=None, model_id=None, entity_projection=False, features=None, diagnostics=False, scorer='numpy_reference') -> dict:
        start = time.perf_counter()
        from .features import RetrievalFeatures
        features = RetrievalFeatures.parse(features)
        if type(diagnostics) is not bool:raise ValueError('diagnostics must be boolean')
        if scorer not in ('numpy_reference','torch_cpu','torch_cuda'):raise ValueError('unsupported dense scorer')
        if type(entity_projection) is not bool:raise ValueError('entity projection requires explicit boolean')
        entity_projection = entity_projection or features.entity
        self._last_dense_diagnostics = {}
        self._fts_elapsed_ms = 0.0
        if not scope or not isinstance(query, str) or not query.strip():
            raise ValueError('nonempty scope and query required')
        if type(budget) is not int or not 0 <= budget <= 32768:
            raise ValueError('budget must be an integer from 0 to 32768')
        if (mode not in ('literal', 'sparse', 'hybrid', 'dense') or type(candidate_limit) is not int
                or not 1 <= candidate_limit <= 1000 or type(neighbor_turns) is not int
                or neighbor_turns not in (0, 1, 2)):
            raise ValueError('invalid retrieval settings')
        if type(entity_projection) is not bool or (entity_projection and mode not in ('sparse', 'hybrid')):
            raise ValueError('entity projection requires sparse/hybrid mode and an explicit boolean')
        if len(query) > 16000:
            raise ValueError('query too long')
        generation = self.db.execute('SELECT generation FROM scopes WHERE scope=?', (scope,)).fetchone()
        if generation is None:
            raise ValueError('scope not indexed')
        if budget == 0:
            return {'scope': scope, 'generation': generation[0], 'mode': mode, 'context': '',
                    'selected': [], 'ranked_ids': [], 'candidate_count': 0,
                    'budget': 0, 'budget_used': 0, 'counter': getattr(self.counter, 'name', 'caller_supplied'),
                    'timing_ms': {'sparse': 0.0, 'query_embedding': 0.0, 'retrieval_total': 0.0,
                                  'pack': 0.0, 'total': (time.perf_counter()-start)*1000},
                    'query_embedding_cache_hit': False, 'semantic_encoder_used': False,
                    'answer_generated': False, 'empty_reason': 'zero_budget', 'result_cache_hit': False}
        prepared=getattr(self,'_batch_lexical',None)
        channels=list(prepared[query]) if prepared is not None and query in prepared else self._lexical_channels(scope,query,mode,candidate_limit)
        if features.explicit_alias:
            from .features import AliasIndex
            channels.append(AliasIndex(self.rows(scope),features.aliases).lookup(query,candidate_limit))
        sparse_ms = (time.perf_counter() - start) * 1000
        embedding_ms, query_cached = 0.0, False
        if mode in ('hybrid', 'dense'):
            if encoder is None or not model_id:
                raise ValueError('dense mode requires an explicit local encoder and model identity')
            if getattr(encoder, 'model_id', model_id) != model_id:
                raise ValueError('encoder identity mismatch')
            dense, embedding_ms, query_cached = self._dense_search(scope, query, encoder, model_id, candidate_limit,scorer)
            channels.append(dense)
        fusion_start=time.perf_counter()
        scores = {}
        for channel in channels:
            for rank, rid in enumerate(dict.fromkeys(channel), 1):
                scores[rid] = scores.get(rid, 0.0) + 1.0 / (60.0 + rank)
        ordered = sorted(scores, key=lambda rid: (-scores[rid], rid))
        fusion_ms=(time.perf_counter()-fusion_start)*1000
        material_start=time.perf_counter()
        by_rowid = {}
        for offset in range(0, len(ordered), 500):
            batch = ordered[offset:offset+500]
            marks = ','.join('?' for _ in batch)
            for row in self.db.execute(f'SELECT * FROM docs WHERE scope=? AND rowid IN ({marks})', (scope, *batch)):
                by_rowid[row['rowid']] = dict(row)
        ranked = [by_rowid[rid] for rid in ordered]
        material_ms=(time.perf_counter()-material_start)*1000
        ranked = self._rank_candidates(scope, query, ranked)
        if entity_projection:
            from .entities import reorder
            ranked = reorder(ranked, query)
        if features.temporal or features.query_grammar:
            from .features import reorder
            ranked = reorder(ranked,query,features)
        expansion_receipt=[]
        if features.association:
            from .features import expand
            ranked,expansion_receipt=expand(ranked,self.rows(scope),features)
        ranked_ids = [r['id'] for r in ranked]
        retrieval_ms = (time.perf_counter() - start) * 1000
        # Optional adjacent context is actual text, not automatic credit for unseen IDs.
        expansion_start=time.perf_counter()
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
        neighbor_ms=(time.perf_counter()-expansion_start)*1000
        if features.segment:
            from .features import pack_segments
            context,selected,final_units=pack_segments(self,expanded,budget,query)
        else:
            context, selected, final_units = self._pack_candidates(expanded, budget, query)
        total_ms = (time.perf_counter()-start)*1000
        if diagnostics and self._last_dense_diagnostics:
            by_id={r['rowid']:r['id'] for r in self.rows(scope)}
            self._last_dense_diagnostics.update(candidate_ids=[by_id[rid] for rid in self._last_dense_diagnostics.get('candidate_rowids',[])],
                selected_ids=[r['id'] for r in selected],budget_cutoff=budget,budget_used=final_units,feature_components=features.identity())
        return {'scope': scope, 'generation': generation[0], 'mode': mode, 'context': context,
                'features':features.identity(),'candidate_expansion':expansion_receipt,
                'parent_locator_ids':[r.get('parent_id',r['id']) for r in selected],
                'complete_evidence_ids':[r['id'] for r in selected if r['complete']],
                'runtime_diagnostics':dict(self._last_dense_diagnostics) if diagnostics else None,
                'selected': selected, 'ranked_ids': ranked_ids, 'candidate_count': len(ranked),
                'budget': budget, 'budget_used': final_units,
                'counter': getattr(self.counter, 'name', 'caller_supplied'),
                'timing_ms': {'fts':self._fts_elapsed_ms,'fusion':fusion_ms,'row_materialization':material_ms,'neighbor_expansion':neighbor_ms,
                              'dense_matrix_load':self._last_dense_diagnostics.get('dense_matrix_load',0.0),'dense_scoring':self._last_dense_diagnostics.get('dense_scoring',0.0),
                              'sparse': sparse_ms, 'query_embedding': embedding_ms,
                              'retrieval_total': retrieval_ms, 'pack': total_ms-retrieval_ms,
                              'total': total_ms},
                'query_embedding_cache_hit': query_cached,
                'semantic_encoder_used': mode in ('hybrid', 'dense'),
                'answer_generated': False}

    def _result_cache_key(self,scope,query,kwargs):
        if type(self.counter) is not TokenCounter or not isinstance(scope,str) or not isinstance(query,str):return None
        # Type tags preserve the same validation boundary for search and overlap.
        settings=tuple(sorted((k,type(v).__name__,repr(v)) for k,v in kwargs.items() if k!='encoder'))
        return (scope,query,settings,id(kwargs.get('encoder')),getattr(getattr(kwargs.get('encoder'),'profile',None),'id',None),id(self.counter),self.counter.name,id(self.counter.encode))

    def search(self, scope, query, **kwargs):
        """One read snapshot; cache only deterministic native counters and explicit inputs."""
        started = time.perf_counter()
        with self._lock:
            self.db.execute('BEGIN')
            try:
                self._refresh_caches()
                key = self._result_cache_key(scope,query,kwargs)
                if key is not None and key in self._results:
                    out = copy.deepcopy(self._results[key])
                    self._results.move_to_end(key)
                    elapsed = (time.perf_counter()-started)*1000
                    out['result_cache_hit'] = True
                    out['query_embedding_cache_hit'] = bool(out['semantic_encoder_used'])
                    out['timing_ms'] = {'sparse': 0.0, 'query_embedding': 0.0,
                                        'retrieval_total': elapsed, 'pack': 0.0, 'total': elapsed}
                    return out
                out = self._search(scope, query, **kwargs)
                out['result_cache_hit'] = False
                if key is not None:
                    self._results[key] = copy.deepcopy(out)
                    if len(self._results) > 64:
                        self._results.popitem(last=False)
                return out
            finally:
                self.db.rollback()
