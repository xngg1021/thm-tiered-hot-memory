"""Explicit local-only, zero-LLM CPU query sweep over a fixed micro workload."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from thm.runtime.micro import DOCUMENTS,QUERIES,CORPUS_SHA
from thm.runtime.autotune import gate
from thm.runtime.receipts import write_receipt


def sweep(model_path,model_id,backend='torch_fp32',threads=1,encoder_factory=None):
    from thm.runtime.worker import configure
    from thm.runtime.backends import create
    from thm.runtime.scorers import score
    configure({'threads':threads})
    factory=encoder_factory or create
    encoder=factory(model_path,model_id,backend=backend,device='cpu',threads=threads,
        document_batch_size=64,query_batch_size=1,isolated=True)
    try:
        docs=encoder.encode_many(DOCUMENTS)
        reference={'status':'ok','identity':encoder.identity(),'corpus_sha256':CORPUS_SHA,
                   'document_vectors':docs,'query_vectors':[encoder.encode_one(q) for q in QUERIES],
                   'query_batch_size':1,'scorer':'numpy_reference'}
        queries=list(QUERIES)*4;rows=[]
        for batch in (1,4,8,32):
            encoder.encode_many(queries[:batch])
            latencies=[];construction=encoding=scoring=transfer=0.;cpu=time.process_time();start=time.perf_counter()
            for _ in range(3):
                for offset in range(0,len(queries),batch):
                    before=time.perf_counter();chunk=queries[offset:offset+batch];construction+=time.perf_counter()-before
                    before=time.perf_counter();vectors=encoder.encode_many(chunk);encoded=time.perf_counter()
                    _,timing=score(docs,vectors)
                    latencies.append((time.perf_counter()-before)*1000)
                    encoding+=encoded-before;scoring+=timing['dense_scoring'];transfer+=timing['transfer']
            wall=time.perf_counter()-start;cpu=time.process_time()-cpu
            q=[]
            for offset in range(0,len(QUERIES),batch):q.extend(encoder.encode_many(QUERIES[offset:offset+batch]))
            candidate={**reference,'query_vectors':q,'query_batch_size':batch}
            rows.append({'query_batch_size':batch,'queries':len(queries)*3,'queries_per_second':len(queries)*3/wall,
                'p50_ms':statistics.median(latencies),'p95_ms':sorted(latencies)[math.ceil(.95*len(latencies))-1],
                'latency_scope':'completed batch encoder+scorer; no arrival queue',
                'cpu_utilization_percent':100*cpu/wall,'batch_construction_ms':construction*1000,
                'wait_overhead_ms':0.,'wait_semantics':'offline prebuilt input; no scheduler wait',
                'query_encoding_ms':encoding*1000,'scorer_ms_including_transfer':scoring,
                'transfer_ms':transfer,'wall_seconds':wall,'semantic_parity':gate(reference,candidate)})
        return {'schema':1,'kind':'controlled-cpu-query-batch','backend':backend,'threads':threads,
            'embedding_profile':encoder.identity(),'workload_sha256':hashlib.sha256(json.dumps(queries).encode()).hexdigest(),
            'rows':rows,'observed_kernel_dispatch':None,'dispatch_status':'unknown',
            'generation_calls':0,'full_dataset_acceptance':False}
    finally:encoder.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path',required=True);p.add_argument('--model-id',required=True)
    p.add_argument('--backend',choices=['torch_fp32','onnxruntime_fp32','openvino_fp32'],default='torch_fp32')
    p.add_argument('--threads',type=int,default=1);p.add_argument('--wall-seconds',type=float,default=240)
    p.add_argument('--output-dir',required=True);p.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if not math.isfinite(args.wall_seconds) or not 0<args.wall_seconds<=600:raise ValueError('query sweep budget must be <=600 seconds')
    root=Path(args.output_dir)
    if not args.internal_worker:
        from research.runtime.bounds import bounded_process
        return bounded_process([sys.executable,'-m','research.runtime.query_batch',*sys.argv[1:],'--internal-worker'],args.wall_seconds,root)
    root.mkdir(parents=True,exist_ok=False)
    write_receipt(root/'query-batch.json',sweep(args.model_path,args.model_id,args.backend,args.threads))
    return 0

if __name__=='__main__':sys.exit(main())
