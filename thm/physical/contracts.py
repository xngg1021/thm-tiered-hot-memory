"""Separate logical, representation, transfer and allocation identities."""
from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from thm.runtime.identity import digest

class DataRole(str, Enum):
    CONTROL_METADATA='control_metadata'
    JOURNAL='journal'
    FTS_INDEX='fts_index'
    LOCATOR='locator'
    VECTOR_SEGMENT='vector_segment'
    RAW_CORPUS='raw_corpus'
    DERIVED_CACHE='derived_cache'
    TELEMETRY='telemetry'
    IMMUTABLE_HISTORY='immutable_history'
    BACKUP='backup'
    ARCHIVE='archive'

@dataclass(frozen=True)
class GenerationRef:
    scope: str
    source_generation: str
    embedding_profile_id: str | None = None

@dataclass(frozen=True)
class LogicalObjectRef:
    source_id: str
    parent_id: str
    generation: GenerationRef
    kind: str = 'memory_item'

@dataclass(frozen=True)
class RepresentationRef:
    logical: LogicalObjectRef
    representation_id: str
    role: DataRole
    authority: bool = False
    def __post_init__(self):
        if self.authority:raise ValueError('representation cannot acquire semantic authority')

@dataclass(frozen=True)
class SegmentRef:
    parent: LogicalObjectRef
    locator_id: str
    start: int
    end: int
    complete: bool = False
    def __post_init__(self):
        if self.complete or not 0 <= self.start < self.end:
            raise ValueError('partial segment requires valid parent offsets and complete=false')

@dataclass(frozen=True)
class VectorShardRef:
    generation: GenerationRef
    object_sha256: str
    row_order_sha256: str
    rows: int
    dimension: int
    dtype: str = 'f32le'

@dataclass(frozen=True)
class TransferExtent:
    object_sha256: str
    offset: int
    length: int
    def __post_init__(self):
        if self.offset < 0 or self.length <= 0:raise ValueError('invalid transfer extent')

@dataclass(frozen=True)
class AllocationExtent:
    target_id: str
    allocation_id: str
    offset: int
    length: int
    alignment: int | None = None
    def __post_init__(self):
        if self.offset < 0 or self.length <= 0:raise ValueError('invalid allocation extent')

@dataclass(frozen=True)
class StorageTarget:
    target_id: str
    media_class: str = 'unknown'
    protocol: str | None = None
    filesystem: str | None = None
    root: str | None = field(default=None, repr=False)
    mount_relation: str | None = None
    numa_node: int | None = None
    pcie_bdf: str | None = None
    capacity: int | None = None
    free_capacity: int | None = None
    logical_block: int | None = None
    physical_block: int | None = None
    readonly: bool | None = None
    mmap: bool | None = None
    direct_io: bool | None = None
    dax: bool | None = None
    zoned: str | None = None
    remote: bool | None = None
    network_rtt_ms: float | None = None
    replication: int | None = None
    failure_domain: str | None = None
    gpu_direct: bool | None = None
    driver_identity: str | None = None
    observation: str = 'unvalidated'
    adapter: str = 'unavailable'
    def __post_init__(self):
        for name in ('capacity','free_capacity','logical_block','physical_block','replication'):
            value=getattr(self,name)
            if value is not None and (type(value) is not int or value<0):raise ValueError('invalid observed '+name)
        for name in ('readonly','mmap','direct_io','dax','remote','gpu_direct'):
            value=getattr(self,name)
            if value is not None and type(value) is not bool:raise ValueError('invalid capability '+name)
    def public(self):
        data=asdict(self);data.pop('root')
        return data
    @property
    def fingerprint(self):
        data=self.public();data.pop('free_capacity');data.pop('network_rtt_ms')
        from pathlib import Path
        import hashlib
        root=Path(__file__).parent
        implementation=digest({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('contracts.py','probe.py','benchmark.py','adapters.py')})
        return digest({'target':data,'schema':1,'implementation':implementation})

@dataclass(frozen=True)
class TopologyNode:
    node_id: str
    kind: str
    observed: dict = field(default_factory=dict)

@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    relation: str
    latency_ns: float | None = None
    bandwidth_bytes_s: float | None = None
    numa_distance: int | None = None
    copy_required: bool | None = None
    dma_capable: bool | None = None
    transport: str | None = None

@dataclass(frozen=True)
class StorageTopology:
    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]
    def __post_init__(self):
        ids=[n.node_id for n in self.nodes]
        if len(set(ids))!=len(ids) or any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError('invalid topology identities')

@dataclass(frozen=True)
class StorageProfile:
    target_fingerprint: str
    costs: tuple[dict, ...]
    scratch_bytes: int
    wall_seconds: float
    cache_state: str = 'warm-or-os-managed; cold unavailable'
    schema: int = 1
    @property
    def id(self):return digest(asdict(self))

@dataclass(frozen=True)
class PlacementIntent:
    role: DataRole
    workload: str | None = None
    capacity_required: int = 0
    local_only: bool = True
    mutable: bool = False
    p95_latency_ms: float | None = None
    minimum_replicas: int | None = None
    failure_domain: str | None = None
    operation: str | None = None
    transfer_size: int = 4096
    concurrency: int = 1
    accelerator_consumer: str | None = None
    max_write_amplification: float | None = None
    def __post_init__(self):
        for name in ('p95_latency_ms','max_write_amplification'):
            value=getattr(self,name)
            if value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):raise ValueError('invalid constraint '+name)
        for name in ('capacity_required','transfer_size','concurrency'):
            value=getattr(self,name)
            if type(value) is not int or value<(0 if name=='capacity_required' else 1):raise ValueError('invalid constraint '+name)
        if self.minimum_replicas is not None and (type(self.minimum_replicas) is not int or self.minimum_replicas<1):raise ValueError('invalid durability constraint')
        role=DataRole(self.role)
        sequential=role in (DataRole.JOURNAL,DataRole.RAW_CORPUS,DataRole.TELEMETRY,DataRole.IMMUTABLE_HISTORY,DataRole.BACKUP,DataRole.ARCHIVE)
        if self.workload is None:object.__setattr__(self,'workload','archive' if role==DataRole.ARCHIVE else 'background' if sequential else 'interactive')
        if self.operation is None:object.__setattr__(self,'operation','buffered-sequential' if sequential else 'buffered-random')
        if self.workload not in ('interactive','bulk','background','archive') or self.capacity_required<0:
            raise ValueError('invalid placement intent')

@dataclass(frozen=True)
class PlacementManifest:
    generation: GenerationRef
    object_sha256: str
    target_id: str
    object_name: str
    row_order_sha256: str
    byte_length: int
    publication: str = 'verified'

@dataclass(frozen=True)
class MigrationPlan:
    migration_id: str
    predecessor: PlacementManifest
    target_id: str
    retire_source: bool = False

@dataclass(frozen=True)
class MigrationReceipt:
    migration_id: str
    stage: str
    authoritative_object: str
    source_valid: bool
    target_verified: bool
    published: bool
    cleanup_safe: bool
    migration_bytes: int = 0

@dataclass
class PhysicalTelemetry:
    target_id: str
    bytes_requested: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    transfer_seconds: float = 0
    access_mode: str = 'buffered'
    staging_seconds: float | None = None
    cache_level: str | None = None
    placement_miss: bool = False
    migration_bytes: int = 0
    def receipt(self):
        return {**asdict(self),'read_amplification':self.bytes_read/self.bytes_requested if self.bytes_requested else None,
                'derived_write_amplification':None}
