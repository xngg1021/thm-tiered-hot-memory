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


def bounded_artifact_digest(source, maximum_bytes, *, copy_root=None):
    """Match the model-bundle identity while bounding traversal and every read."""
    import hashlib
    import os
    import stat
    from pathlib import Path
    from ..identity import digest
    source = Path(source)
    if source.is_symlink() or not source.exists():
        raise ValueError('existing non-symlink artifact required')
    root = source.parent if source.is_file() else source
    if not root.is_dir() or root.is_symlink():
        raise ValueError('local artifact bundle required')
    from contextlib import ExitStack
    from thm._bounded_files import validated_descriptor
    # Hold directory descriptors until copying finishes. Enumeration and opens
    # stay relative to those directories, even if their pathnames are replaced.
    with ExitStack() as directories:
        root_fd, _ = directories.enter_context(validated_descriptor(root, directory=True))
        pending, files, entries, total = [(root, root_fd)], [], 0, 0
        while pending:
            directory, directory_fd = pending.pop()
            with os.scandir(directory_fd if os.name == 'posix' else directory) as children:
                for entry in children:
                    entries += 1
                    if entries > 4096:
                        raise MemoryError('extension artifact entry budget')
                    path = directory / entry.name
                    # DirEntry.stat returns zero device/inode on Windows.
                    info = os.stat(entry.name if os.name == 'posix' else path,
                                   dir_fd=directory_fd if os.name == 'posix' else None,
                                   follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise ValueError('symlink artifact content refused')
                    if stat.S_ISDIR(info.st_mode):
                        child_fd, _ = directories.enter_context(validated_descriptor(
                            entry.name if os.name == 'posix' else path, directory=True,
                            expected=info, dir_fd=directory_fd if os.name == 'posix' else None))
                        pending.append((path, child_fd))
                    elif stat.S_ISREG(info.st_mode):
                        if entry.name == 'thm-preparation.json':
                            if path == source:
                                raise ValueError('preparation metadata is not a model artifact')
                            continue
                        total += info.st_size
                        if total > maximum_bytes:
                            raise MemoryError('extension artifact input budget')
                        files.append((path, directory_fd, info))
                    else:
                        raise ValueError('regular artifact files required')
        if not files:
            raise ValueError('empty artifact bundle')
        rows, consumed = [], 0
        for path, directory_fd, expected in sorted(files):
            h, length = hashlib.sha256(), 0
            with ExitStack() as stack:
                fd, _ = stack.enter_context(validated_descriptor(
                    path.name if os.name == 'posix' else path, expected=expected,
                    dir_fd=directory_fd if os.name == 'posix' else None))
                target = None
                if copy_root is not None:
                    destination = Path(copy_root) / path.relative_to(root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    target = stack.enter_context(destination.open('xb'))
                while True:
                    block = os.read(fd, min(1024*1024, maximum_bytes-consumed+1))
                    if not block:
                        break
                    consumed += len(block); length += len(block)
                    if consumed > maximum_bytes:
                        raise MemoryError('artifact grew beyond preparation budget')
                    h.update(block)
                    if target is not None and target.write(block) != len(block):
                        raise OSError('short artifact staging write')
                if target is not None:
                    target.flush()
                    os.fsync(target.fileno())
            if length != expected.st_size:
                raise ValueError('artifact changed while hashing')
            rows.append({'name': path.relative_to(root).as_posix(), 'sha256': h.hexdigest(), 'bytes': length})
        return digest(rows)


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
        self.source_shape = None
        self._artifact_directory = None

    def _discard_staged(self):
        if self._artifact_directory is not None:
            self._artifact_directory.cleanup()
            self._artifact_directory = None

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
            self.handle = self.artifact = None
            try:
                self.binding.close()
            except Exception:
                self._event('cleanup', status='failed')
            self.handle = self.artifact = None
            self._discard_staged()
            raise
        self._event(stage, status='completed', elapsed_ms=(self.clock()-start)*1000)
        return value

    def prepare(self, source):
        with self.lock:
            self._fresh()
            if self.state != 'new':
                raise ValueError('prepare requires new session')
            import hashlib
            if (isinstance(source, (bytes, bytearray, memoryview)) or hasattr(source, 'nbytes')) and byte_size(source) > self.config.max_input_bytes:
                raise MemoryError('extension preparation input budget')
            if isinstance(source, (bytearray, memoryview)):
                source = bytes(source)
            elif hasattr(source, 'tobytes') and callable(getattr(source, 'copy', None)):
                source = source.copy()
            if isinstance(source, (bytes, bytearray, memoryview)) or hasattr(source, 'nbytes'):
                if byte_size(source) > self.config.max_input_bytes:
                    raise MemoryError('extension preparation input budget')
            self.source_shape = tuple(source.shape) if hasattr(source, 'shape') else None
            if isinstance(source, (bytes, bytearray, memoryview)):
                observed = hashlib.sha256(source).hexdigest()
            elif hasattr(source, 'tobytes'):
                observed = hashlib.sha256(source.tobytes()).hexdigest()
            else:
                import tempfile
                from pathlib import Path
                original = Path(source)
                source_was_file = original.is_file()
                self._artifact_directory = tempfile.TemporaryDirectory(prefix='thm-artifact-')
                try:
                    observed = bounded_artifact_digest(original, self.config.max_input_bytes, copy_root=self._artifact_directory.name)
                    source = Path(self._artifact_directory.name) / original.name if source_was_file else Path(self._artifact_directory.name)
                except Exception:
                    self._discard_staged()
                    raise
            if observed != self.config.source_sha256:
                self._discard_staged()
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
            self.handle = self.artifact = None
            try:
                self.binding.close()
            finally:
                self.handle = self.artifact = None
                self._discard_staged()
                self.state = 'invalidated'
                self._event('invalidate', reason=reason)

    def receipt(self):
        with self.lock:
            out = {'schema': 'thm-extension/1', 'config': self.config.public(), 'state': self.state,
                   'source_shape': self.source_shape,
                   'binding_identity': identity({'class': type(self.binding).__module__ + ':' + type(self.binding).__name__,
                       'configuration': getattr(self.binding, 'configuration', {}), 'options': self.config.options}),
                   'calls': self.calls, 'events': list(self.events), 'error': self.failure,
                   'fallback': 'validated-reference', 'automatic_install': False,
                   'hardware_accepted': False, 'observed_kernel_dispatch': None,
                   'freshness_scope': 'process' if self.config.driver_identity == 'unknown' else 'bound-identity'}
            return {**out, 'receipt_sha256': identity(out)}

    def close(self):
        with self.lock:
            if self.state != 'closed':
                self.handle = self.artifact = None
                try:
                    self.binding.close()
                finally:
                    self._discard_staged()
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
