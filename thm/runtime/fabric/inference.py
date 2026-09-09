"""Local vendor inference adapters. No provider may download or choose a model."""
from dataclasses import dataclass
import importlib
from pathlib import Path
import time
from .contracts import identity
from .registry import ProviderUnavailable


@dataclass(frozen=True)
class ModelArtifact:
    locator: str
    source_sha: str
    provider: str
    provider_version: str
    precision: str
    options_sha: str

    def public(self):
        return {k: v for k, v in self.__dict__.items() if k != 'locator'}


def model_digest(path):
    import hashlib
    path = Path(path)
    if path.is_symlink() or not path.exists():
        raise ValueError('existing local model required')
    if path.is_file():
        sha = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024*1024), b''):
                sha.update(block)
        return sha.hexdigest()
    from ..identity import manifest
    return manifest(path)['sha256']


class LocalInferenceBase:
    module = None

    def __init__(self, spec):
        self.spec = spec; self.options = dict(spec.options); self.model = None
        self.last = {}; self.artifact = None

    def _module(self):
        return importlib.import_module(self.options.get('module', self.module))

    def probe(self):
        module = self._module()
        return {'provider': self.spec.provider_id, 'availability': 'dependency-present',
                'version': str(getattr(module, '__version__', 'unknown')), 'devices': [],
                'observed_kernel_dispatch': None}

    def prepare(self, source, **options):
        module = self._module()
        self.artifact = ModelArtifact(str(Path(source).resolve()), model_digest(source), self.spec.provider_id,
                                      str(getattr(module, '__version__', 'unknown')),
                                      options.get('precision', 'fp32'), identity(options))
        if self.artifact.precision not in self.spec.supported_precisions:
            raise ValueError('unsupported model precision')
        return self.artifact

    def _verify(self, artifact):
        if artifact.provider != self.spec.provider_id or model_digest(artifact.locator) != artifact.source_sha:
            raise ValueError('model artifact identity changed')
        version = str(getattr(self._module(), '__version__', 'unknown'))
        if version != artifact.provider_version:
            raise ValueError('provider version changed')

    def compile(self, artifact, **options):
        self.load(artifact, **options)
        return {'artifact': artifact.public(), 'compiled': False, 'reason': 'runtime-managed-load',
                'observed_kernel_dispatch': None}

    def encode_one(self, inputs):
        return self.encode_many(inputs)

    def capabilities(self):
        return {**self.spec.public(), 'input_contract': 'model-specific-pretokenized-tensors',
                'network': False, 'generative_calls': 0}

    def telemetry(self):
        return {**self.last, 'provider': self.spec.provider_id,
                'artifact': self.artifact.public() if self.artifact else None,
                'observed_kernel_dispatch': None, 'energy': None, 'hardware_validation': 'unvalidated'}

    def _run(self, function, inputs):
        if self.model is None:
            raise RuntimeError('provider model not loaded')
        start = time.perf_counter(); cpu = time.process_time()
        result = function(inputs)
        self.last = {'encode_ms': (time.perf_counter()-start)*1000,
                     'cpu_seconds': time.process_time()-cpu, 'requested_threads': None,
                     'provider_threads': None, 'semantic_status': 'unvalidated'}
        return result

    def close(self):
        self.model = None


class TorchInference(LocalInferenceBase):
    module = 'torch'

    def _module(self):
        if self.options.get('extension'):
            importlib.import_module(self.options['extension'])
        return importlib.import_module('torch')

    def probe(self):
        torch = self._module(); device = self.options.get('device', 'cpu')
        api = getattr(torch.backends, 'mps') if device == 'mps' else getattr(torch, device, None)
        available = device == 'cpu' or bool(api and api.is_available())
        if self.options.get('require_hip') and not getattr(torch.version, 'hip', None):
            available = False
        if self.options.get('require_cuda') and getattr(torch.version, 'hip', None):
            available = False
        return {'provider': self.spec.provider_id, 'availability': 'available' if available else 'device-unavailable',
                'devices': [device] if available else [], 'version': torch.__version__,
                'driver_runtime': getattr(torch.version, 'hip', None) or getattr(torch.version, 'cuda', None),
                'observed_kernel_dispatch': None}

    def load(self, artifact, **options):
        self._verify(artifact); start = time.perf_counter()
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(artifact.locator, device=self.options.get('device', 'cpu'),
                                         local_files_only=True, trust_remote_code=False)
        if artifact.precision == 'fp32':
            self.model.float()
        self.artifact = artifact
        self.last = {'startup_ms': (time.perf_counter()-start)*1000}
        self._verify(artifact)
        return self

    def encode_one(self, text):
        return self.encode_many([text])[0]

    def encode_many(self, texts):
        return self._run(lambda x: self.model.encode(list(x), batch_size=min(32, max(1, len(x))),
                                                    normalize_embeddings=True, show_progress_bar=False).tolist(), texts)

    def capabilities(self):
        return {**super().capabilities(), 'input_contract': 'local-SentenceTransformer-texts'}


