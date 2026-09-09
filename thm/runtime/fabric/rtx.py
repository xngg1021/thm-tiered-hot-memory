"""TensorRT-RTX native AOT/JIT, immutable engine cache, explicit CUDA buffers."""
import threading
import time
from .inference import LocalInferenceBase
from .store import CompiledArtifactStore
from .contracts import identity
from .registry import ProviderUnavailable


class TensorRTRTXInference(LocalInferenceBase):
    module = 'tensorrt_rtx'

    def __init__(self, spec):
        super().__init__(spec)
        self.lock = threading.RLock(); self.engine = None; self.runtime = None

    def probe(self):
        trt = self._module()
        import cupy as cp
        count = cp.cuda.runtime.getDeviceCount()
        return {'provider': self.spec.provider_id, 'availability': 'available' if count else 'device-unavailable',
                'devices': ['cuda:'+str(i) for i in range(count)], 'version': trt.__version__,
                'driver_runtime': cp.cuda.runtime.driverGetVersion(), 'observed_kernel_dispatch': None}

    def _dependencies(self, artifact, options):
        import cupy as cp
        device = cp.cuda.runtime.getDeviceProperties(cp.cuda.runtime.getDevice())
        return {'model_source': artifact.source_sha, 'transformation': 'ONNX-to-TensorRT-RTX-AOT-JIT',
                'provider_version': artifact.provider_version,
                'driver_runtime': [cp.cuda.runtime.driverGetVersion(), cp.cuda.runtime.runtimeGetVersion()],
                'device_capability': {k: device.get(k) for k in ('major','minor','totalGlobalMem')},
                'precision': artifact.precision, 'compiler_options': options}

    def _engine_bytes(self, artifact, cache_root, options):
        self._verify(artifact); trt = self._module()
        dependencies = self._dependencies(artifact, options)
        cache = CompiledArtifactStore(cache_root) if cache_root else None
        value = cache.load(dependencies) if cache else None
        start = time.perf_counter(); hit = value is not None
        self.logger = trt.Logger(trt.Logger.ERROR)
        if value is None:
            builder = trt.Builder(self.logger); network = builder.create_network(0)
            parser = trt.OnnxParser(network, self.logger)
            if not parser.parse_from_file(artifact.locator):
                raise ValueError('TensorRT-RTX local ONNX parse failed')
            config = builder.create_builder_config()
            workspace = options.get('workspace_bytes', 64*1024**2)
            if type(workspace) is not int or not 0 < workspace <= 2*1024**3:
                raise ValueError('bounded compiler workspace required')
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace)
            shapes = options.get('shapes', {})
            if shapes:
                profile = builder.create_optimization_profile()
                for name, bounds in shapes.items():
                    if len(bounds) != 3 or not profile.set_shape(name, *bounds):
                        raise ValueError('invalid dynamic shape bounds')
                config.add_optimization_profile(profile)
            # TensorRT-RTX owns kernel heuristics. This provider never enables
            # FP16/INT8/TF32 flags or changes source weights.
            serialized = builder.build_serialized_network(network, config)
            if serialized is None:
                raise ProviderUnavailable('TensorRT-RTX compilation failed')
            value = bytes(serialized)
            self._verify(artifact)
            if cache:
                cache.publish(dependencies, value)
        self.last = {'compile_ms': (time.perf_counter()-start)*1000, 'compiled_cache_hit': hit,
                     'compiled_artifact_key': identity(dependencies), 'compiler_workspace_bytes': options.get('workspace_bytes', 64*1024**2),
                     'vendor_heuristics': 'TensorRT-RTX-builder-and-runtime-JIT'}
        return value

    def compile(self, artifact, *, cache_root=None, **options):
        with self.lock:
            self._engine_bytes(artifact, cache_root, options)
            return {'artifact': artifact.public(), 'compiled': True, **self.last}

    def load(self, artifact, *, cache_root=None, **options):
        with self.lock:
            value = self._engine_bytes(artifact, cache_root, options); trt = self._module()
            start = time.perf_counter(); self.runtime = trt.Runtime(self.logger)
            self.engine = self.runtime.deserialize_cuda_engine(value)
            if self.engine is None:
                raise ProviderUnavailable('TensorRT-RTX engine incompatible')
            self.model = self.engine.create_execution_context()
            if self.model is None:
                self.close(); raise ProviderUnavailable('TensorRT-RTX context failed')
            self.artifact = artifact; self.last['jit_startup_ms'] = (time.perf_counter()-start)*1000
            return self

    def encode_many(self, inputs):
        import cupy as cp
        trt = self._module()
        if not isinstance(inputs, dict):
            raise ValueError('named TensorRT-RTX input tensors required')
        def execute(values):
            names = [self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors)]
            expected = {n for n in names if self.engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT}
            if set(values) != expected:
                raise ValueError('TensorRT-RTX input names mismatch')
            stream = cp.cuda.Stream(non_blocking=True); buffers = {}; output_names = []
            with stream:
                for name in expected:
                    buffers[name] = cp.ascontiguousarray(values[name], dtype=trt.nptype(self.engine.get_tensor_dtype(name)))
                    if not self.model.set_input_shape(name, buffers[name].shape):
                        raise ValueError('TensorRT-RTX input shape outside profile')
                for name in names:
                    if name not in expected:
                        shape = tuple(self.model.get_tensor_shape(name))
                        if any(d < 0 for d in shape):
                            raise ValueError('data-dependent outputs require explicit allocator')
                        buffers[name] = cp.empty(shape, dtype=trt.nptype(self.engine.get_tensor_dtype(name)))
                        output_names.append(name)
                    if not self.model.set_tensor_address(name, buffers[name].data.ptr):
                        raise ValueError('TensorRT-RTX tensor binding failed')
                if not self.model.execute_async_v3(stream.ptr):
                    raise ProviderUnavailable('TensorRT-RTX enqueue failed')
                stream.synchronize()
                result = {name: cp.asnumpy(buffers[name]) for name in output_names}
            self.last['host_device_bytes'] = sum(b.nbytes for b in buffers.values())
            return result
        with self.lock:
            return self._run(execute, inputs)

    def close(self):
        with self.lock:
            super().close(); self.engine = None; self.runtime = None
