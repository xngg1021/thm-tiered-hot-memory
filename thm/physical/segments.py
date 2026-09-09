"""Immutable contiguous float32 shards, checked before manifest publication."""
from dataclasses import asdict
import hashlib
import json
import mmap
import os
from pathlib import Path
import struct
import tempfile
import time
from thm.runtime.identity import digest, validate_vectors
from thm.runtime.storage import pack, unpack
from .contracts import PhysicalTelemetry

MAGIC=b'THMSEG01'
MAX_HEADER=16*1024*1024
SCHEMA='''CREATE TABLE IF NOT EXISTS physical_placements(
 scope TEXT, profile TEXT, generation TEXT, manifest TEXT NOT NULL,
 PRIMARY KEY(scope,profile));'''


def sync_directory(path):
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)


def object_path(root, name):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('invalid physical root')
    if not isinstance(name,str) or len(name)!=68 or not name.endswith('.seg') or any(c not in '0123456789abcdef' for c in name[:-4]):
        raise ValueError('invalid immutable object locator')
    path=root/name
    if path.is_symlink():raise ValueError('symlink immutable object refused')
    return path


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def create(root, profile, generation, row_keys, vectors):
    root=Path(root)
    if not row_keys or len(set(tuple(r) for r in row_keys))!=len(row_keys):raise ValueError('empty/duplicate segment rows')
    validate_vectors(vectors,profile,len(row_keys))
    header={'schema':1,'embedding_profile_id':profile.id,'generation':generation,
        'dimension':profile.dimension,'dtype':'f32le','rows':len(row_keys),
        'row_order_sha256':digest(row_keys),'byte_length':len(row_keys)*profile.dimension*4}
    encoded=json.dumps(header,sort_keys=True,separators=(',',':')).encode()
    if root.is_symlink() or not root.is_dir():raise ValueError('existing nonsymlink storage root required')
    fd,temp=tempfile.mkstemp(prefix='.thm-build-',dir=root)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(MAGIC);f.write(struct.pack('<I',len(encoded)));f.write(encoded)
            h=hashlib.sha256()
            for vector in vectors:
                raw=pack(vector);h.update(raw);f.write(raw)
            f.write(h.digest());f.flush();os.fsync(f.fileno())
        sha=file_sha(temp);name=sha+'.seg'
        manifest={**header,'object_sha256':sha,'object_name':name,'root':str(root.resolve()),'publication':'verified'}
        read_segment(temp,manifest,profile,generation,row_keys)
        # Exclusive atomic name publication, no replace/no silent overwrite.
        os.link(temp,object_path(root,name));sync_directory(root)
        return manifest
    finally:
        Path(temp).unlink(missing_ok=True)


def read_segment(path, manifest, profile, generation, row_keys, *, mode='buffered', telemetry=None):
    if mode not in ('buffered','mmap'):raise ValueError('unknown segment read mode')
    if Path(path).is_symlink():raise ValueError('symlink segment refused')
    if manifest['embedding_profile_id']!=profile.id or manifest['generation']!=generation:
        raise ValueError('segment profile/generation mismatch')
    if manifest['row_order_sha256']!=digest(row_keys):raise ValueError('segment row-order mismatch')
    start=time.perf_counter()
    with Path(path).open('rb') as f:
        size=os.fstat(f.fileno()).st_size
        if size<44:raise ValueError('truncated segment')
        mapped=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) if mode=='mmap' else None
        try:
            stream=mapped if mapped is not None else f
            h=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            if h.hexdigest()!=manifest['object_sha256']:raise ValueError('segment checksum mismatch')
            stream.seek(0)
            if stream.read(8)!=MAGIC:raise ValueError('segment magic mismatch')
            length=struct.unpack('<I',stream.read(4))[0]
            if length>MAX_HEADER or length>size-44:raise ValueError('invalid segment header length')
            header=json.loads(stream.read(length))
            for key in ('schema','embedding_profile_id','generation','dimension','dtype','rows','row_order_sha256','byte_length'):
                if header.get(key)!=manifest.get(key):raise ValueError('segment header mismatch: '+key)
            if header['schema']!=1 or header['dtype']!='f32le' or header['dimension']!=profile.dimension or header['rows']!=len(row_keys):
                raise ValueError('segment schema/dimension mismatch')
            payload_bytes=len(row_keys)*profile.dimension*4
            if header['byte_length']!=payload_bytes or size!=12+length+payload_bytes+32:raise ValueError('segment length mismatch')
            vectors=[];payload_hash=hashlib.sha256()
            for _ in row_keys:
                raw=stream.read(profile.dimension*4);payload_hash.update(raw)
                vectors.append(unpack(raw,profile.dimension))
            if stream.read(32)!=payload_hash.digest():raise ValueError('payload checksum mismatch')
            validate_vectors(vectors,profile,len(row_keys))
        finally:
            if mapped is not None:mapped.close()
    if telemetry is not None:
        telemetry.bytes_requested+=payload_bytes;telemetry.bytes_read+=size*2
        telemetry.transfer_seconds+=time.perf_counter()-start;telemetry.access_mode=mode
    return vectors


