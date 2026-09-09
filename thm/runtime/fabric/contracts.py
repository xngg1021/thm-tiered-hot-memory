"""Execution contracts; providers have no reference to memory authority."""
from dataclasses import asdict, dataclass, field
from enum import IntEnum
import hashlib
import json
import math
from typing import Protocol, runtime_checkable


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def finite(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError('invalid ' + name)
    return value


class Maturity(IntEnum):
    DOCUMENTED = 0
    DISCOVERABLE = 1
    PREPARABLE = 2
    EXECUTABLE = 3
    RECEIPT_COMPLETE = 4
    HARDWARE_ACCEPTED = 5


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    vendor: str
    runtime_family: str
    factory: str
    dependencies: tuple = ()
    supported_device_classes: tuple = ('cpu',)
    supported_precisions: tuple = ('fp32',)
    supported_operations: tuple = ()
    supported_os: tuple = ('Linux', 'Windows', 'Darwin')
    priority: int = 0
    compile: bool = False
    resident_handle: bool = False
    asynchronous: bool = False
    multi_device: bool = False
    telemetry: bool = False
    maturity: int = 1
    validation_state: str = 'hardware-unvalidated'
    options: tuple = ()

    def __post_init__(self):
        if not self.provider_id or ':' not in self.factory or self.maturity not in range(6):
            raise ValueError('invalid provider spec')
        if self.maturity == 5 and self.validation_state != 'hardware-accepted':
            raise ValueError('hardware evidence required')

    def public(self):
        return asdict(self)


@dataclass(frozen=True)
class IndexIdentity:
    scope: str
    generation: str
    embedding_profile: str
    provider: str
    provider_version: str
    index_config: str
    precision: str = 'fp32'
    device: str = 'cpu'
    placement: str = 'dram'
    runtime: str = 'unknown'
    training_sha: str | None = None

    def __post_init__(self):
        if not all(isinstance(v, str) and v for k, v in asdict(self).items() if k != 'training_sha'):
            raise ValueError('complete index identity required')

    @property
    def key(self):
        return identity(asdict(self))

    def public(self):
        out = asdict(self)
        out['scope'] = identity(self.scope)
        return out


@dataclass(frozen=True)
class RuntimeSample:
    """All times are milliseconds, except explicit process/device CPU/GPU seconds.

    latency_ms spans queue entry to completed result; stage clocks may overlap.
    Unknown measurements remain None; sample contains no query or private path.
    """
    candidate: str
    workload: str
    latency_ms: float
    queue_wait_ms: float = 0.0
    encode_ms: float | None = None
    search_ms: float | None = None
    transfer_ms: float | None = None
    materialization_ms: float | None = None
    packing_ms: float | None = None
    cpu_seconds: float | None = None
    gpu_seconds: float | None = None
    cpu_utilization: float | None = None
    gpu_utilization: float | None = None
    ram_peak: int | None = None
    vram_peak: int | None = None
    bytes_read: int | None = None
    bytes_written: int | None = None
    host_device_bytes: int | None = None
    queries_per_second: float | None = None
    documents_per_second: float | None = None
    startup_ms: float | None = None
    compile_ms: float | None = None
    joules: float | None = None
    energy_source: str | None = None
    batch: int = 1
    requested_threads: int | None = None
    provider_threads: int | None = None
    resident_hit: bool = False
    fallback: bool = False
    error: str | None = None
    semantic_policy: str = 'auto-safe'
    profile_source: str = 'bootstrap'

    def __post_init__(self):
        if self.workload not in ('interactive', 'bulk', 'background'):
            raise ValueError('invalid workload')
        for k, v in asdict(self).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                finite(v, k)
        if self.batch < 1 or self.batch > 256:
            raise ValueError('invalid actual batch')
        if self.joules is not None and not self.energy_source:
            raise ValueError('energy requires observation source')

    def public(self):
        return asdict(self)


@runtime_checkable
class DeviceProvider(Protocol):
    def discover(self): ...
    def capabilities(self): ...
    def fingerprint(self): ...
    def topology(self): ...
    def telemetry(self): ...


@runtime_checkable
class InferenceProvider(Protocol):
    def probe(self): ...
    def prepare(self, source, **options): ...
    def compile(self, artifact, **options): ...
    def load(self, artifact, **options): ...
    def encode_one(self, inputs): ...
    def encode_many(self, inputs): ...
    def capabilities(self): ...
    def telemetry(self): ...
    def close(self): ...


@runtime_checkable
class VectorIndexProvider(Protocol):
    def build(self, vectors, ids, identity, **options): ...
    def load_handle(self, identity): ...
    def search(self, handle, query_vectors, top_k): ...
    def update_or_rebuild(self, vectors, ids, identity, **options): ...
    def memory_usage(self): ...
    def capabilities(self): ...
    def telemetry(self): ...
    def close(self): ...


@runtime_checkable
class TransferProvider(Protocol):
    def supports(self, source, target): ...
    def estimate(self, size, source, target): ...
    def stage(self, data, **options): ...
    def transfer(self, data, target, **options): ...
    def synchronize(self): ...
    def telemetry(self): ...

