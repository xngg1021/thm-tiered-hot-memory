"""Optional public Python SDK bindings for explicit extension sessions.

These bindings return tensors/scores, not semantic ranking acceptance. Callers
retain the canonical independent ranking/quality gate and source authority.
"""
from pathlib import Path
import importlib


class PJRTBinding:
    operations = ('score',)
    def __init__(self, *, backend='cpu', device_index=0):
        self.backend, self.device_index, self.handle = backend, device_index, None

    def prepare(self, source, config):
        import numpy as np
        if config.precision != 'fp32':
            raise ValueError('PJRT score binding requires fp32')
        self.api = importlib.import_module('jax')
        devices = self.api.devices(self.backend)
        if not 0 <= self.device_index < len(devices):
            raise ValueError('PJRT device unavailable')
        self.device = devices[self.device_index]
        array = np.asarray(source, dtype=np.float32)
        if array.ndim != 2 or not array.size or not np.isfinite(array).all():
            raise ValueError('finite matrix required')
        self.shape = array.shape
        return self.api.device_put(array, self.device)

    def compile(self, artifact, config):
        import numpy as np
        # Compile a fixed-shape exact score operation; source matrix is device resident.
        def score(query):
            return artifact @ query
        sample = self.api.device_put(np.zeros(artifact.shape[1], dtype=np.float32), self.device)
        return self.api.jit(score).lower(sample).compile()

    def load(self, artifact, config):
        self.handle = artifact
        return artifact

    def execute(self, handle, operation, inputs):
        import numpy as np
        array = np.asarray(inputs, dtype=np.float32)
        if array.shape != (self.shape[1],) or not np.isfinite(array).all():
            raise ValueError('PJRT query shape mismatch')
        query = self.api.device_put(array, self.device)
        output = handle(query)
        if hasattr(output, 'block_until_ready'):
            output.block_until_ready()
        return np.asarray(output)

    def close(self):
        self.handle = None


class NeuronBinding:
    """Load an explicit local precompiled TorchScript Neuron artifact."""
    operations = ('inference',)
    def prepare(self, source, config):
        self.api = importlib.import_module('torch')
        importlib.import_module('torch_neuronx')
        path = Path(source)
        if not path.is_file() or path.is_symlink():
            raise ValueError('local precompiled Neuron artifact required')
        return path

    def compile(self, artifact, config):
        # Input contract is already-compiled TorchScript; no hidden compiler call.
        self.model = self.api.jit.load(str(artifact))
        self.model.eval()
        return self.model

    def load(self, artifact, config):
        return artifact

    def execute(self, handle, operation, inputs):
        with self.api.inference_mode():
            output = handle(*(self.api.as_tensor(x) for x in inputs))
        if isinstance(output, (tuple, list)):
            return tuple(x.detach().cpu().numpy() for x in output)
        return output.detach().cpu().numpy()

    def close(self):
        self.model = None


class TTNNBinding:
    operations = ('score',)
    def __init__(self, *, device_index=0):
        self.device_index, self.device, self.matrix = device_index, None, None

    def prepare(self, source, config):
        import numpy as np
        if config.precision != 'bf16':
            raise ValueError('TTNN score binding requires explicit bf16 operating point')
        array = np.asarray(source, dtype=np.float32)
        if array.ndim != 2 or not array.size or not np.isfinite(array).all():
            raise ValueError('finite TTNN score matrix required')
        self.shape = array.shape
        self.api = importlib.import_module('ttnn')
        self.torch = importlib.import_module('torch')
        self.device = self.api.open_device(device_id=self.device_index)
        self.matrix = self.api.from_torch(self.torch.as_tensor(array, dtype=self.torch.bfloat16), dtype=self.api.bfloat16, device=self.device, layout=self.api.TILE_LAYOUT)
        return self.matrix

    def compile(self, artifact, config):
        # TTNN specializes its program on first operation; source stays resident.
        return artifact

    def load(self, artifact, config):
        return artifact

    def execute(self, handle, operation, inputs):
        import numpy as np
        array = np.asarray(inputs, dtype=np.float32)
        if array.shape != (self.shape[1],) or not np.isfinite(array).all():
            raise ValueError('TTNN query shape mismatch')
        query = self.api.from_torch(self.torch.as_tensor(array, dtype=self.torch.bfloat16).reshape(-1, 1),
                                   dtype=self.api.bfloat16, device=self.device, layout=self.api.TILE_LAYOUT)
        result = None
        try:
            result = self.api.matmul(handle, query)
            return self.api.to_torch(result).float().numpy().reshape(-1)
        finally:
            self.api.deallocate(query)
            if result is not None:
                self.api.deallocate(result)

    def close(self):
        if self.device is not None:
            try:
                if self.matrix is not None:
                    self.api.deallocate(self.matrix)
            finally:
                self.api.close_device(self.device)
                self.device, self.matrix = None, None


