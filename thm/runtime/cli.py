"""Explicit runtime setup; core is available before any semantic calibration."""
import argparse
import json
from pathlib import Path
import sys
from .hardware import probe
from .backends import available
from .receipts import write_receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('doctor','probe','status'):
        p=sub.add_parser(name);p.add_argument('--json',dest='output');p.add_argument('--profile');p.add_argument('--model-path')
    p=sub.add_parser('autotune');p.add_argument('--model-path',required=True);p.add_argument('--model-id',required=True);p.add_argument('--output',required=True)
    p.add_argument('--policy',choices=['reference','auto-safe','auto-throughput','approximate-performance'],default='auto-safe')
    p.add_argument('--workload',choices=['interactive','bulk','background'],default='interactive');p.add_argument('--device',action='append',choices=['cpu','cuda','mps'])
    p.add_argument('--max-candidates',type=int,default=12);p.add_argument('--timeout',type=int,default=180)
    p=sub.add_parser('prepare');p.add_argument('--model-path',required=True);p.add_argument('--backend',required=True);p.add_argument('--cache-root',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('invalidate-profile');p.add_argument('--profile',required=True);p.add_argument('--output',required=True);p.add_argument('--reason',default='explicit-user-invalidation')
    p=sub.add_parser('import-dispatch');p.add_argument('--input',required=True);p.add_argument('--embedding-profile-id',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('migrate-vectors');p.add_argument('--db',required=True);p.add_argument('--scope',required=True);p.add_argument('--legacy-model-id',required=True)
    p.add_argument('--embedding-profile',required=True);p.add_argument('--expected-generation',required=True);p.add_argument('--certify-legacy-identity',action='store_true');p.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        if getattr(args,'output',None) and Path(args.output).exists():raise ValueError('output already exists')
        if args.command in ('doctor','probe','status'):
            h=probe();result={'schema':1,'core_only_available':True,'semantic_accelerators':available(),'hardware':h.identity(),
                'semantic_status':'explicit-local-model-and-backend-required','reason':'core-ready; semantic setup is optional',
                'selected_profile':None,'profile_freshness':'not-configured','generation_calls':0,'model_downloads':0}
            if args.command=='probe':
                from .capabilities import backend_probe
                result['hardware']['accelerators']=backend_probe()
            if args.profile:
                from .profiles import load_profile,fingerprint
                from .identity import manifest
                p=load_profile(args.profile);result['selected_profile']=p.identity()
                result['profile_freshness']='unknown-model-path-required'
                if args.model_path:
                    from .identity import EmbeddingProfile,digest
                    current=manifest(args.model_path)['sha256'];source=current;derived=None
                    data=json.loads(Path(args.profile).read_text())
                    identity=next((t.get('result',{}).get('identity') for t in data.get('trials',[]) if t.get('result',{}).get('identity',{}).get('embedding_profile_id')==p.embedding_profile_id),None)
                    if p.backend!='torch_fp32':
                        prep=json.loads((Path(args.model_path)/'thm-preparation.json').read_text())
                        if prep['derived_manifest_sha256']!=current or prep['backend']!=p.backend:raise ValueError('derived model identity changed')
                        source=prep['source_manifest_sha256'];derived=current
                        if identity is None:raise ValueError('derived freshness requires calibration embedding identity')
                        fields={k:v for k,v in identity.items() if k in EmbeddingProfile.__dataclass_fields__}
                        fields.update(source_manifest_sha256=source,derived_manifest_sha256=derived,
                            transformation=digest({k:prep[k] for k in ('backend','precision','source_manifest_sha256','transformation','model_file','converter_versions')}))
                        if EmbeddingProfile(**fields).id!=p.embedding_profile_id:raise ValueError('derived embedding profile changed')
                    p.require_fresh(fingerprint(h,source,derived,p.embedding_profile_id));result['profile_freshness']='fresh'

        elif args.command=='autotune':
            from .autotune import autotune
            result=autotune(args.model_path,args.model_id,backends=[('torch_fp32',d) for d in (args.device or ['cpu'])],
                policy=args.policy,workload=args.workload,maximum=args.max_candidates,timeout=args.timeout,
                plan_callback=lambda entries:write_receipt(str(args.output)+'.plan.json',{'entries':entries,'phase':'before-execution'}))
        elif args.command=='prepare':
            from .prepare import prepare
            result=prepare(args.model_path,args.cache_root,args.backend)
        elif args.command=='invalidate-profile':
            import hashlib
            raw=Path(args.profile).read_bytes();data=json.loads(raw)
            result={'status':'invalidated','profile_artifact_sha256':hashlib.sha256(raw).hexdigest(),
                'runtime_profile_id':data.get('runtime_profile',data).get('runtime_profile_id'),'reason':args.reason}
            write_receipt(str(args.profile)+'.invalidated',result)
        elif args.command=='import-dispatch':
            from .receipts import import_dispatch
            result=import_dispatch(args.input,args.embedding_profile_id)
        elif args.command=='migrate-vectors':
            if not args.certify_legacy_identity:raise ValueError('explicit legacy identity certification required')
            from .identity import EmbeddingProfile
            from .storage import migrate_legacy
            from ..retrieval import SearchIndex
            data=json.loads(Path(args.embedding_profile).read_text());profile=EmbeddingProfile(**{k:v for k,v in data.items() if k in EmbeddingProfile.__dataclass_fields__})
            index=SearchIndex(args.db)
            try:result=migrate_legacy(index,args.scope,args.legacy_model_id,profile,args.expected_generation)
            finally:index.close()
        if getattr(args,'output',None):write_receipt(args.output,result)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False));return 1 if result.get('status')=='failed' else 0
    except Exception as exc:
        print(json.dumps({'status':'error','error_type':type(exc).__name__,'message':str(exc) if isinstance(exc,ValueError) else 'runtime operation failed'}),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
