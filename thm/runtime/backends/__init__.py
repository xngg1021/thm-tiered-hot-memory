"""Lazy backend registry; all implementations require local model bytes."""
from typing import Protocol
from ..identity import bounded_int, manifest, EmbeddingProfile
from ..hardware import versions
import json
from pathlib import Path
import threading


class EncoderBackend(Protocol):
    model_id: str
    profile: EmbeddingProfile
    document_batch_size: int
    def identity(self) -> dict: ...
    def encode_one(self, text: str) -> list: ...
    def encode_many(self, texts: list[str]) -> list: ...
    def capabilities(self) -> dict: ...
    def close(self) -> None: ...

REGISTRY = {'torch_fp32':('torch','torch','fp32'), 'onnxruntime_fp32':('onnxruntime','onnx','fp32'),
            'openvino_fp32':('openvino','openvino','fp32'), 'onnxruntime_int8':('onnxruntime','onnx','int8'),
            'openvino_int8':('openvino','openvino','int8')}


def available():
    installed = versions()
    return {name: {'installed':bool(installed.get(package) or (package == 'onnxruntime' and installed.get('onnxruntime-gpu'))),
                   'precision':precision,'real_runtime_validation':'pending-real-local-runtime'}
            for name,(package,_,precision) in REGISTRY.items()}


class LocalEncoder:
    def __init__(self, path, model_id, *, backend='torch_fp32', device='cpu', threads=None,
                 document_batch_size=64, query_batch_size=32, isolated=False):
        if backend not in REGISTRY: raise ValueError('unsupported backend')
        self.document_batch_size = bounded_int(document_batch_size,'document batch',256)
        self.query_batch_size = bounded_int(query_batch_size,'query batch',256)
        if threads is not None: bounded_int(threads,'threads',256)
        if threads is not None and not isolated:
            raise ValueError('thread control requires an isolated worker; host policy is not mutated')
        if not isinstance(model_id,str) or not model_id.strip(): raise ValueError('model_id required')
        source = manifest(path)
        package, family, precision = REGISTRY[backend]
        installed = versions()
        backend_version = installed.get(package) or (installed.get('onnxruntime-gpu') if package=='onnxruntime' else None)
        if not backend_version: raise ValueError('optional backend is not installed: '+backend)
        source_sha, derived_sha, transform = source['sha256'], None, 'none'
        kwargs = {}
        if family != 'torch':
            receipt = json.loads((Path(path)/'thm-preparation.json').read_text())
            if receipt['backend'] != backend or receipt['derived_manifest_sha256'] != source['sha256']:
                raise ValueError('derived model identity mismatch; prepare locally again')
            source_sha, derived_sha, transform = receipt['source_manifest_sha256'], source['sha256'], receipt['transformation']
            kwargs = {'file_name':receipt['model_file'], 'export':False}
            if family == 'onnx':
                import onnxruntime as ort
                if device not in ('cpu','cuda') and not device.endswith('ExecutionProvider'):raise ValueError('explicit ONNX execution provider required')
                provider = 'CUDAExecutionProvider' if device == 'cuda' else device if device.endswith('ExecutionProvider') else 'CPUExecutionProvider'
                if provider not in ort.get_available_providers(): raise ValueError('requested execution provider unavailable')
                options = ort.SessionOptions()
                if threads is not None: options.intra_op_num_threads = threads
                kwargs.update(provider=provider,session_options=options)
            elif family == 'openvino':
                kwargs['device'] = device.upper()
                kwargs['ov_config'] = {'INFERENCE_PRECISION_HINT':'f32'}
                if threads is not None: kwargs['ov_config']['INFERENCE_NUM_THREADS'] = threads
        if family == 'torch':
            import torch
            if device == 'cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable')
            if device not in ('cpu','cuda','mps'): raise ValueError('unsupported torch device')
            if threads is not None: torch.set_num_threads(threads)
            kwargs['torch_dtype'] = 'float32'
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(str(path), backend=family, device=device if family=='torch' else 'cpu',
                    local_files_only=True, trust_remote_code=False, model_kwargs=kwargs)
        if family == 'torch': self.model.float()
        if manifest(path)['sha256'] != source['sha256']: raise ValueError('model bytes changed during loading')
        dimension = self.model.get_sentence_embedding_dimension()
        self.profile = EmbeddingProfile(source_sha,backend,backend_version,precision,int(dimension),device=device,
                                         transformation=transform,derived_manifest_sha256=derived_sha)
        self.model_id, self.device, self.threads = model_id, device, threads
        self.batch_size = self.document_batch_size
        self._lock = threading.RLock()

    def identity(self): return {**self.profile.identity(),'threads':self.threads,'thread_policy':'isolated-explicit' if self.threads else 'host-inherited'}
    def capabilities(self): return {'encode_many':True,'max_batch':256,'device':self.device,'observed_kernel_dispatch':None}
    def encode_many(self, texts):
        texts = list(texts)
        if any(not isinstance(t,str) for t in texts): raise ValueError('encoder inputs must be strings')
        if not texts: return []
        with self._lock:
            if self.model is None: raise ValueError('encoder closed')
            return self.model.encode(texts,batch_size=self.batch_size,normalize_embeddings=True,show_progress_bar=False).tolist()
    def encode_one(self,text): return self.encode_many([text])[0]
    def __call__(self,texts): return self.encode_many(texts)
    def close(self):
        with self._lock: self.model = None


def create(path,model_id,**kwargs): return LocalEncoder(path,model_id,**kwargs)
