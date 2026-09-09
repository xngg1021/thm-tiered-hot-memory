"""Explicit, restartable copy/verify/publish. Source retirement is opt-in."""
import json
import os
from pathlib import Path
import tempfile
from thm.runtime.identity import EmbeddingProfile,digest
from .segments import current,object_path,read_segment,sync_directory,file_sha

STAGES=('before-copy','partial-copy','after-copy-before-verify','after-verify-before-publish',
        'after-publish-before-cleanup','during-cleanup')


def durable(path,payload):
    path=Path(path)
    with path.open('x',encoding='utf-8') as f:
        json.dump(payload,f,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    sync_directory(path.parent)


def begin(index,scope,profile,target_root,journal,*,retire_source=False):
    index._writable()
    source=current(index,scope,profile.id)
    if source is None:raise ValueError('published external segment required')
    root=Path(target_root)
    if root.is_symlink() or not root.is_dir() or root.resolve()==Path(source['root']).resolve():raise ValueError('distinct existing target root required')
    with index._lock:
        generation=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()[0]
        keys=[[r['id'],r['hash']] for r in index.rows(scope)]
        read_segment(object_path(source['root'],source['object_name']),source,profile,generation,keys)
    journal=Path(journal);journal.mkdir(parents=True,exist_ok=False)
    target={**source,'root':str(root.resolve()),'target_id':'local-'+digest(str(root.resolve()))[:20]}
    data={'schema':1,'scope':scope,'profile':profile.identity(),'source':source,'target':target,
        'retire_source':retire_source,'row_keys':keys,'index_identity':digest(str(index.path))}
    durable(journal/'plan.json',data)
    return {'status':'planned','object_sha256':source['object_sha256'],'retire_source':retire_source}


def resume(index,journal,*,inject=None):
    index._writable();journal=Path(journal)
    if journal.is_symlink():raise ValueError('symlink journal refused')
    data=json.loads((journal/'plan.json').read_text())
    if data['index_identity']!=digest(str(index.path)):raise ValueError('migration index identity mismatch')
    p=dict(data['profile']);p.pop('embedding_profile_id');profile=EmbeddingProfile(**p)
    source=data['source'];target=data['target'];scope=data['scope'];keys=data['row_keys']
    src=object_path(source['root'],source['object_name']);dst=object_path(target['root'],target['object_name'])
    # Serialize recovery of this journal without stealing stale locks. A crash
    # releases the SQLite lock, and publication comparisons protect other journals.
    index.db.execute('BEGIN IMMEDIATE')
    try:
        gen=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
        active=current(index,scope,profile.id)
        if not gen or gen[0]!=source['generation'] or active not in (source,target):raise ValueError('migration predecessor changed')
        if [[r['id'],r['hash']] for r in index.rows(scope)]!=keys:raise ValueError('migration rows changed')
    finally:index.db.rollback()
    def checkpoint(stage,published=False):
        receipt={'schema':1,'stage':stage,'object_sha256':source['object_sha256'],
            'source_valid':src.is_file() and file_sha(src)==source['object_sha256'],
            'target_verified':dst.is_file() and file_sha(dst)==target['object_sha256'],
            'published':published,'cleanup_safe':published and data['retire_source'],
            'migration_bytes':target['byte_length']}
        # Exclusive append-only attempts; old interrupted records remain intact.
        fd,name=tempfile.mkstemp(prefix='receipt-',suffix='.json',dir=journal);os.close(fd)
        with open(name,'w') as f:json.dump(receipt,f,sort_keys=True);f.flush();os.fsync(f.fileno())
        sync_directory(journal)
        if inject:inject(stage)
        return receipt
    published=active==target
    if not published:
        read_segment(src,source,profile,source['generation'],keys)
        checkpoint('before-copy')
        if not dst.exists():
            fd,name=tempfile.mkstemp(prefix='.thm-migrate-',dir=dst.parent)
            try:
                with os.fdopen(fd,'wb') as out,src.open('rb') as stream:
                    first=stream.read(4096);out.write(first);out.flush();checkpoint('partial-copy')
                    for chunk in iter(lambda:stream.read(1024*1024),b''):out.write(chunk)
                    out.flush();os.fsync(out.fileno())
                checkpoint('after-copy-before-verify')
                read_segment(name,target,profile,source['generation'],keys)
                try:os.link(name,dst)
                except FileExistsError:read_segment(dst,target,profile,source['generation'],keys)
                sync_directory(dst.parent)
            finally:Path(name).unlink(missing_ok=True)
        read_segment(dst,target,profile,source['generation'],keys)
        checkpoint('after-verify-before-publish')
        with index._lock:
            index.db.execute('BEGIN IMMEDIATE')
            try:
                gen=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(scope,)).fetchone()
                if not gen or gen[0]!=source['generation'] or current(index,scope,profile.id) not in (source,target):raise ValueError('migration predecessor changed before publish')
                index.db.execute('UPDATE physical_placements SET manifest=? WHERE scope=? AND profile=?',(json.dumps(target,sort_keys=True),scope,profile.id))
                index.db.commit();index._clear_caches()
            except Exception:index.db.rollback();raise
    read_segment(dst,target,profile,source['generation'],keys)
    checkpoint('after-publish-before-cleanup',True)
    if data['retire_source']:
        with index._lock:
            index.db.execute('BEGIN IMMEDIATE')
            try:
                if current(index,scope,profile.id)!=target:raise ValueError('cleanup publication changed')
                read_segment(dst,target,profile,source['generation'],keys)
                for row in index.db.execute('SELECT manifest FROM physical_placements'):
                    other=json.loads(row[0])
                    if (other['root'],other['object_name'])==(source['root'],source['object_name']):raise ValueError('source still referenced')
                checkpoint('during-cleanup',True)
                if src.exists():
                    if file_sha(src)!=source['object_sha256']:raise ValueError('source changed before cleanup')
                    src.unlink();sync_directory(src.parent)
                index.db.commit()
            except Exception:index.db.rollback();raise
    return checkpoint('complete',True)
