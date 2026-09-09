"""Explicit storage operator commands; all output files are exclusive."""
import argparse
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
from thm.runtime.receipts import write_receipt
from thm.runtime.identity import EmbeddingProfile
from .probe import probe
from .adapters import capabilities
from .contracts import DataRole,PlacementIntent,StorageProfile


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('probe','doctor','benchmark','profile','plan','placements','export','migrate','verify'):
        p=sub.add_parser(name);p.add_argument('--json',action='store_true');p.add_argument('--output')
        if name in ('probe','doctor','benchmark','profile','plan','export','migrate'):p.add_argument('--root',required=True)
        if name in ('placements','export','migrate','verify'):p.add_argument('--db',required=True)
        if name in ('export','migrate','verify'):p.add_argument('--scope',required=True);p.add_argument('--profile-id',required=True)
        if name in ('export','migrate','plan'):p.add_argument('--dry-run',action='store_true')
        if name in ('benchmark','profile'):
            p.add_argument('--seconds',type=float,default=5);p.add_argument('--scratch-mib',type=int,default=8);p.add_argument('--concurrency',type=int,choices=(1,2,4),default=1)
        if name=='plan':
            p.add_argument('--storage-profile',required=True);p.add_argument('--role',choices=[r.value for r in DataRole],default='vector_segment')
            p.add_argument('--workload',choices=('interactive','bulk','background','archive'),default=None)
            p.add_argument('--capacity',type=int,default=0);p.add_argument('--p95-ms',type=float)
        if name=='migrate':
            p.add_argument('--journal',required=True);p.add_argument('--resume',action='store_true');p.add_argument('--retire-source',action='store_true')
        if name in ('export','verify'):p.add_argument('--read-mode',choices=('buffered','mmap'),default='mmap')
    args=parser.parse_args(argv)
    if args.output and Path(args.output).exists():raise FileExistsError('output already exists')
    if args.command in ('probe','doctor','benchmark','profile','plan'):
        target,topology=probe(args.root)
        result={'target':target.public(),'topology':asdict(topology),'capabilities':capabilities()}
        if args.command in ('benchmark','profile'):
            if not args.output:parser.error('benchmark/profile require --output')
            from .benchmark import benchmark
            profile=benchmark(target,seconds=args.seconds,scratch_bytes=args.scratch_mib*1024*1024,concurrency=args.concurrency)
            result={'target':target.public(),'profile':asdict(profile),'profile_id':profile.id}
        elif args.command=='plan':
            from .planner import plan
            profile=StorageProfile(**json.loads(Path(args.storage_profile).read_text())['profile'])
            result=plan(PlacementIntent(DataRole(args.role),workload=args.workload,capacity_required=args.capacity,p95_latency_ms=args.p95_ms),[target],[profile])
    else:
        from thm.retrieval import SearchIndex
        from .segments import current,export,load
        readonly=args.command in ('placements','verify') or getattr(args,'dry_run',False)
        with closing(SearchIndex(args.db,readonly=readonly)) as index:
            if args.command=='placements':
                exists=index.db.execute("SELECT 1 FROM sqlite_master WHERE name='physical_placements'").fetchone()
                rows=[json.loads(r[0]) for r in index.db.execute('SELECT manifest FROM physical_placements')] if exists else []
                result={'placements':[{k:v for k,v in r.items() if k!='root'} for r in rows]}
            else:
                row=index.db.execute('SELECT identity FROM embedding_profiles WHERE profile=?',(args.profile_id,)).fetchone()
                if not row:raise ValueError('profile missing')
                data=json.loads(row[0]);data.pop('embedding_profile_id');profile=EmbeddingProfile(**data)
                if args.command=='export':
                    result={'action':'export','dry_run':True,'profile_id':profile.id} if args.dry_run else export(index,args.scope,profile,args.root,mode=args.read_mode)
                elif args.command=='verify':
                    generation=index.db.execute('SELECT generation FROM scopes WHERE scope=?',(args.scope,)).fetchone()[0]
                    m=current(index,args.scope,profile.id)
                    if m is None:raise ValueError('external placement missing')
                    from .segments import read_segment,object_path
                    keys=[[r['id'],r['hash']] for r in index.rows(args.scope)]
                    values=read_segment(object_path(m['root'],m['object_name']),m,profile,generation,keys,mode=args.read_mode)
                    result={'status':'verified','rows':len(values),'object_sha256':m['object_sha256'],'read_mode':args.read_mode}
                else:
                    from .migration import begin,resume
                    if args.dry_run:result={'action':'migration','dry_run':True,'source':{k:v for k,v in (current(index,args.scope,profile.id) or {}).items() if k!='root'},'retire_source':args.retire_source}
                    else:
                        if args.resume:
                            saved=json.loads((Path(args.journal)/'plan.json').read_text())
                            if saved['scope']!=args.scope or saved['profile']['embedding_profile_id']!=args.profile_id or Path(saved['target']['root'])!=Path(args.root).resolve() or saved['retire_source']!=args.retire_source:
                                raise ValueError('resume must match exact target/profile/retirement intent')
                        else:begin(index,args.scope,profile,args.root,args.journal,retire_source=args.retire_source)
                        result=resume(index,args.journal)
    if args.output:write_receipt(args.output,result)
    print(json.dumps(result,indent=2,sort_keys=True));return 0
