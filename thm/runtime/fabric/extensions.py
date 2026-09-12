"""Explicit extension execution with generation, resource and lifecycle receipts.

Bindings own vendor ABI details. The controller owns validation, state, cleanup,
quarantine and provenance. No binding is imported or installed at core startup.
"""
from collections import deque
from dataclasses import asdict, dataclass
from importlib import metadata, util
import platform
import threading
import time

from .contracts import finite, identity
from .registry import ProviderUnavailable


@dataclass(frozen=True)
class ExtensionConfig:
    provider_id: str
    generation: str
    source_sha256: str
    runtime_identity: str
    dependency_version: str
    device_identity: str
    driver_identity: str = 'unknown'
    precision: str = 'fp32'
    max_input_bytes: int = 16 * 1024 * 1024
    max_output_bytes: int = 16 * 1024 * 1024
    max_calls: int = 1024
    wall_seconds: float = 30
    options: tuple = ()
    evidence: str = 'environment-unvalidated'

    def __post_init__(self):
        for key in ('provider_id', 'generation', 'runtime_identity', 'dependency_version', 'device_identity', 'driver_identity'):
            if not isinstance(getattr(self, key), str) or not getattr(self, key):
                raise ValueError('complete extension identity required: ' + key)
        if len(self.source_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.source_sha256):
            raise ValueError('source SHA256 required')
        for key in ('max_input_bytes', 'max_output_bytes', 'max_calls'):
            if type(getattr(self, key)) is not int or not 1 <= getattr(self, key) <= 2**30:
                raise ValueError('bounded extension resource required')
        finite(self.wall_seconds, 'wall seconds', .001)
        if self.wall_seconds > 300 or self.precision not in ('fp32', 'fp16', 'bf16', 'int8'):
            raise ValueError('invalid extension budget/precision')
        if self.evidence not in ('fixture-validated', 'environment-unvalidated', 'hardware-unvalidated'):
            raise ValueError('execution cannot self-certify acceptance')
        identity(self.options)

    def public(self):
        out = asdict(self)
        for key in ('generation', 'device_identity', 'runtime_identity'):
            out[key] = identity(out[key])
        out['options'] = identity(out['options'])
        return out


