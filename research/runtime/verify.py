"""One reserved local verification package: calibrate, shortlist, measure, compare."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from research.runtime.bounds import campaign, estimate, ReferenceArtifactKey, semantic_identity, reuse
from thm.runtime.hardware import probe,versions
from thm.runtime.capabilities import backend_probe
from thm.runtime.identity import manifest,implementation_identity
from thm.runtime.receipts import write_receipt
from thm.runtime.autotune import autotune
from thm.runtime.prepare import prepare
from thm.runtime.backends import available
from research.runtime.census import census
from thm.retrieval import TokenCounter

LOCOMO_SHA='79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4'
LME_SHA='08d8dad4be43ee2049a22ff5674eb86725d0ce5ff434cde2627e5e8e7e117894'


def load_dataset(path,expected):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('dataset differs from pinned machine evidence')
    return json.loads(raw)


def plan(model_path,locomo,lme,root,model_id,*,include_approximate=False):
    root=Path(root)
    common=['--model-path',str(model_path),'--model-id',model_id,'--counter','cl100k_base','--modes','literal','sparse','dense','hybrid','--budgets','300','600','1200']
    arms=[{'name':'cpu-reference','backend':'torch_fp32','device':'cpu','policy':'reference','batch':64,'query_batch':1},
          {'name':'cuda-reference','backend':'torch_fp32','device':'cuda','policy':'reference','batch':64,'query_batch':1}]
    return {'schema':1,'stages':['hardware-probe','local-model-preparation','autotune-shortlist','lme-census','reference-and-winner-matrices','retrieval-feature-ab','parity-and-diagnostics','comparison'],
        'reference_arms':arms,'datasets':{'locomo':LOCOMO_SHA,'lme':LME_SHA},'output_namespace':root.name,
        'policies':['reference','auto-safe','auto-throughput']+(['approximate-performance'] if include_approximate else []),
        'document_batch_candidates':[16,32,64,128,256],'query_batch_candidates':[1,4,8,32],
        'mode_budget_cartesian_explosion':False,'features':['entity','explicit_alias','temporal','query_grammar','segment','association'],
        'performance_acceptance':'pending-real-local-runtime','generation_calls':0}


def execute(args):
    limits=campaign(getattr(args,'mode','acceptance'), full_campaign=getattr(args,'full_campaign',False),
        acknowledge=getattr(args,'acknowledge_multi_hour_run',False), wall_seconds=getattr(args,'wall_seconds',3600),
        approximate=args.include_approximate, retrieval_ab=args.retrieval_ab)
    deadline=time.monotonic()+limits['wall_seconds']
    root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=False)
    planned=plan(args.model_path,args.locomo_dataset,args.lme_dataset,root,args.model_id,include_approximate=args.include_approximate)
    planned.update(limits)
    if limits['mode']=='smoke':planned['policies']=['reference','auto-safe']
    planned['stages']=['headless-ignition','storage-probe','hardware-probe','backend-preparation','bounded-autotune','measured-pilot','bounded-reference-and-winners','parity','comparison']
    if limits['extended_diagnostics']:planned['stages']+=['retrieval-feature-ab','extended-diagnostics']
    write_receipt(root/'plan.json',planned)
    if args.plan_only:return planned
    with (root/'headless.log').open('x') as log:
        ignition=subprocess.run([sys.executable,'-S','scripts/runtime_headless_probe.py'],stdout=log,stderr=subprocess.STDOUT,timeout=max(.01,deadline-time.monotonic()))
    if ignition.returncode:raise ValueError('headless ignition failed')
    from thm.physical.probe import probe as storage_probe
    target,topology=storage_probe(root)
    write_receipt(root/'storage.json',{'target':target.public(),'topology':asdict(topology)})
    from research.runtime.synthetic import smoke
    write_receipt(root/'synthetic.json',smoke())
    locomo=load_dataset(args.locomo_dataset,LOCOMO_SHA);lme=load_dataset(args.lme_dataset,LME_SHA)
    if not locomo or not lme:raise ValueError('nonempty pinned datasets required')
    source=manifest(args.model_path);hardware=probe();accelerators=backend_probe()
    git=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    dirty=subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,check=True).stdout
    if dirty.strip():raise ValueError('local verification requires a clean exact checkout')
    write_receipt(root/'hardware.json',{'hardware':hardware.identity(),'backend_probe':accelerators,'git_head':git,'implementation_sha256':implementation_identity(),
        'model_manifest_sha256':source['sha256'],'packages':versions(),'generation_calls':0,'observed_kernel_dispatch':None})
    write_receipt(root/'lme-census.json',census(lme if limits['mode']=='full-research' else lme[:limits['lme_limit']],TokenCounter('cl100k_base')))
    backend_paths={'torch_fp32':str(Path(args.model_path).resolve())};backends=[('torch_fp32','cpu')]
    cuda=any(x.get('cuda_available') is True for x in accelerators)
    if cuda:backends.append(('torch_fp32','cuda'))
    for backend,cap in available().items():
        if backend=='torch_fp32' or not cap['installed'] or (backend.endswith('int8') and not args.include_approximate):continue
        try:receipt=prepare(args.model_path,root/'derived-models',backend)
        except Exception as exc:receipt={'status':'failed','error_type':type(exc).__name__,'backend':backend}
        write_receipt(root/(backend+'-preparation.json'),receipt)
        if receipt.get('status')=='prepared':backend_paths[backend]=str((root/'derived-models'/receipt['artifact_locator']).resolve());backends.append((backend,'cpu'))
    tunes={};calibrations={}
    policies=[('auto-safe','interactive')] if limits['mode']=='smoke' else [('auto-safe','interactive'),('auto-throughput','bulk')]+([('approximate-performance','bulk')] if args.include_approximate else [])
    for policy,workload in policies:
        result=autotune(args.model_path,args.model_id,backends=backends,policy=policy,workload=workload,maximum=min(args.max_candidates,2 if limits['mode']=='smoke' else 6) if limits['mode']!='full-research' else args.max_candidates,backend_paths=backend_paths)
        write_receipt(root/(policy+'-autotune.json'),result)
        calibrations[policy]={'status':result.get('status','missing-status'),'artifact':policy+'-autotune.json','reason':result.get('reason')}
        if result.get('status')=='calibrated':tunes[policy]=result
    arms=list(planned['reference_arms'][:1])
    if cuda and limits['mode']!='smoke':arms.append(planned['reference_arms'][1])
    # Full matrices only for reference + measured winners, never every calibration point.
    for policy,tune in tunes.items():
        p=tune['runtime_profile'];arms.append({'name':policy,'backend':p['backend'],'device':p['device'],'policy':policy,
            'batch':p['document_batch_size'],'query_batch':p['query_batch_size'],'threads':p['threads'],'scorer':p['scorer'],'profile_file':str(root/(policy+'-autotune.json'))})
    if cuda and limits['mode']=='full-research':
        arms.append({'name':'cuda-batched-overlap','backend':'torch_fp32','device':'cuda','policy':'auto-throughput','batch':64,'query_batch':32,'overlap':True})
    rows=[]
    current_limit=limits['sample_instances']
    sampling=True
    def run_arm(arm,dataset,label,features=None):
        output=root/(arm['name']+'-'+label+'.json')
        command=[sys.executable,'research/recall/'+('benchmark.py' if label=='locomo' else 'lme_retrieval.py'),'--dataset',str(dataset),'--output',str(output),
            '--model-path',backend_paths[arm['backend']],'--model-id',args.model_id,'--counter','cl100k_base','--modes','literal','sparse','dense','hybrid',
            '--budgets','300','600','1200','--device',arm['device'],'--runtime-policy',arm['policy'],'--backend',arm['backend'],
            '--scorer',arm.get('scorer','numpy_reference'),'--batch-size',str(arm['batch']),'--query-batch-size',str(arm['query_batch']),'--threads',str(arm.get('threads',1))]
        if arm['policy']!='reference':command+=['--vector-storage','blob','--embedding-cache',str(root/'embedding-cache.sqlite')]
        if arm.get('profile_file'):command+=['--runtime-profile',arm['profile_file']]
        if arm.get('overlap'):command+=['--overlap']
        if label=='lme' and current_limit is not None:command+=['--limit',str(current_limit)]
        if limits['mode']=='smoke':
            i=command.index('--budgets');j=command.index('--device');command[i:j]=['--budgets','600']
        if features:command+=['--features-json',json.dumps(features)]
        reference_key=ReferenceArtifactKey(
            dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
            source_manifest=source['sha256'],
            embedding_profile={'backend':arm['backend'],'device':arm['device'],'model_id':args.model_id,
                'precision':'fp32','packages':versions()},
            reference_policy={'command':command[command.index('--counter'):],
                'limit':current_limit if label=='lme' else None},
            semantic_implementation=semantic_identity(),
            counter_identity={'name':'cl100k_base','packages':versions()}) if arm['policy']=='reference' else None
        reused=None
        reference_dir=getattr(args,'reference_dir',None)
        if reference_key and reference_dir and not sampling:
            candidate=Path(reference_dir)/output.name
            if candidate.exists():
                raw,reused=reuse(candidate,reference_key)
                with output.open('xb') as f:f.write(raw)
        start=time.perf_counter()
        # stdout has source scope IDs; retain locally rather than publish private paths.
        with (root/(arm['name']+'-'+label+'.log')).open('x') as log:
            result=subprocess.CompletedProcess(command,0) if reused else subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=max(.01,deadline-time.monotonic()))
        receipt={'arm':arm['name'],'dataset':label,'returncode':result.returncode,'wall_seconds':time.perf_counter()-start,
            'artifact':output.name,'verification_mode':limits['mode'],'lme_limit':current_limit if label=='lme' else None,'reused':False,'feature_experiment':features,'generation_calls':0}
        if result.returncode==0:
            receipt['sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
            artifact=json.loads(output.read_text())
            receipt['runtime']=artifact.get('runtime')
            receipt['index_build_seconds']=sum(b['index_seconds'] for b in artifact.get('builds',[]))
            receipt['document_embedding_seconds']=sum(b.get('embedding',{}).get('seconds',0) for b in artifact.get('builds',[]))
            receipt['quality']={k:v.get('main_categories_1_to_4',v.get('all_instances')) for k,v in artifact.get('summaries',{}).items()}
        if reused:receipt.update(reused)
        if reference_key and result.returncode==0:
            write_receipt(output.with_suffix('.reference.json'),{'key':asdict(reference_key),'key_id':reference_key.id,
                'artifact_sha256':receipt['sha256'],'returncode':0,'provenance':{'git_head':git,'mode':limits['mode'],
                'reused':bool(reused),'source':reused}})
        rows.append(receipt);write_receipt(root/(arm['name']+'-'+label+'-execution.json'),receipt)
    # The fixed LME pilot is retained separately and cannot pass as a full matrix.
    pilot={**arms[0],'name':'estimate-reference'}
    run_arm(pilot,args.lme_dataset,'lme')
    sample=rows.pop()
    if sample['returncode']:raise ValueError('estimator sample failed')
    extra_seconds=0
    if limits['mode']!='smoke':
        pilot_locomo=root/'pilot-locomo-input.json'
        write_receipt(pilot_locomo,locomo[:1])
        run_arm(pilot,pilot_locomo,'locomo')
        sample_locomo=rows.pop()
        if sample_locomo['returncode']:raise ValueError('LoCoMo estimator sample failed')
        extra_seconds=sample_locomo['wall_seconds']*len(locomo)*(len(arms)+(len(planned['features']) if args.retrieval_ab else 0))
    projection=estimate(sample['wall_seconds'],min(current_limit,len(lme)),
        len(lme) if limits['lme_limit'] is None else min(limits['lme_limit'],len(lme)),
        len(arms),max(0,deadline-time.monotonic()),extra_seconds=extra_seconds)
    projection['projected_locomo_seconds']=extra_seconds
    projection['expected_matrix_artifacts']=len(arms)*(1 if limits['mode']=='smoke' else 2)+(len(planned['features']) if args.retrieval_ab else 0)
    matrix_count=projection['expected_matrix_artifacts']
    dataset_count=1 if limits['mode']=='smoke' else 2
    reference_count=sum(arm['policy']=='reference' for arm in arms)*dataset_count
    projection['expected_top_level_artifacts']=len([p for p in root.iterdir() if p.is_file()])+2+matrix_count*3+reference_count+(matrix_count-reference_count)*(2 if limits['extended_diagnostics'] else 1)+(1 if len(arms)>1 else 0)
    projection['artifact_count_scope']='estimated top-level files; derived model subtrees and SQLite sidecars excluded'
    write_receipt(root/'runtime-estimate.json',projection)
    if projection['projected_total_seconds']>3600 and not getattr(args,'acknowledge_multi_hour_run',False):raise ValueError('multi-hour projection requires acknowledgement')
    if not projection['within_budget']:raise ValueError('projected campaign exceeds wall-time budget')
    current_limit=limits['lme_limit'];sampling=False
    for arm in arms:
        for dataset,label in ([(args.lme_dataset,'lme')] if limits['mode']=='smoke' else [(args.locomo_dataset,'locomo'),(args.lme_dataset,'lme')]):run_arm(arm,dataset,label)
    if args.retrieval_ab:
        for feature in planned['features']:
            # Algorithm changes get independent runs and never enter performance winner table.
            arm={**arms[0],'name':'feature-'+feature,'policy':'auto-throughput'}
            run_arm(arm,args.locomo_dataset,'locomo',{feature:True})
    from research.recall.hardware_parity import compare
    from research.evidence_io import read_json_bound
    from research.runtime.diagnostics import score_deltas
    comparisons=[]
    for row in rows:
        if row['returncode'] or row['arm']=='cpu-reference':continue
        source=root/('cpu-reference-'+row['dataset']+'.json');target=root/row['artifact']
        if not source.is_file():continue
        a,source_sha=read_json_bound(source);b,target_sha=read_json_bound(target);receipt=compare(a,b)
        receipt['source_artifacts']={'cpu':{'file':source.name,'sha256':source_sha},'candidate':{'file':target.name,'sha256':target_sha}}
        if limits['extended_diagnostics']:
            diagnostics=score_deltas(a,b);diagnostics['source_artifacts']=receipt['source_artifacts']
            write_receipt(root/(row['arm']+'-'+row['dataset']+'-score-deltas.json'),diagnostics)
        receipt['feature_experiment']=row['feature_experiment'];name=row['arm']+'-'+row['dataset']+'-parity.json';write_receipt(root/name,receipt)
        comparisons.append({'arm':row['arm'],'dataset':row['dataset'],'parity_artifact':name,'strict':receipt['strict_semantic_equivalent'],
            'aggregate':receipt['aggregate_semantic_metrics_equivalent'],'feature_experiment':row['feature_experiment']})
    missing_policies=[policy for policy in planned['policies'] if policy!='reference' and policy not in tunes]
    complete=not missing_policies and bool(rows) and all(r['returncode']==0 for r in rows)
    result={'schema':1,'status':'measured-needs-acceptance' if complete else 'incomplete-local-run',
        'calibrations':calibrations,'missing_required_winners':missing_policies,
        'verification_mode':limits['mode'],'full_dataset_acceptance':False,'lme_limit':limits['lme_limit'],
        'executions':rows,'comparisons':comparisons,'git_head':git,'generation_calls':0,'merge_authorized':False}
    write_receipt(root/'comparison.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('model-path','model-id','locomo-dataset','lme-dataset','output-dir'):p.add_argument('--'+name,required=True)
    p.add_argument('--plan-only',action='store_true');p.add_argument('--include-approximate',action='store_true');p.add_argument('--retrieval-ab',action='store_true')
    p.add_argument('--mode',choices=['smoke','acceptance','full-research'],default='acceptance')
    p.add_argument('--full-campaign',action='store_true')
    p.add_argument('--acknowledge-multi-hour-run',action='store_true')
    p.add_argument('--wall-seconds',type=float,default=None)
    p.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--reference-dir',help='Exact-key reference artifact directory')
    p.add_argument('--max-candidates',type=int,default=12);args=p.parse_args()
    if args.wall_seconds is None:args.wall_seconds=300 if args.mode=='smoke' else 3600
    campaign(args.mode,full_campaign=args.full_campaign,acknowledge=args.acknowledge_multi_hour_run,wall_seconds=args.wall_seconds,approximate=args.include_approximate,retrieval_ab=args.retrieval_ab)
    if not args.internal_worker and not args.plan_only:
        from research.runtime.bounds import bounded_process
        return bounded_process([sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--internal-worker'],args.wall_seconds,Path(args.output_dir))
    if Path(args.output_dir).exists():raise FileExistsError('verification output namespace exists')
    try:result=execute(args)
    except (Exception,KeyboardInterrupt) as exc:
        root=Path(args.output_dir)
        if root.is_dir() and not (root/'interrupted.json').exists():
            write_receipt(root/'interrupted.json',{'status':'interrupted-or-refused','error_type':type(exc).__name__})
        raise
    print(json.dumps(result,indent=2));return 1 if result.get('status')=='incomplete-local-run' else 0

if __name__=='__main__':sys.exit(main())
