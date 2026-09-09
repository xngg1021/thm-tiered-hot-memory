"""Bounded subprocess calibration; semantic admission precedes performance choice."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import struct
from .identity import digest
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
    return selected


def candidate_plan(hardware, backends, policy, maximum):
    """A cap selects a stable prefix; scorer variants never replace that prefix."""
    configs = candidates(hardware, backends, policy, 32)
    # Keep baseline independent of the accelerated trial cap.
    baseline = {'backend':'torch_fp32','device':'cpu','threads':1,
                'document_batch_size':64,'query_batch_size':1,'affinity':[],
                'scorer':'numpy_reference'}
    variants = []
    for config in configs:
        if config['backend'] == 'torch_fp32':
            variants.append({**config, 'scorer':'torch_cuda' if config['device']=='cuda' else 'torch_cpu'})
    families=len({(c['backend'],c['device']) for c in configs})
    representatives=variants[:sum(c['backend']=='torch_fp32' for c in configs[:families])]
    ordered=configs[:families]+representatives+configs[families:]+variants[len(representatives):]
    return [{'ordinal':0,'config':baseline,'capability_family':'reference',
             'execution_reason':'required-baseline','skip_reason':None}] + [
        {'ordinal':i+1,'config':config,
         'capability_family':config['backend']+'/'+config['device']+'/'+config['scorer'],
         'execution_reason':'diverse-bounded-trial' if i<maximum else None,
         'skip_reason':None if i<maximum else 'candidate-cap'}
        for i,config in enumerate(ordered)]


def numeric_guard(dimension):
    # FP32 unit roundoff u=2^-24. Two normalized length-d dot products
    # have absolute error bounded by 2*gamma_(2d+1), using Cauchy-Schwarz.
    # This is a sanity envelope, not a bound on transformer approximation error.
    u=2.0**-24; operations=2*dimension+1
    if operations*u>=1:raise ValueError('unsupported numeric operation envelope')
    return 2*operations*u/(1-operations*u)


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
                     'packed_evidence':[{'id':x['id'],'hash':x['hash'],'source':x['source'],'complete':x['complete']} for x in r['selected']],
                     'complete_evidence_ids':r['complete_evidence_ids'],
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
    score_tolerance=numeric_guard(profile.dimension)
    for signature in (left,right):
        if not isinstance(signature,list) or len(signature)!=len(QUERIES):return {'admitted':False,'reason':'invalid-signature-length'}
        for row in signature:
            if not isinstance(row,dict) or not {'ranked_ids','selected_ids','budget_used','packed_evidence','complete_evidence_ids'}<=row.keys():
                return {'admitted':False,'reason':'incomplete-structural-signature'}
            if any(not isinstance(row[k],list) for k in ('ranked_ids','selected_ids','packed_evidence','complete_evidence_ids')) or type(row['budget_used']) is not int or row['budget_used']<0:
                return {'admitted':False,'reason':'invalid-structural-signature'}
            scores=row.get('scores') if isinstance(row,dict) else None
            if not isinstance(scores,list) or len(scores)!=len(DOCUMENTS) or any(type(v) not in (int,float) or not math.isfinite(v) for v in scores):
                return {'admitted':False,'reason':'invalid-signature-scores'}
    score_delta=max(abs(x-y) for a,b in zip(left,right) for x,y in zip(a['scores'],b['scores']))
    structural=all({k:v for k,v in a.items() if k!='scores'}=={k:v for k,v in b.items() if k!='scores'} for a,b in zip(left,right))
    delta=max(abs(x-y) for name in ('document_vectors','query_vectors') for a,b in zip(reference[name],candidate[name]) for x,y in zip(a,b))
    numeric_ok=max(delta,score_delta)<=score_tolerance
    strict=structural and numeric_ok
    bitwise=all(struct.pack('>d',float(x))==struct.pack('>d',float(y))
        for name in ('document_vectors','query_vectors')
        for a,b in zip(reference[name],candidate[name]) for x,y in zip(a,b)) and all(
        struct.pack('>d',float(x))==struct.pack('>d',float(y))
        for a,b in zip(left,right) for x,y in zip(a['scores'],b['scores']))
    return {'admitted':strict,'strict_retrieval_parity':strict,
            'bitwise_parity':bitwise,'structural_retrieval_parity':structural,
            'semantic_admission':strict,
            'numeric_parity':{'bitwise_equal':bitwise,'max_embedding_abs_diff':delta,
                'max_score_abs_diff':score_delta,'numeric_tolerance':score_tolerance,
                'tolerance_basis':'fp32:2*gamma_(2d+1);normalized-dot-product-sanity-envelope',
                'within_numeric_guard':numeric_ok},
            'max_embedding_abs_diff':delta,'max_score_abs_diff':score_delta,
            'score_absolute_tolerance':score_tolerance,
            'reference_results':left,'candidate_results':right,
            'reason':'strict' if strict else 'retrieval-drift'}


def run_candidate(config,timeout=180):
    with tempfile.TemporaryDirectory() as temp:
        cfg=Path(temp)/'config.json';cfg.write_text(json.dumps(config));output=Path(temp)/'receipt.json'
        try:
            subprocess.run([sys.executable,'-m','thm.runtime.worker','measure',str(cfg),str(output)],timeout=timeout,check=True,capture_output=True)
            return json.loads(output.read_text())
        except (subprocess.SubprocessError,OSError,ValueError) as exc:return {'status':'failed','error_type':type(exc).__name__}


def autotune(model_path,model_id,*,backends=None,policy='auto-safe',workload='interactive',maximum=12,timeout=180,runner=run_candidate,backend_paths=None, reference_session=None, deadline=None, baseline_only=False, plan_callback=None):
    metrics={'interactive':'single_query_p95_ms','bulk':'queries_per_second','background':'docs_per_second'}
    if workload not in metrics:raise ValueError('invalid workload')
    if policy not in ('reference','auto-safe','auto-throughput','approximate-performance'):raise ValueError('invalid policy')
    bounded_int(maximum,'candidate cap',32)
    hardware=probe();source=manifest(model_path)['sha256']
    ref={'model_path':str(Path(model_path).resolve()),'model_id':model_id,'backend':'torch_fp32','device':'cpu','threads':1,'document_batch_size':64,'query_batch_size':1,'affinity':[]}
    plan=candidate_plan(hardware,backends or [('torch_fp32','cpu')],policy,maximum)
    if baseline_only:
        for entry in plan[1:]:entry.update(skip_reason='baseline-only-budget',execution_reason=None)
    if plan_callback:plan_callback(plan)
    key=digest({'reference':{k:v for k,v in ref.items() if k!='model_path'},
                'fingerprint':fingerprint(hardware,source),'corpus':CORPUS_SHA})
    def remaining():
        value=timeout if deadline is None else min(timeout,deadline-time.monotonic())
        if value<=0:raise TimeoutError('calibration deadline')
        return value
    remaining()
    cached=reference_session.get(key) if reference_session is not None else None
    if cached is not None:
        if digest(cached['result'])!=cached['sha256']:raise ValueError('reference session receipt changed')
        reference=json.loads(json.dumps(cached['result']))
    else:reference=runner(ref,remaining())
    provenance={'reused':cached is not None,'source_receipt_sha256':digest(reference),
                'identity_key':key,'reuse_class':'within-run-reference-measurement'}
    if reference_session is not None and reference.get('status')=='ok':
        reference_session[key]={'result':json.loads(json.dumps(reference)),'sha256':digest(reference)}
    if reference.get('status')!='ok':return {'status':'failed','reason':'reference-unavailable','reference':reference,'generation_calls':0}
    try:
        if reference['identity']['source_manifest_sha256']!=source:raise ValueError('reference source identity')
        if any(reference['identity'].get(k)!=v for k,v in {'backend':'torch_fp32','device':'cpu','precision':'fp32'}.items()):
            raise ValueError('reference execution identity')
        reference_gate=gate(reference,reference)
        if not reference_gate['admitted']:raise ValueError('reference self-validation')
        for field in metrics.values():
            if not math.isfinite(reference[field]) or reference[field]<=0:raise ValueError('reference timing')
    except (ValueError,KeyError,TypeError):
        return {'status':'failed','reason':'reference-invalid','reference':reference,'candidate_plan':plan,'generation_calls':0}
    trials=[]
    for entry in plan[1:]:
        if entry['skip_reason']:continue
        if deadline is not None and deadline-time.monotonic()<timeout:
            entry.update(skip_reason='remaining-budget',execution_reason=None);continue
        config=entry['config']
        result=runner({**ref,**config,'model_path':str((backend_paths or {}).get(config['backend'],model_path))},remaining());result['query_batch_size']=config['query_batch_size']
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
        entry['admission_reason']=semantic['reason']
        trials.append({'ordinal':entry['ordinal'],'config':config,'result':result,'semantic_gate':semantic,'eligible':accepted})
    eligible=[t for t in trials if t['eligible']]
    metric=metrics[workload]
    baseline={'config':plan[0]['config'],'result':reference,'semantic_gate':reference_gate}
    if policy in ('auto-safe','reference'):
        eligible=[t for t in eligible if (t['result'][metric]<reference[metric] if workload=='interactive' else t['result'][metric]>reference[metric])]
    fallback=not eligible
    winner=min(eligible,key=lambda t:t['result'][metric] if workload=='interactive' else -t['result'][metric]) if eligible else baseline
    ident=winner['result']['identity'];config=winner['config']
    p=RuntimeProfile(ident['embedding_profile_id'],fingerprint(hardware,source,ident.get('derived_manifest_sha256'),ident['embedding_profile_id']),
        backend=config['backend'],device=config['device'],precision=ident['precision'],threads=config['threads'],
        document_batch_size=config['document_batch_size'],query_batch_size=1 if policy=='reference' else config['query_batch_size'],
        scorer=config['scorer'],policy=policy,workload=workload,affinity=tuple(config['affinity']),semantic_gate='strict' if winner['semantic_gate']['admitted'] else 'measured-drift')
    if manifest(model_path)['sha256']!=source:raise ValueError('model changed during calibration')
    return {'schema':1,'status':'calibrated','hardware':hardware.identity(),'source_manifest_sha256':source,'corpus_sha256':CORPUS_SHA,
            'runtime_profile':p.identity(),'selection_metric':metric,
            'selection':'reference-fallback' if fallback else 'calibrated-candidate',
            'reason':'no-faster-safe-candidate' if fallback else 'measured-winner',
            'accelerated_candidate_found':not fallback,
            'optimized_auto_safe':policy=='auto-safe' and not fallback,
            'semantic_gate':'strict/reference' if fallback else p.semantic_gate,
            'strict_semantic_parity':winner['semantic_gate']['admitted'],
            'aggregate_quality_parity':None,'candidate_plan':plan,'reference_reuse':provenance,'trials':trials,'reference':reference,'generation_calls':0,
            'admission':'micro-corpus-only; real Protocol 2 acceptance pending','observed_kernel_dispatch':None}