def byte_size(value):
    if hasattr(value, 'nbytes'):
        size = int(value.nbytes)
        if size < 0:
            raise ValueError('invalid array extent')
        return size
    if isinstance(value, (bytes, bytearray, memoryview)):
        return memoryview(value).nbytes
    if isinstance(value, dict):
        return sum(byte_size(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return sum(byte_size(v) for v in value)
    if type(value) in (int, float, bool):
        return 8
    raise TypeError('byte-addressable tensor/transfer input required')


class ExtensionSession:
    """Serial, generation-bound lifecycle. Deadlines gate results, not native preemption.

    Run this session in BoundedShadowExplorer for OS-enforced interruption of
    untrusted/long native calls. It never publishes a late or oversized result.
    """
    def __init__(self, config, binding, *, clock=time.monotonic):
        if not isinstance(config, ExtensionConfig):
            raise TypeError('ExtensionConfig required')
        for name in ('prepare', 'compile', 'load', 'execute', 'close'):
            if not callable(getattr(binding, name, None)):
                raise TypeError('complete binding required: ' + name)
        self.config, self.binding, self.clock = config, binding, clock
        self.state, self.artifact, self.handle = 'new', None, None
        self.lock = threading.RLock()
        self.events = deque(maxlen=128)
        self.calls, self.failure, self.started = 0, None, clock()
        self.sequence = 0

    def _event(self, stage, **fields):
        self.events.append({'stage': stage, 'sequence': self.sequence, **fields})
        self.sequence += 1

    def _fresh(self, generation=None, driver_identity=None, dependency_version=None):
        if self.state in ('closed', 'invalidated', 'quarantined'):
            raise ProviderUnavailable('extension ' + self.state)
        for supplied, actual in ((generation, self.config.generation), (driver_identity, self.config.driver_identity),
                                 (dependency_version, self.config.dependency_version)):
            if supplied is not None and supplied != actual:
                self.invalidate('identity-changed')
                raise ProviderUnavailable('extension identity changed')

    def _call(self, stage, function, *args):
        start = self.clock()
        try:
            value = function(*args)
            if self.clock() - self.started > self.config.wall_seconds:
                raise TimeoutError('extension lifetime budget')
        except Exception as exc:
            self.failure = ('resource-limit' if isinstance(exc, (MemoryError, TimeoutError)) else
                            'dependency-missing' if isinstance(exc, ImportError) else
                            'invalid-contract' if isinstance(exc, (ValueError, TypeError)) else 'runtime-failure')
            self.state = 'quarantined'
            self._event(stage, status='failed', error=self.failure)
            try:
                self.binding.close()
            except Exception:
                self._event('cleanup', status='failed')
            self.handle = self.artifact = None
            raise
        self._event(stage, status='completed', elapsed_ms=(self.clock()-start)*1000)
        return value

    def prepare(self, source):
        with self.lock:
            self._fresh()
            if self.state != 'new':
                raise ValueError('prepare requires new session')
            import hashlib
            if isinstance(source, (bytes, bytearray, memoryview)):
                observed = hashlib.sha256(source).hexdigest()
            elif hasattr(source, 'tobytes'):
                observed = hashlib.sha256(source.tobytes()).hexdigest()
            else:
                from .inference import artifact_digest
                observed = artifact_digest(source)
            if observed != self.config.source_sha256:
                raise ValueError('extension source checksum mismatch')
            self.artifact = self._call('prepare', self.binding.prepare, source, self.config)
            self.state = 'prepared'
            return self.artifact

    def compile(self):
        with self.lock:
            self._fresh()
            if self.state != 'prepared':
                raise ValueError('compile requires prepared artifact')
            self.artifact = self._call('compile', self.binding.compile, self.artifact, self.config)
            self.state = 'compiled'
            return self.artifact

    def load(self):
        with self.lock:
            self._fresh()
            if self.state != 'compiled':
                raise ValueError('load requires compiled artifact')
            self.handle = self._call('load', self.binding.load, self.artifact, self.config)
            self.state = 'loaded'
            return self.handle

    def execute(self, operation, inputs, *, generation, driver_identity=None, dependency_version=None):
        with self.lock:
            self._fresh(generation, driver_identity, dependency_version)
            if self.state != 'loaded':
                raise ValueError('execute requires loaded session')
            if operation not in self.binding.operations:
                raise ValueError('unsupported extension operation')
            if self.calls >= self.config.max_calls or byte_size(inputs) > self.config.max_input_bytes:
                raise MemoryError('extension input/call budget')
            self.calls += 1
            def execute():
                out = self.binding.execute(self.handle, operation, inputs)
                if byte_size(out) > self.config.max_output_bytes:
                    raise MemoryError('extension output budget')
                return out
            return self._call(operation, execute)

    def invalidate(self, reason='source-generation-changed'):
        with self.lock:
            if self.state == 'closed':
                return
            try:
                self.binding.close()
            finally:
                self.handle = self.artifact = None
                self.state = 'invalidated'
                self._event('invalidate', reason=reason)

    def receipt(self):
        with self.lock:
            out = {'schema': 'thm-extension/1', 'config': self.config.public(), 'state': self.state,
                   'calls': self.calls, 'events': list(self.events), 'error': self.failure,
                   'fallback': 'validated-reference', 'automatic_install': False,
                   'hardware_accepted': False, 'observed_kernel_dispatch': None,
                   'freshness_scope': 'process' if self.config.driver_identity == 'unknown' else 'bound-identity'}
            return {**out, 'receipt_sha256': identity(out)}

    def close(self):
        with self.lock:
            if self.state != 'closed':
                try:
                    self.binding.close()
                finally:
                    self.handle, self.artifact, self.state = None, None, 'closed'
                    self._event('close')


class FunctionBinding:
    """Typed vendor binding assembled from explicit, already-loaded SDK callables.

    Useful for C/ObjC SDKs with version-specific handles and caller-owned memory.
    It does not treat symbol discovery as execution or select an ABI implicitly.
    """
    def __init__(self, *, operations, prepare, compile, load, execute, close):
        self.operations = tuple(operations)
        if not self.operations or any(not callable(f) for f in (prepare, compile, load, execute, close)):
            raise TypeError('explicit vendor operations and functions required')
        self.prepare, self.compile, self.load, self.execute, self.close = prepare, compile, load, execute, close


EXTENSION_MODULES = {
    'google.pjrt': ('jax', 'jax'), 'aws.neuron': ('torch-neuronx', 'torch_neuronx'),
    'tenstorrent.ttnn': ('ttnn', 'ttnn'), 'portable.vulkan': ('vulkan', 'vulkan'),
    'portable.opencl': ('pyopencl', 'pyopencl'), 'diskann': ('diskannpy', 'diskannpy'),
}


def discover_extension(provider_id):
    distribution, module = EXTENSION_MODULES.get(provider_id, (None, None))
    try:
        version = metadata.version(distribution) if distribution else None
    except metadata.PackageNotFoundError:
        version = None
    try:
        available = bool(module and util.find_spec(module))
    except (ValueError, ImportError):
        available = False
    return {'provider': provider_id, 'module_present': available, 'dependency_version': version,
            'os': platform.system(), 'driver_identity': 'unknown', 'device_execution': False,
            'automatic_install': False, 'contract_schema': 'thm-extension/1'}
