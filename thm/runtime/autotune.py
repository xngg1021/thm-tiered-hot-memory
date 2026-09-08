"""Bounded subprocess calibration; semantic admission precedes performance choice."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from .hardware import probe
from .identity import manifest,EmbeddingProfile,validate_vectors,bounded_int
from .micro import DOCUMENTS,QUERIES,CORPUS_SHA
from .profiles import RuntimeProfile,fingerprint


def candidates(hardware,backends,policy='auto-safe',maximum=12):
    bounded_int(maximum,'candidate cap',32)
    if policy=='reference':
        if len(backends)!=1 or backends[0][0]!='torch_fp32':raise ValueError('reference requires one fixed Torch backend/device')
        return [{'backend':'torch_fp32','device':backends[0][1],'threads':1,'document_batch_size':64,'query_batch_size':1,'affinity':[],'scorer':'numpy_reference'}]
    available=hardware.process_available_cpus or 1
    # Never occupy every available core by default; an explicit local experiment may override.
    cap=min(8,max(1,available-1))
    physical=hardware.physical_cores_if_known or cap
    threads=sorted({1,min(cap,max(1,physical//2)),min(cap,physical)})
    out=[]
    for backend,device in backends:
        if backend.endswith('int8') and policy!='approximate-performance':continue
        for thread in threads:
            for doc_batch,query_batch in [(16,1),(32,4),(64,8),(128,32),(256,32)]:
                if hardware.ram_available is not None and hardware.ram_available<2*1024**3 and doc_batch>32:continue
                out.append({'backend':backend,'device':device,'threads':thread,'document_batch_size':doc_batch,'query_batch_size':query_batch,'affinity':[],'scorer':'numpy_reference'})
    # Round-robin backends, then spread batch/thread choices, avoiding Cartesian expansion.
    grouped={b:[x for x in out if (x['backend'],x['device'])==b] for b in backends}
    selected=[]
    # Ensure thread diversity early, then batch diversity; optional NUMA/P-core candidates
    # are restricted to the process's actual CPU mask and executed only in the child.
    for b,values in grouped.items():
        values.sort(key=lambda c:(c['document_batch_size']!=64,c['threads'],c['document_batch_size']))
    for i in range(max((len(v) for v in grouped.values()),default=0)):
        for values in grouped.values():
            if i<len(values) and len(selected)<maximum:selected.append(values[i])
    if selected and len(selected)>=3 and hardware.cpu_affinity:
        allowed=set(hardware.cpu_affinity)
        masks=[sorted(set(cpus)&allowed) for cpus in hardware.numa_nodes.values()]
        if hardware.core_types and all(str(v) in ('1','2') for v in hardware.core_types.values()):
            masks.append(sorted(int(k) for k,v in hardware.core_types.items() if str(v)=='2' and int(k) in allowed))
        for offset,mask in enumerate(m for m in masks if m and set(m)!=allowed):
            if offset>=min(2,len(selected)//3):break
            selected[-1-offset]={**selected[-1-offset],'affinity':mask,'threads':min(selected[-1-offset]['threads'],len(mask))}
    if len(selected)>=4:
        gpu=next((i for i in range(len(selected)-1,-1,-1) if selected[i]['device']=='cuda' and selected[i]['backend']=='torch_fp32'),None)
        if gpu is not None:selected[gpu]={**selected[gpu],'scorer':'torch_cuda'}
        cpu=next((i for i in range(len(selected)-1,-1,-1) if selected[i]['device']=='cpu' and selected[i]['backend']=='torch_fp32'),None)
        if cpu is not None:selected[cpu]={**selected[cpu],'scorer':'torch_cpu'}
    return selected


def retrieval_signature(measured):
    """Exercise real fusion and packing against identical fixed source documents."""
    from ..retrieval import Document,SearchIndex,TokenCounter
    lookup={**dict(zip(DOCUMENTS,measured['document_vectors'])),**dict(zip(QUERIES,measured['query_vectors']))}
    class Encoder:
        model_id='calibration-vector-snapshot'
        def __call__(self,texts):return [lookup[t[2:] if t.startswith(': ') else t] for t in texts]
    with tempfile.TemporaryDirectory() as temp:
        index=SearchIndex(Path(temp)/'calibration.sqlite',TokenCounter())
        try:
            index.replace_scope('calibration',[Document(str(i),'calibration','session',i,t) for i,t in enumerate(DOCUMENTS)])
            enc=Encoder();index.embed('calibration',enc,enc.model_id)
            out=index.search_many('calibration',QUERIES,mode='hybrid',budget=512,diagnostics=True,encoder=enc,model_id=enc.model_id,query_batch_size=measured.get('query_batch_size',1),scorer=measured.get('scorer','numpy_reference'))
            return [{'ranked_ids':r['ranked_ids'],'selected_ids':[x['id'] for x in r['selected']],'budget_used':r['budget_used'],
                     'scores':r['runtime_diagnostics']['scores']} for r in out]
        finally:index.close()


def gate(reference,candidate):
    if candidate.get('status')!='ok':return {'admitted':False,'reason':'candidate-failed'}
    if reference.get('corpus_sha256')!=CORPUS_SHA or candidate.get('corpus_sha256')!=CORPUS_SHA:raise ValueError('calibration corpus identity mismatch')
    if reference['identity']['source_manifest_sha256']!=candidate['identity']['source_manifest_sha256']:
        return {'admitted':False,'reason':'source-model-mismatch'}
    fields=EmbeddingProfile.__dataclass_fields__
    profile=EmbeddingProfile(**{k:v for k,v in candidate['identity'].items() if k in fields})
    for name,n in [('document_vectors',len(DOCUMENTS)),('query_vectors',len(QUERIES))]:validate_vectors(candidate[name],profile,n)
    if reference['identity']['dimension']!=profile.dimension:return {'admitted':False,'reason':'dimension-drift'}
    left=reference['retrieval_signature'] if 'retrieval_signature' in reference else retrieval_signature(reference)
    right=candidate['retrieval_signature'] if 'retrieval_signature' in candidate else retrieval_signature(candidate)
    score_tolerance=0.0  # Strict admission changes no ranking tie policy or numeric threshold.
    for signature in (left,right):
        if not isinstance(signature,list) or len(signature)!=len(QUERIES):return {'admitted':False,'reason':'invalid-signature-length'}
        for row in signature:
            scores=row.get('scores') if isinstance(row,dict) else None
            if not isinstance(scores,list) or len(scores)!=len(DOCUMENTS) or any(type(v) not in (int,float) or not math.isfinite(v) for v in scores):
                return {'admitted':False,'reason':'invalid-signature-scores'}
    score_delta=max(abs(x-y) for a,b in zip(left,right) for x,y in zip(a['scores'],b['scores']))
    strict=score_delta<=score_tolerance and all({k:v for k,v in a.items() if k!='scores'}=={k:v for k,v in b.items() if k!='scores'} for a,b in zip(left,right))
    delta=max(abs(x-y) for name in ('document_vectors','query_vectors') for a,b in zip(reference[name],candidate[name]) for x,y in zip(a,b))
    return {'admitted':strict,'strict_retrieval_parity':strict,'max_embedding_abs_diff':delta,'max_score_abs_diff':score_delta,'score_absolute_tolerance':score_tolerance,
            'reference_results':left,'candidate_results':right,'reason':'strict' if strict else 'retrieval-drift'}


def run_candidate(config,timeout=180):
    with tempfile.TemporaryDirectory() as temp:
        cfg=Path(temp)/'config.json';cfg.write_text(json.dumps(config));output=Path(temp)/'receipt.json'
        try:
            subprocess.run([sys.executable,'-m','thm.runtime.worker','measure',str(cfg),str(output)],timeout=timeout,check=True,capture_output=True)
            return json.loads(output.read_text())
        except (subprocess.SubprocessError,OSError,ValueError) as exc:return {'status':'failed','error_type':type(exc).__name__}


def autotune(model_path,model_id,*,backends=None,policy='auto-safe',workload='interactive',maximum=12,timeout=180,runner=run_candidate,backend_paths=None):
    metrics={'interactive':'single_query_p95_ms','bulk':'queries_per_second','background':'docs_per_second'}
    if workload not in metrics:raise ValueError('invalid workload')
    hardware=probe();source=manifest(model_path)['sha256']
    ref={'model_path':str(Path(model_path).resolve()),'model_id':model_id,'backend':'torch_fp32','device':'cpu','threads':1,'document_batch_size':64,'query_batch_size':1,'affinity':[]}
    reference=runner(ref,timeout)
    if reference.get('status')!='ok':return {'status':'failed','reason':'reference-unavailable','reference':reference,'generation_calls':0}
    trials=[]
    for config in candidates(hardware,backends or [('torch_fp32','cpu')],policy,maximum):
        result=runner({**ref,**config,'model_path':str((backend_paths or {}).get(config['backend'],model_path))},timeout);result['query_batch_size']=config['query_batch_size']
        try:
            if result.get('status')=='ok':
                ident=result['identity']
                if ident['backend']!=config['backend'] or ident['device']!=config['device']:raise ValueError('candidate execution identity mismatch')
                for field in ('single_query_p95_ms','queries_per_second','docs_per_second'):
                    value=result[field]
                    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('invalid candidate timing')
            semantic=gate(reference,result)
        except (ValueError,KeyError,TypeError) as exc:semantic={'admitted':False,'reason':'invalid-candidate','error_type':type(exc).__name__}
        accepted=result.get('status')=='ok' and (semantic.get('admitted') or (policy in ('auto-throughput','approximate-performance') and semantic.get('reason')=='retrieval-drift'))
        trials.append({'config':config,'result':result,'semantic_gate':semantic,'eligible':accepted})
    eligible=[t for t in trials if t['eligible']]
    if not eligible:return {'status':'failed','reason':'no-candidate-passed','trials':trials,'hardware':hardware.identity(),'generation_calls':0}
    metric=metrics[workload]
    winner=min(eligible,key=lambda t:t['result'][metric] if workload=='interactive' else -t['result'][metric])
    ident=winner['result']['identity'];config=winner['config']
    p=RuntimeProfile(ident['embedding_profile_id'],fingerprint(hardware,source,ident.get('derived_manifest_sha256'),ident['embedding_profile_id']),
        backend=config['backend'],device=config['device'],precision=ident['precision'],threads=config['threads'],
        document_batch_size=config['document_batch_size'],query_batch_size=1 if policy=='reference' else config['query_batch_size'],
        scorer=config['scorer'],policy=policy,workload=workload,affinity=tuple(config['affinity']),semantic_gate='strict' if winner['semantic_gate']['admitted'] else 'measured-drift')
    if manifest(model_path)['sha256']!=source:raise ValueError('model changed during calibration')
    return {'schema':1,'status':'calibrated','hardware':hardware.identity(),'source_manifest_sha256':source,'corpus_sha256':CORPUS_SHA,
            'runtime_profile':p.identity(),'selection_metric':metric,'trials':trials,'reference':reference,'generation_calls':0,
            'admission':'micro-corpus-only; real Protocol 2 acceptance pending','observed_kernel_dispatch':None}