def current(index, scope, profile_id):
    try:row=index.db.execute('SELECT manifest FROM physical_placements WHERE scope=? AND profile=?',(scope,profile_id)).fetchone()
    except __import__('sqlite3').OperationalError:return None
    return json.loads(row[0]) if row else None


def export(index, scope, profile, root, *, mode='mmap', before_publish=None):
    index._writable()
    if mode not in ('buffered','mmap'):raise ValueError('invalid read mode')
    with index._lock:
        index.db.execute('BEGIN')
        try:
            generation=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()[0]
            complete=index.db.execute('SELECT generation,count FROM vector_generations WHERE scope=? AND profile=?',(scope,profile.id)).fetchone()
            docs=index.rows(scope);keys=[[r['id'],r['hash']] for r in docs]
            rows=list(index.db.execute('SELECT v.vector,v.dimension,v.dtype FROM docs d JOIN vectors_v2 v ON d.scope=v.scope AND d.id=v.id AND d.hash=v.hash WHERE d.scope=? AND v.profile=? ORDER BY d.rowid',(scope,profile.id)))
            if not complete or tuple(complete)!=(generation,len(docs)) or len(rows)!=len(docs):raise ValueError('incomplete profile generation')
            if any(r[1]!=profile.dimension for r in rows):raise ValueError('profile dimension mismatch')
            values=[unpack(r[0],r[1]) if r[2]=='f32le' else json.loads(r[0]) for r in rows]
        finally:index.db.rollback()
    manifest=create(root,profile,generation,keys,values)
    manifest.update(target_id='local-'+digest(str(Path(root).resolve()))[:20],read_mode=mode)
    if before_publish:before_publish()
    with index._lock:
        index.db.execute('BEGIN IMMEDIATE')
        try:
            actual=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
            if not actual or actual[0]!=generation:raise ValueError('source generation changed before publication')
            index.db.execute(SCHEMA)
            index.db.execute('INSERT OR REPLACE INTO physical_placements VALUES(?,?,?,?)',(scope,profile.id,generation,json.dumps(manifest,sort_keys=True)))
            index.db.commit();index._clear_caches()
        except Exception:index.db.rollback();raise
    return {k:v for k,v in manifest.items() if k!='root'}


def load(index,scope,profile,generation):
    manifest=current(index,scope,profile.id)
    if manifest is None:return None
    docs=index.rows(scope);keys=[[r['id'],r['hash']] for r in docs]
    telemetry=PhysicalTelemetry(manifest['target_id'])
    values=read_segment(object_path(manifest['root'],manifest['object_name']),manifest,profile,generation,keys,
        mode=manifest['read_mode'],telemetry=telemetry)
    index.physical_io_receipt=telemetry.receipt()
    return [r['rowid'] for r in docs],values
