"""Explicit subprocess boundary for thread policy, conversion and calibration."""
import json
import os
from pathlib import Path
import sys
import time


def configure(config):
    # Child environment only. No changes propagate to the host or user settings.
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    threads=config.get('threads',1)
    from .identity import bounded_int
    bounded_int(threads,'threads',256)
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[name]=str(threads)
    affinity=config.get('affinity')
    if affinity:
        if not hasattr(os,'sched_setaffinity'):raise ValueError('affinity unavailable')
        available=os.sched_getaffinity(0)
        if not set(affinity)<=available:raise ValueError('affinity outside process allocation')
        os.sched_setaffinity(0,affinity)


def measure(config):
    configure(config)
    from .backends import create
    from .micro import DOCUMENTS,QUERIES,CORPUS_SHA
    from .identity import validate_vectors
    import statistics
    cpu_start=time.process_time();overall_start=time.perf_counter()
    start=time.perf_counter()
    encoder=create(config['model_path'],config['model_id'],backend=config['backend'],device=config['device'],
        threads=config['threads'],document_batch_size=config['document_batch_size'],query_batch_size=config['query_batch_size'],isolated=True)
    load=(time.perf_counter()-start)*1000
    try:
        encoder.encode_many(DOCUMENTS[:2]);warmup=1
        durations=[];docs=None
        for _ in range(3):
            start=time.perf_counter();docs=encoder.encode_many(DOCUMENTS);durations.append(time.perf_counter()-start)
        single=[]
        for query in QUERIES:
            start=time.perf_counter();encoder.encode_one(query);single.append((time.perf_counter()-start)*1000)
        start=time.perf_counter();query_vectors=[]
        for offset in range(0,len(QUERIES),config['query_batch_size']):query_vectors.extend(encoder.encode_many(QUERIES[offset:offset+config['query_batch_size']]))
        batch=time.perf_counter()-start
        validate_vectors(docs,encoder.profile,len(DOCUMENTS));validate_vectors(query_vectors,encoder.profile,len(QUERIES))
        memory=None
        try:
            import resource
            memory={'maxrss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'platform':sys.platform}
        except ImportError:pass
        result={'status':'ok','identity':encoder.identity(),'corpus_sha256':CORPUS_SHA,'warmup':warmup,'repeats':3,
            'sample_count':len(QUERIES),'model_load_ms':load,'docs_per_second':len(DOCUMENTS)/statistics.median(durations),
            'queries_per_second':len(QUERIES)/batch,'single_query_p50_ms':statistics.median(single),
            'single_query_p95_ms':sorted(single)[max(0,__import__('math').ceil(.95*len(single))-1)],
            'batch_total_ms':batch*1000,'memory':memory,'document_vectors':docs,'query_vectors':query_vectors,
            'generation_calls':0,'observed_kernel_dispatch':None,
            'cpu_process_seconds':time.process_time()-cpu_start,'cpu_utilization_percent':100*(time.process_time()-cpu_start)/(time.perf_counter()-overall_start),
            'gpu_utilization_percent':None,'vram_peak':None,'scorer':config.get('scorer','numpy_reference'),'query_batch_size':config['query_batch_size']}
        from .scorers import score
        _,scoring=score(docs,query_vectors,result['scorer'])
        result['scoring']=scoring;result['query_embedding_per_second']=result['queries_per_second']
        result['queries_per_second']=len(QUERIES)/(batch+scoring['dense_scoring']/1000)
        from .autotune import retrieval_signature
        result['retrieval_signature']=retrieval_signature(result)
        return result
    finally:encoder.close()


def serve(config):
    configure(config)
    from .backends import create
    from contextlib import redirect_stdout
    with redirect_stdout(sys.stderr):
        encoder=create(config['model_path'],config['model_id'],backend=config['backend'],device=config['device'],threads=config['threads'],
            document_batch_size=config['document_batch_size'],query_batch_size=config.get('query_batch_size',32),isolated=True)
    print(json.dumps({'identity':encoder.identity()}),flush=True)
    try:
        for line in sys.stdin:
            request=json.loads(line)
            if request.get('close'):break
            start=time.perf_counter();cpu=time.process_time()
            with redirect_stdout(sys.stderr):vectors=encoder.encode_many(request['texts'])
            print(json.dumps({'vectors':vectors,'worker_wall_ms':(time.perf_counter()-start)*1000,'worker_cpu_ms':(time.process_time()-cpu)*1000},allow_nan=False),flush=True)
    finally:encoder.close()


def main():
    config=json.loads(Path(sys.argv[2]).read_text())
    try:
        if sys.argv[1]=='serve':serve(config);return
        if sys.argv[1]=='measure':result=measure(config)
        elif sys.argv[1]=='prepare':
            configure(config)
            from .prepare import convert
            result=convert(config)
        else:raise ValueError('unknown worker action')
    except Exception as exc:
        # Exceptions may contain private filenames; public receipts retain only class.
        result={'status':'failed','error_type':type(exc).__name__}
    from .receipts import write_receipt
    write_receipt(sys.argv[3],result)

if __name__=='__main__':main()
