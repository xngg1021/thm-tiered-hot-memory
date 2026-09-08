"""Hardware/runtime fingerprint freshness and explicit session policies."""
from dataclasses import asdict, dataclass
from .identity import digest, bounded_int, implementation_identity
from .hardware import versions

POLICIES=('reference','auto-safe','auto-throughput','approximate-performance')
WORKLOADS=('interactive','bulk','background')


def fingerprint(hardware,source_sha,derived_sha=None,embedding_profile=None):
    h=hardware.identity() if hasattr(hardware,'identity') else dict(hardware)
    h.pop('ram_available',None)
    return digest({'hardware':h,'backend_versions':versions(),'source_model':source_sha,
                   'derived_model':derived_sha,'embedding_profile':embedding_profile,
                   'retrieval_implementation':implementation_identity()})


@dataclass(frozen=True)
class RuntimeProfile:
    embedding_profile_id: str
    fingerprint: str
    backend: str = 'torch_fp32'
    device: str = 'cpu'
    precision: str = 'fp32'
    threads: int = 1
    document_batch_size: int = 64
    query_batch_size: int = 1
    scorer: str = 'numpy_reference'
    policy: str = 'reference'
    workload: str = 'interactive'
    affinity: tuple = ()
    semantic_gate: str = 'unvalidated'
    overlap: bool = False
    schema: int = 1

    def __post_init__(self):
        for value,name,limit in ((self.threads,'threads',256),(self.document_batch_size,'document batch',256),(self.query_batch_size,'query batch',256)):
            bounded_int(value,name,limit)
        if self.policy not in POLICIES or self.workload not in WORKLOADS:raise ValueError('unsupported runtime policy/workload')
        if self.precision!='fp32' and self.policy!='approximate-performance':raise ValueError('approximate precision requires explicit policy')
        if self.policy in ('auto-safe','reference') and self.semantic_gate not in ('strict','reference'):
            raise ValueError('safe profile requires strict calibration')
        if self.policy=='reference' and (self.overlap or self.query_batch_size!=1):raise ValueError('reference is sequential and fixed')
        if any(type(cpu) is not int or cpu<0 for cpu in self.affinity):raise ValueError('invalid affinity')

    @property
    def id(self):return 'rp1-'+digest(asdict(self))
    def identity(self):return {**asdict(self),'runtime_profile_id':self.id}
    def require_fresh(self,current):
        if current!=self.fingerprint:raise ValueError('runtime profile stale; explicitly recalibrate')


def from_dict(data):
    data=dict(data);recorded=data.pop('runtime_profile_id',None);data['affinity']=tuple(data.get('affinity',()))
    p=RuntimeProfile(**data)
    if recorded is not None and p.id!=recorded:raise ValueError('runtime profile identity mismatch')
    return p


def load_profile(path):
    import json
    from pathlib import Path
    path=Path(path)
    if Path(str(path)+'.invalidated').exists():raise ValueError('runtime profile explicitly invalidated')
    data=json.loads(path.read_text())
    return from_dict(data.get('runtime_profile',data))
