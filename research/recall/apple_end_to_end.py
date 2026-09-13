"""Local CPU/MPS dense+hybrid comparison through Evaluation Fabric; bounded by default."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from thm.retrieval import SentenceEncoder
from thm.evaluation.adapters import ADAPTERS
from thm.evaluation.fixtures import FIXTURES
from thm.evaluation.runner import run
from thm.systems.artifacts import model_snapshot
from thm.systems.contracts import atomic_json


def compare(model_path,model_id,output,*,sources=None,full_research=False,batch_size=64,encoder_factory=SentenceEncoder):
    root=Path(output); root.mkdir(parents=True,exist_ok=False)
    receipts=[]
    with model_snapshot(model_path) as (snapshot,manifest):
        for device in ('cpu','mps'):
            encoder=encoder_factory(snapshot,model_id,device=device,batch_size=batch_size)
            try:
                for benchmark in ('locomo','longmemeval-s'):
                    for mode in ('dense','hybrid'):
                        source=(sources or FIXTURES)[benchmark]
                        start=time.perf_counter()
                        receipt=run(ADAPTERS[benchmark],source,root/f'{device}-{benchmark}-{mode}',
                            mode='full-research' if full_research else 'acceptance',full_research=full_research,
                            provenance='external-dataset' if sources else 'deterministic-fixture',retrieval_mode=mode,
                            encoder=encoder,model_id=model_id,ceiling=True)
                        receipts.append({'device':device,'benchmark':benchmark,'mode':mode,
                            'end_to_end_seconds':time.perf_counter()-start,'receipt':receipt})
            finally:
                encoder.close()
    comparisons=[]
    for benchmark in ('locomo','longmemeval-s'):
        for mode in ('dense','hybrid'):
            a,b=[r for r in receipts if r['benchmark']==benchmark and r['mode']==mode]
            cpu=a['receipt']['layers']['memory-dataplane']['rows']; mps=b['receipt']['layers']['memory-dataplane']['rows']
            parity=[r['selected_ids'] for r in cpu]==[r['selected_ids'] for r in mps]
            comparisons.append({'benchmark':benchmark,'mode':mode,'selected_evidence_order_equal':parity,
                'end_to_end_speedup':a['end_to_end_seconds']/b['end_to_end_seconds'],
                'embedding_speedup':None,'retrieval_speedup':None,
                'component_speedup_reason':'separate component timing required; not inferred from total',
                'hardware_acceptance':False})
    result={'schema':'thm-apple-end-to-end/1','model_manifest_sha':manifest['sha256'],
        'model_id':model_id,'batch_size':batch_size,'runs':receipts,'comparisons':comparisons,
        'generation_calls':0,'judge_calls':0,'automatic_admission':False}
    atomic_json(root/'comparison.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path',required=True);p.add_argument('--model-id',required=True)
    p.add_argument('--output',required=True);p.add_argument('--batch-size',type=int,default=64)
    p.add_argument('--full-research',action='store_true');p.add_argument('--sources-json')
    args=p.parse_args()
    if args.full_research and not args.sources_json:
        p.error('full research requires explicit local datasets')
    sources=None
    if args.sources_json:
        from thm._bounded_files import bounded_file_bytes
        sources=json.loads(bounded_file_bytes(args.sources_json,1024**3 if args.full_research else 4_000_000))
    import torch
    if not torch.backends.mps.is_available():
        print(json.dumps({'status':'unavailable','reason':'MPS unavailable on this host','hardware_acceptance':False}))
        return 2
    compare(args.model_path,args.model_id,args.output,sources=sources,full_research=args.full_research,batch_size=args.batch_size)
    return 0


if __name__=='__main__':raise SystemExit(main())
