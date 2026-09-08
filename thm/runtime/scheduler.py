"""Explicit per-request profile routing. No silent cross-profile vector fallback."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from .profiles import POLICIES,WORKLOADS


class RuntimeScheduler:
    def __init__(self,index,profiles,encoders,*,policy='auto-safe',fallback_to_sparse=False,max_pending=32,verify_fresh=True):
        if policy not in POLICIES:raise ValueError('invalid policy')
        from .identity import bounded_int
        bounded_int(max_pending,'queue bound',256)
        self.index=index;self.profiles={p.id:p for p in profiles};self.encoders=encoders;self.policy=policy
        if not self.profiles:raise ValueError('at least one explicit profile required')
        for p in profiles:
            encoder=encoders.get(p.embedding_profile_id)
            if encoder is None or encoder.profile.id!=p.embedding_profile_id:raise ValueError('missing compatible profile encoder')
            if (p.backend,p.device,p.precision)!=(encoder.profile.backend,encoder.profile.device,encoder.profile.precision):raise ValueError('runtime backend identity mismatch')
            if verify_fresh:
                from .profiles import fingerprint
                from .hardware import probe
                p.require_fresh(fingerprint(probe(),encoder.profile.source_manifest_sha256,encoder.profile.derived_manifest_sha256,encoder.profile.id))
            if policy in ('reference','auto-safe') and (p.precision!='fp32' or p.semantic_gate not in ('strict','reference')):raise ValueError('semantic gate not satisfied')
        self.pinned=next(iter(self.profiles));self.fallback=fallback_to_sparse
        self.lock=threading.Lock();self.pending={k:0 for k in self.profiles};self.warm=set();self.closed=False
        self.slots=threading.BoundedSemaphore(max_pending);self.pool=ThreadPoolExecutor(max_workers=min(4,len(profiles)),thread_name_prefix='thm-runtime')

    def choose(self,workload,*,cpu_load=None,gpu_queue=None,vram_available=None):
        if workload not in WORKLOADS:raise ValueError('invalid workload')
        if self.policy!='auto-throughput':return self.pinned
        candidates=list(self.profiles)
        if vram_available is not None and vram_available<256*1024**2:
            cpu=[k for k in candidates if self.profiles[k].device=='cpu']
            if cpu:candidates=cpu
        return min(candidates,key=lambda k:(self.pending[k]+(gpu_queue or 0 if self.profiles[k].device!='cpu' else cpu_load or 0),k not in self.warm,self.profiles[k].workload!=workload,k))

    def search(self,scope,query,*,workload='interactive',requested_profile=None,load=None,**kwargs):
        with self.lock:
            if self.closed:raise RuntimeError('scheduler closed')
            key=requested_profile or self.choose(workload,**(load or {}))
            if key not in self.profiles or (self.policy!='auto-throughput' and key!=self.pinned):raise ValueError('session profile pinned')
            self.pending[key]+=1
        p=self.profiles[key];encoder=self.encoders[p.embedding_profile_id];start=time.perf_counter()
        receipt={'requested_profile':key,'actual_profile':key,'embedding_profile_id':p.embedding_profile_id,'semantic_policy':self.policy,
            'workload':workload,'fallback_mode':None,'reason':'session-pinned' if self.policy!='auto-throughput' else 'bounded-queue-routing',
            'device':p.device,'precision':p.precision,'threads':p.threads,'document_batch_size':p.document_batch_size,'query_batch_size':p.query_batch_size,
            'scorer':p.scorer,'warm':key in self.warm,'observed_kernel_dispatch':None}
        try:
            if 'encoder' in kwargs or 'model_id' in kwargs:raise ValueError('scheduler owns encoder identity')
            call=self.index.search_overlap if p.overlap and self.policy!='reference' else self.index.search
            if isinstance(query,list):
                result=self.index.search_many(scope,query,query_batch_size=p.query_batch_size,scorer=p.scorer,encoder=encoder,model_id=encoder.model_id,**kwargs)
            else:result=call(scope,query,encoder=encoder,model_id=encoder.model_id,**kwargs)
            with self.lock:self.warm.add(key)
        except Exception as exc:
            if not self.fallback:raise
            clean={k:v for k,v in kwargs.items() if k not in ('encoder','model_id','mode')}
            result=self.index.search_many(scope,query,mode='sparse',**clean) if isinstance(query,list) else self.index.search(scope,query,mode='sparse',**clean)
            receipt.update(actual_profile=None,embedding_profile_id=None,fallback_mode='fallback-to-sparse',reason=type(exc).__name__)
        finally:
            with self.lock:self.pending[key]-=1
        receipt['total_latency_ms']=(time.perf_counter()-start)*1000
        for item in result if isinstance(result,list) else [result]:item['runtime_receipt']=dict(receipt)
        return result

    def search_many(self,scope,queries,**kwargs):
        return self.search(scope,list(queries),**kwargs)

    def submit(self,*args,**kwargs):
        if not self.slots.acquire(blocking=False):raise RuntimeError('scheduler queue full')
        try:future=self.pool.submit(self.search,*args,**kwargs)
        except Exception:self.slots.release();raise
        future.add_done_callback(lambda f:self.slots.release());return future

    def close(self,*,cancel_pending=True):
        with self.lock:self.closed=True
        self.pool.shutdown(wait=True,cancel_futures=cancel_pending)
        for encoder in self.encoders.values():encoder.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
