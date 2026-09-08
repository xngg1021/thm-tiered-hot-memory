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
    root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=False)
    planned=plan(args.model_path,args.locomo_dataset,args.lme_dataset,root,args.model_id,include_approximate=args.include_approximate)
    write_receipt(root/'plan.json',planned)
    if args.plan_only:return planned
    locomo=load_dataset(args.locomo_dataset,LOCOMO_SHA);lme=load_dataset(args.lme_dataset,LME_SHA)
    source=manifest(args.model_path);hardware=probe();accelerators=backend_probe()
    git=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    dirty=subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,check=True).stdout
    if dirty.strip():raise ValueError('local verification requires a clean exact checkout')
    write_receipt(root/'hardware.json',{'hardware':hardware.identity(),'backend_probe':accelerators,'git_head':git,'implementation_sha256':implementation_identity(),
        'model_manifest_sha256':source['sha256'],'packages':versions(),'generation_calls':0,'observed_kernel_dispatch':None})
    write_receipt(root/'lme-census.json',census(lme,TokenCounter('cl100k_base')))
    backend_paths={'torch_fp32':str(Path(args.model_path).resolve())};backends=[('torch_fp32','cpu')]
    cuda=any(x.get('cuda_available') is True for x in accelerators)
    if cuda:backends.append(('torch_fp32','cuda'))
    for backend,cap in available().items():
        if backend=='torch_fp32' or not cap['installed'] or (backend.endswith('int8') and not args.include_approximate):continue
        try:receipt=prepare(args.model_path,root/'derived-models',backend)
        except Exception as exc:receipt={'status':'failed','error_type':type(exc).__name__,'backend':backend}
        write_receipt(root/(backend+'-preparation.json'),receipt)
        if receipt.get('status')=='prepared':backend_paths[backend]=str((root/'derived-models'/receipt['artifact_locator']).resolve());backends.append((backend,'cpu'))
    tunes={}
    for policy,workload in [('auto-safe','interactive'),('auto-throughput','bulk')]+([('approximate-performance','bulk')] if args.include_approximate else []):
        result=autotune(args.model_path,args.model_id,backends=backends,policy=policy,workload=workload,maximum=args.max_candidates,backend_paths=backend_paths)
        write_receipt(root/(policy+'-autotune.json'),result)
        if result.get('status')=='calibrated':tunes[policy]=result
    arms=list(planned['reference_arms'][:1])
    if cuda:arms.append(planned['reference_arms'][1])
    # Full matrices only for reference + measured winners, never every calibration point.
    for policy,tune in tunes.items():
        p=tune['runtime_profile'];arms.append({'name':policy,'backend':p['backend'],'device':p['device'],'policy':policy,
            'batch':p['document_batch_size'],'query_batch':p['query_batch_size'],'threads':p['threads'],'scorer':p['scorer'],'profile_file':str(root/(policy+'-autotune.json'))})
    if cuda:
        arms.append({'name':'cuda-batched-overlap','backend':'torch_fp32','device':'cuda','policy':'auto-throughput','batch':64,'query_batch':32,'overlap':True})
    rows=[]
    def run_arm(arm,dataset,label,features=None):
        output=root/(arm['name']+'-'+label+'.json')
        command=[sys.executable,'research/recall/'+('benchmark.py' if label=='locomo' else 'lme_retrieval.py'),'--dataset',str(dataset),'--output',str(output),
            '--model-path',backend_paths[arm['backend']],'--model-id',args.model_id,'--counter','cl100k_base','--modes','literal','sparse','dense','hybrid',
            '--budgets','300','600','1200','--device',arm['device'],'--runtime-policy',arm['policy'],'--backend',arm['backend'],
            '--scorer',arm.get('scorer','numpy_reference'),'--batch-size',str(arm['batch']),'--query-batch-size',str(arm['query_batch']),'--threads',str(arm.get('threads',1))]
        if arm['policy']!='reference':command+=['--vector-storage','blob','--embedding-cache',str(root/'embedding-cache.sqlite')]
        if arm.get('profile_file'):command+=['--runtime-profile',arm['profile_file']]
        if arm.get('overlap'):command+=['--overlap']
        if features:command+=['--features-json',json.dumps(features)]
        start=time.perf_counter()
        # stdout has source scope IDs; retain locally rather than publish private paths.
        with (root/(arm['name']+'-'+label+'.log')).open('x') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        receipt={'arm':arm['name'],'dataset':label,'returncode':result.returncode,'wall_seconds':time.perf_counter()-start,
            'artifact':output.name,'feature_experiment':features,'generation_calls':0}
        if result.returncode==0:
            receipt['sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
            artifact=json.loads(output.read_text())
            receipt['runtime']=artifact.get('runtime')
            receipt['index_build_seconds']=sum(b['index_seconds'] for b in artifact.get('builds',[]))
            receipt['document_embedding_seconds']=sum(b.get('embedding',{}).get('seconds',0) for b in artifact.get('builds',[]))
            receipt['quality']={k:v.get('main_categories_1_to_4',v.get('all_instances')) for k,v in artifact.get('summaries',{}).items()}
        rows.append(receipt);write_receipt(root/(arm['name']+'-'+label+'-execution.json'),receipt)
    for arm in arms:
        for dataset,label in [(args.locomo_dataset,'locomo'),(args.lme_dataset,'lme')]:run_arm(arm,dataset,label)
    if args.retrieval_ab:
        for feature in planned['features']:
            # Algorithm changes get independent runs and never enter performance winner table.
            arm={**arms[0],'name':'feature-'+feature,'policy':'auto-throughput'}
            run_arm(arm,args.locomo_dataset,'locomo',{feature:True})
    from research.recall.hardware_parity import compare
    comparisons=[]
    for row in rows:
        if row['returncode'] or row['arm']=='cpu-reference':continue
        source=root/('cpu-reference-'+row['dataset']+'.json');target=root/row['artifact']
        if not source.is_file():continue
        a=json.loads(source.read_text());b=json.loads(target.read_text());receipt=compare(a,b)
        receipt['source_artifacts']={k:{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in [('cpu',source),('candidate',target)]}
        receipt['feature_experiment']=row['feature_experiment'];name=row['arm']+'-'+row['dataset']+'-parity.json';write_receipt(root/name,receipt)
        comparisons.append({'arm':row['arm'],'dataset':row['dataset'],'parity_artifact':name,'strict':receipt['strict_semantic_equivalent'],
            'aggregate':receipt['aggregate_semantic_metrics_equivalent'],'feature_experiment':row['feature_experiment']})
    result={'schema':1,'status':'measured-needs-acceptance' if all(r['returncode']==0 for r in rows) else 'incomplete-local-run',
        'executions':rows,'comparisons':comparisons,'git_head':git,'generation_calls':0,'merge_authorized':False}
    write_receipt(root/'comparison.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('model-path','model-id','locomo-dataset','lme-dataset','output-dir'):p.add_argument('--'+name,required=True)
    p.add_argument('--plan-only',action='store_true');p.add_argument('--include-approximate',action='store_true');p.add_argument('--retrieval-ab',action='store_true')
    p.add_argument('--max-candidates',type=int,default=12);args=p.parse_args()
    result=execute(args);print(json.dumps(result,indent=2));return 1 if result.get('status')=='incomplete-local-run' else 0

if __name__=='__main__':sys.exit(main())
