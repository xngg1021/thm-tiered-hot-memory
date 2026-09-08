"""Shared runner integration; research keeps per-conversation/instance SQLite IDF."""
from dataclasses import dataclass
import time
from .identity import bounded_int
from .profiles import POLICIES
from ..features import RetrievalFeatures


@dataclass(frozen=True)
class ExecutionConfig:
    policy: str = 'reference'
    backend: str = 'torch_fp32'
    device: str = 'cpu'
    threads: int = 1
    document_batch_size: int = 64
    query_batch_size: int = 1
    vector_storage: str = 'json'
    scorer: str = 'numpy_reference'
    overlap: bool = False
    features: RetrievalFeatures = RetrievalFeatures()
    runtime_profile_file: str | None = None

    def __post_init__(self):
        if self.policy not in POLICIES:raise ValueError('invalid runtime policy')
        for v,n in ((self.threads,'threads'),(self.document_batch_size,'document batch'),(self.query_batch_size,'query batch')):bounded_int(v,n,256)
        if type(self.overlap) is not bool:raise ValueError('overlap must be boolean')
        if self.policy=='reference' and (self.backend!='torch_fp32' or self.query_batch_size!=1 or self.overlap or self.features!=RetrievalFeatures() or self.vector_storage!='json' or self.scorer!='numpy_reference'):
            raise ValueError('reference requires fixed Torch FP32 sequential semantics and default features')
        if self.backend.endswith('int8') and self.policy!='approximate-performance':raise ValueError('INT8 requires approximate policy')


class Execution:
    def __init__(self,config,model_path,model_id,cache_path=None):
        self.config=config;self.encoder=None;self.cache=None;self.query_embedding_precompute_ms=0;self.precomputed={}
        self.started=time.perf_counter()
        if cache_path and config.policy=='reference':raise ValueError('reference disables embedding cache')
        if model_path:
            from .isolated import IsolatedEncoder
            self.encoder=IsolatedEncoder({'model_path':str(model_path),'model_id':model_id,'backend':config.backend,'device':config.device,
                'threads':config.threads,'document_batch_size':config.document_batch_size,'query_batch_size':config.query_batch_size})
            if config.runtime_profile_file:
                import json
                from pathlib import Path
                from .profiles import load_profile,fingerprint
                from .hardware import probe
                p=load_profile(config.runtime_profile_file);identity=self.encoder.profile
                p.require_fresh(fingerprint(probe(),identity.source_manifest_sha256,identity.derived_manifest_sha256,identity.id))
                if p.embedding_profile_id!=identity.id:raise ValueError('runtime/document profile mismatch')
            if cache_path:
                from .storage import EmbeddingCache
                self.cache=EmbeddingCache(cache_path)
        self.initialization_ms=(time.perf_counter()-self.started)*1000
    def embed(self,index,scope):
        return index.embed(scope,self.encoder,self.encoder.model_id,document_batch_size=self.config.document_batch_size,
                           vector_storage=self.config.vector_storage,embedding_cache=self.cache)
    def preencode(self,queries):
        if self.encoder is None or self.config.policy=='reference':return
        start=time.perf_counter();unique=list(dict.fromkeys(queries));batch=self.config.query_batch_size
        for i in range(0,len(unique),batch):
            chunk=unique[i:i+batch];values=self.encoder.encode_many(chunk)
            self.precomputed.update(zip(chunk,values))
        self.query_embedding_precompute_ms+=(time.perf_counter()-start)*1000
    def search_many(self,index,scope,queries,**kwargs):
        cfg=self.config;kwargs.update(encoder=self.encoder,model_id=self.encoder.model_id if self.encoder else None,features=cfg.features,diagnostics=cfg.policy!='reference')
        if self.precomputed and self.encoder:
            for query in queries:
                if query in self.precomputed:index._cache[(self.encoder.profile.id,query)]=self.precomputed[query]
        if cfg.policy!='reference' and cfg.query_batch_size>1 and len(queries)>1:
            return index.search_many(scope,queries,query_batch_size=cfg.query_batch_size,scorer=cfg.scorer,**kwargs)
        call=index.search_overlap if cfg.overlap else index.search
        return [call(scope,q,**kwargs) for q in queries]
    def receipt(self):
        from dataclasses import asdict
        config=asdict(self.config);config.pop('runtime_profile_file',None)
        return {'config':config,'embedding_profile':self.encoder.identity() if self.encoder else None,'initialization_ms':self.initialization_ms,
            'query_preembedding_ms':self.query_embedding_precompute_ms,'wall_seconds':time.perf_counter()-self.started,
            'cache':{'hits':self.cache.hits,'misses':self.cache.misses} if self.cache else None,'generation_calls':0,'observed_kernel_dispatch':None}
    def close(self):
        if self.cache:self.cache.close()
        if self.encoder:self.encoder.close()


def add_arguments(parser):
    parser.add_argument('--runtime-policy',choices=POLICIES,default='reference')
    parser.add_argument('--backend',default='torch_fp32');parser.add_argument('--query-batch-size',type=int,default=1)
    parser.add_argument('--vector-storage',choices=['json','blob'],default='json');parser.add_argument('--embedding-cache')
    parser.add_argument('--scorer',choices=['numpy_reference','torch_cpu','torch_cuda'],default='numpy_reference')
    parser.add_argument('--overlap',action='store_true');parser.add_argument('--features-json',default='{}');parser.add_argument('--runtime-profile')


def config_from_args(args):
    import json
    return ExecutionConfig(args.runtime_policy,args.backend,args.device,getattr(args,'threads',1),args.batch_size,args.query_batch_size,
        args.vector_storage,args.scorer,args.overlap,RetrievalFeatures.parse(json.loads(args.features_json)),args.runtime_profile)