class OrtInference(LocalInferenceBase):
    module = 'onnxruntime'

    def probe(self):
        ort = self._module(); ep = self.options['ep']
        providers = ort.get_available_providers()
        return {'provider': self.spec.provider_id, 'availability': 'available' if ep in providers else 'ep-unavailable',
                'devices': [ep] if ep in providers else [], 'version': ort.__version__, 'observed_kernel_dispatch': None}

    def load(self, artifact, **options):
        self._verify(artifact); ort = self._module(); ep = self.options['ep']
        # Optional standalone EP ABI library is explicitly local; no download lifecycle.
        library = options.get('ep_library')
        if library:
            ort.register_execution_provider_library(ep, str(Path(library).resolve()))
        if ep not in ort.get_available_providers():
            raise ProviderUnavailable('requested execution provider unavailable')
        session_options = ort.SessionOptions()
        session_options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        if options.get('threads'):
            session_options.intra_op_num_threads = int(options['threads'])
        ep_options = dict(options.get('provider_options', {}))
        if 'backend_path' in self.options and 'backend_path' not in ep_options:
            ep_options['backend_path'] = self.options['backend_path']
        start = time.perf_counter()
        self.model = ort.InferenceSession(artifact.locator, sess_options=session_options, providers=[(ep, ep_options)])
        if ep not in self.model.get_providers():
            self.close(); raise ProviderUnavailable('requested EP did not load')
        self.artifact = artifact
        self.last = {'startup_ms': (time.perf_counter()-start)*1000, 'requested_ep': ep,
                     'registered_eps': self.model.get_providers(), 'observed_operator_placement': None}
        return self

    def encode_many(self, inputs):
        if not isinstance(inputs, dict):
            raise ValueError('ONNX input-name tensor mapping required')
        return self._run(lambda x: self.model.run(None, x), inputs)


class OpenVINOInference(LocalInferenceBase):
    module = 'openvino'

    def probe(self):
        ov = self._module(); devices = ov.Core().available_devices
        return {'provider': self.spec.provider_id, 'availability': 'available' if devices else 'device-unavailable',
                'devices': devices, 'version': ov.__version__, 'observed_kernel_dispatch': None}

    def load(self, artifact, **options):
        self._verify(artifact); ov = self._module(); self.core = ov.Core()
        device = options.get('device', self.options.get('device', 'AUTO'))
        if device.split(':')[0] not in ('AUTO', 'MULTI', 'BATCH', 'CPU', 'GPU', 'NPU'):
            raise ValueError('unsupported OpenVINO device policy')
        config = {'PERFORMANCE_HINT': options.get('performance_hint', 'LATENCY')}
        if artifact.precision == 'fp32':
            config['INFERENCE_PRECISION_HINT'] = 'f32'
        if options.get('cache_dir'):
            config['CACHE_DIR'] = str(Path(options['cache_dir']).resolve())
        start = time.perf_counter()
        self.model = self.core.compile_model(artifact.locator, device, config)
        self.artifact = artifact
        try:
            executed = list(self.model.get_property('EXECUTION_DEVICES'))
        except Exception:
            executed = None
        self.last = {'compile_ms': (time.perf_counter()-start)*1000, 'allowed_devices': device,
                     'runtime_execution_devices': executed}
        return self

    def compile(self, artifact, **options):
        self.load(artifact, **options)
        return {'artifact': artifact.public(), 'compiled': True, **self.last}

    def encode_many(self, inputs):
        return self._run(lambda x: self.model(x), inputs)


class MIGraphXInference(LocalInferenceBase):
    module = 'migraphx'

    def load(self, artifact, **options):
        self._verify(artifact); mgx = self._module(); start = time.perf_counter()
        self.model = mgx.parse_onnx(artifact.locator)
        self.model.compile(mgx.get_target('gpu'), offload_copy=True, fast_math=False, exhaustive_tune=False)
        self.artifact = artifact; self.last = {'compile_ms': (time.perf_counter()-start)*1000}
        return self

    def compile(self, artifact, **options):
        self.load(artifact, **options)
        return {'artifact': artifact.public(), 'compiled': True, **self.last}

    def encode_many(self, inputs):
        mgx = self._module()
        return self._run(lambda x: self.model.run({k: mgx.argument(v) for k, v in x.items()}), inputs)


class CoreMLInference(LocalInferenceBase):
    module = 'coremltools'

    def load(self, artifact, **options):
        self._verify(artifact); ct = self._module()
        unit = options.get('compute_units', 'ALL')
        if unit not in ('CPU_ONLY', 'CPU_AND_GPU', 'CPU_AND_NE', 'ALL'):
            raise ValueError('unsupported Core ML compute units')
        start = time.perf_counter()
        self.model = ct.models.MLModel(artifact.locator, compute_units=getattr(ct.ComputeUnit, unit))
        self.artifact = artifact
        self.last = {'startup_ms': (time.perf_counter()-start)*1000, 'allowed_compute_units': unit,
                     'observed_ane_kernel': None}
        return self

    def encode_many(self, inputs):
        return self._run(lambda x: self.model.predict(x), inputs)
