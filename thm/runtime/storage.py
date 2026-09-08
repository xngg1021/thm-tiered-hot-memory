"""Forward-only profile vectors and exact-input cache; stdlib float32 storage."""
import hashlib
import json
import math
import sqlite3
import struct
import threading
from pathlib import Path
from ..sqlite_guard import connect_derived
from .identity import validate_vectors

SCHEMA = '''
CREATE TABLE IF NOT EXISTS embedding_profiles(profile TEXT PRIMARY KEY,identity TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vector_generations(scope TEXT,profile TEXT,generation TEXT,count INTEGER,PRIMARY KEY(scope,profile));
CREATE TABLE IF NOT EXISTS vectors_v2(scope TEXT,id TEXT,hash TEXT,profile TEXT,dimension INTEGER,dtype TEXT,vector BLOB,PRIMARY KEY(scope,id,profile));
'''


def pack(vector):
    if not vector or any(type(v) not in (float,int) or not math.isfinite(v) for v in vector): raise ValueError('invalid vector')
    try: return struct.pack('<'+'f'*len(vector),*vector)
    except (OverflowError,struct.error) as e: raise ValueError('not finite float32') from e


def unpack(blob, dimension, dtype='f32le'):
    if type(dimension) is not int or not 1 <= dimension <= 65536 or dtype != 'f32le' or not isinstance(blob,bytes) or len(blob)!=4*dimension:
        raise ValueError('malformed/truncated vector BLOB')
    v = list(struct.unpack('<'+'f'*dimension,blob))
    if any(not math.isfinite(x) for x in v) or not any(v): raise ValueError('invalid finite/nonzero vector')
    return v


class EmbeddingCache:
    """No scope/source/tier data enters this compute-only derived database."""
    def __init__(self,path):
        self.db=connect_derived(path,{'embedding_cache'},shared_thread=True)
        self.db.execute('CREATE TABLE IF NOT EXISTS embedding_cache(profile TEXT,input_sha TEXT,input_bytes INTEGER,dimension INTEGER,vector BLOB,PRIMARY KEY(profile,input_sha))')
        self.db.commit(); self.lock=threading.RLock(); self.hits=0; self.misses=0
    def encode(self,encoder,texts):
        profile=encoder.profile; result=[None]*len(texts); missing={}
        with self.lock:
            for i,text in enumerate(texts):
                raw=text.encode('utf-8'); key=hashlib.sha256(raw).hexdigest()
                row=self.db.execute('SELECT input_bytes,dimension,vector FROM embedding_cache WHERE profile=? AND input_sha=?',(profile.id,key)).fetchone()
                if row:
                    if row[0]!=len(raw) or row[1]!=profile.dimension: raise ValueError('cache identity/corruption mismatch')
                    result[i]=unpack(row[2],row[1]);validate_vectors([result[i]],profile,1);self.hits+=1
                else:
                    self.misses+=1;missing.setdefault(key,{'text':text,'positions':[]})['positions'].append(i)
        if missing:
            values=validate_vectors(encoder.encode_many([v['text'] for v in missing.values()]),profile,len(missing))
            with self.lock, self.db:
                for (key,item),vector in zip(missing.items(),values):
                    blob=pack(vector)
                    self.db.execute('INSERT OR IGNORE INTO embedding_cache VALUES(?,?,?,?,?)',(profile.id,key,len(item['text'].encode()),profile.dimension,blob))
                    stored=self.db.execute('SELECT vector FROM embedding_cache WHERE profile=? AND input_sha=?',(profile.id,key)).fetchone()[0]
                    if stored!=blob: raise ValueError('same profile/input produced different cached vectors')
                    for i in item['positions']: result[i]=unpack(blob,profile.dimension)
        return result
    def close(self):
        with self.lock: self.db.close()


def migrate_legacy(index,scope,model_id,profile,expected_generation):
    """Explicit operator certification of legacy identity; preserve legacy vectors."""
    index._writable()
    with index._lock:
        index.db.execute('BEGIN IMMEDIATE')
        try:
            generation=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
            if not generation or generation[0]!=expected_generation: raise ValueError('source generation changed')
            if index.db.execute('SELECT 1 FROM vector_generations WHERE scope=? AND profile=?',(scope,profile.id)).fetchone(): raise ValueError('profile generation already exists')
            rows=list(index.db.execute('SELECT v.id,v.hash,v.vector FROM vectors v JOIN docs d ON d.scope=v.scope AND d.id=v.id AND d.hash=v.hash WHERE v.scope=? AND v.model=? ORDER BY d.rowid',(scope,model_id)))
            count=index.db.execute('SELECT COUNT(*) FROM docs WHERE scope=?',(scope,)).fetchone()[0]
            if not rows or len(rows)!=count: raise ValueError('incomplete legacy generation')
            values=[json.loads(r[2]) for r in rows];validate_vectors(values,profile,len(rows))
            index.db.execute('INSERT OR IGNORE INTO embedding_profiles VALUES(?,?)',(profile.id,json.dumps(profile.identity(),sort_keys=True)))
            index.db.executemany('INSERT INTO vectors_v2 VALUES(?,?,?,?,?,?,?)',[(scope,r[0],r[1],profile.id,profile.dimension,'f32le',pack(v)) for r,v in zip(rows,values)])
            index.db.execute('INSERT INTO vector_generations VALUES(?,?,?,?)',(scope,profile.id,generation[0],count))
            index.db.commit();index._clear_caches()
            return {'schema':1,'action':'legacy-json-to-profile-blob','source_generation':generation[0],'legacy_model_id':model_id,'embedding_profile_id':profile.id,'vectors':count,'legacy_preserved':True}
        except Exception: index.db.rollback();raise
