"""Deterministic test doubles, never registered as production/performance backends."""
import hashlib
import math
from .identity import EmbeddingProfile


class FakeEncoder:
    def __init__(self,kind='fast',*,device='cpu',salt='',document_batch_size=64):
        self.kind=kind;self.salt=salt;self.model_id='test-only';self.document_batch_size=document_batch_size
        self.query_batch_size=1;self.threads=1;self.affinity=[];self.batch_size=document_batch_size;self.device=device;self.calls=[];self.closed=False
        self.profile=EmbeddingProfile(hashlib.sha256(b'test fixture').hexdigest(),'test-only','1','fp32',8,device=device,transformation=salt or 'none')
    def encode_many(self,texts):
        if self.closed:raise RuntimeError('closed')
        if self.kind in ('fails','unavailable'):raise RuntimeError('test backend unavailable')
        if self.kind=='out-of-memory':raise MemoryError('test OOM')
        self.calls.append(list(texts));out=[]
        for text in texts:
            raw=hashlib.sha256((self.salt+text).encode()).digest();v=[(x-127.5)/127.5 for x in raw[:8]]
            if self.kind=='semantic-drift':v.reverse()
            norm=math.sqrt(sum(x*x for x in v));out.append([x/norm for x in v])
        return out
    def __call__(self,texts):return self.encode_many(texts)
    def encode_one(self,text):return self.encode_many([text])[0]
    def identity(self):return self.profile.identity()
    def runtime_identity(self):return {'threads':self.threads,'document_batch_size':self.document_batch_size,'query_batch_size':self.query_batch_size,'affinity':self.affinity}
    def capabilities(self):return {'test_only':True,'nominal_latency':10 if self.kind=='slow' else 1,'warm':bool(self.calls)}
    def close(self):self.closed=True