class OpenCLBinding:
    operations = ('score',)
    KERNEL = '''
    __kernel void scores(__global const float *matrix, __global const float *query,
                         __global float *output, const int dimension) {
        int row = get_global_id(0); float value = 0.0f;
        for (int j=0; j<dimension; ++j) value += matrix[row*dimension+j]*query[j];
        output[row] = value;
    }
    '''
    def __init__(self, *, platform_index=0, device_index=0):
        self.platform_index, self.device_index = platform_index, device_index
        self.resources = []

    def prepare(self, source, config):
        import numpy as np
        if config.precision != 'fp32':
            raise ValueError('OpenCL score binding requires fp32')
        self.api = importlib.import_module('pyopencl')
        devices = self.api.get_platforms()[self.platform_index].get_devices()
        self.context = self.api.Context([devices[self.device_index]])
        self.queue = self.api.CommandQueue(self.context)
        array = np.ascontiguousarray(source, dtype=np.float32)
        if array.ndim != 2 or not array.size or not np.isfinite(array).all():
            raise ValueError('finite OpenCL score matrix required')
        self.shape = array.shape
        matrix = self.api.Buffer(self.context, self.api.mem_flags.READ_ONLY | self.api.mem_flags.COPY_HOST_PTR, hostbuf=array)
        self.resources.append(matrix)
        return matrix

    def compile(self, artifact, config):
        self.program = self.api.Program(self.context, self.KERNEL).build(options=[])
        return artifact

    def load(self, artifact, config):
        return artifact

    def execute(self, handle, operation, inputs):
        import numpy as np
        query = np.ascontiguousarray(inputs, dtype=np.float32)
        if query.shape != (self.shape[1],) or not np.isfinite(query).all():
            raise ValueError('OpenCL query shape mismatch')
        output = np.empty(self.shape[0], dtype=np.float32)
        q = self.api.Buffer(self.context, self.api.mem_flags.READ_ONLY | self.api.mem_flags.COPY_HOST_PTR, hostbuf=query)
        out = None
        try:
            out = self.api.Buffer(self.context, self.api.mem_flags.WRITE_ONLY, output.nbytes)
            self.program.scores(self.queue, (self.shape[0],), None, handle, q, out, np.int32(self.shape[1]))
            self.api.enqueue_copy(self.queue, output, out).wait()
            return output
        finally:
            self.queue.finish()
            q.release()
            if out is not None:
                out.release()

    def close(self):
        if getattr(self, 'queue', None) is not None:
            self.queue.finish()
        for value in self.resources:
            value.release()
        self.resources.clear()
        self.program = self.queue = self.context = None


BINDINGS = {'google.pjrt': PJRTBinding, 'aws.neuron': NeuronBinding,
            'tenstorrent.ttnn': TTNNBinding, 'portable.opencl': OpenCLBinding}


class DiskANNBinding:
    """Explicit approximate memory index using the published diskannpy API.

    Candidate IDs/distances require a separate retrieval quality admission gate.
    Builds stay in an owned temporary directory and are removed on close.
    """
    operations = ('search',)
    def __init__(self, *, complexity=64, graph_degree=32, max_build_bytes=64*1024*1024):
        if any(type(x) is not int or x < 1 for x in (complexity, graph_degree, max_build_bytes)):
            raise ValueError('positive DiskANN build bounds required')
        self.complexity, self.graph_degree, self.max_build_bytes = complexity, graph_degree, max_build_bytes
        self.directory = self.index = None

    def prepare(self, source, config):
        import numpy as np
        import tempfile
        if config.precision != 'fp32':
            raise ValueError('DiskANN binding requires fp32')
        array = np.ascontiguousarray(source, dtype=np.float32)
        if array.ndim != 2 or not array.size or not np.isfinite(array).all():
            raise ValueError('finite DiskANN matrix required')
        if array.nbytes > self.max_build_bytes:
            raise MemoryError('DiskANN source budget')
        self.api = importlib.import_module('diskannpy')
        self.shape = array.shape
        self.directory = tempfile.TemporaryDirectory(prefix='thm-diskann-')
        return array

    def compile(self, artifact, config):
        self.api.build_memory_index(data=artifact, distance_metric='l2', index_directory=self.directory.name,
                                    complexity=self.complexity, graph_degree=self.graph_degree, num_threads=1)
        return self.directory.name

    def load(self, artifact, config):
        self.index = self.api.StaticMemoryIndex(index_directory=artifact, num_threads=1,
                                               initial_search_complexity=self.complexity)
        return self.index

    def execute(self, handle, operation, inputs):
        import numpy as np
        query, k = np.ascontiguousarray(inputs['query'], dtype=np.float32), inputs['k']
        if query.shape != (self.shape[1],) or not np.isfinite(query).all() or type(k) is not int or not 1 <= k <= self.shape[0]:
            raise ValueError('invalid DiskANN query/k')
        out = handle.search(query=query, k_neighbors=k, complexity=max(k, self.complexity))
        ids, distances = np.asarray(out.identifiers), np.asarray(out.distances)
        if ids.shape != (k,) or distances.shape != (k,) or not np.isfinite(distances).all() or any(int(i) != i or not 0 <= i < self.shape[0] for i in ids):
            raise ValueError('invalid DiskANN result')
        return {'identifiers': ids, 'distances': distances}

    def close(self):
        self.index = None
        if self.directory is not None:
            self.directory.cleanup()
            self.directory = None


BINDINGS['diskann'] = DiskANNBinding
