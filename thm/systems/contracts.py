"""Versioned control contracts. Unknown observations stay absent; no tier mapping."""
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

SCHEMA = 'thm-systems/1'


def finite(value, name='value', minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError('invalid ' + name)
    return value


def integer(value, name='value', minimum=0, maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('invalid ' + name)
    return value


def nonempty(value):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > 4096:
        raise ValueError('bounded nonempty identity required')
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_json(path, value):
    """Publish serialized, immutable bytes from an owned temporary descriptor."""
    data = canonical(value) + b'\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.thm-publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if stream.write(data) != len(data):
                raise OSError('short publication')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return hashlib.sha256(data).hexdigest()


class EvidenceLevel(str, Enum):
    DOCUMENTED = 'documented'
    DISCOVERABLE = 'discoverable'
    FIXTURE = 'callable-fixture'
    NATIVE = 'native-executed'
    HARDWARE = 'hardware-observed'
    PERFORMANCE = 'performance-accepted'
    OUTCOME = 'task-outcome-accepted'


@dataclass(frozen=True)
class HotnessVector:
    demand_hotness: float = 0
    semantic_hotness: float = 0
    latency_sensitivity: float = 0
    residency_value: float = 0
    compute_reuse_value: float = 0
    thermal_pressure: float | None = None
    economic_value: float | None = None

    def __post_init__(self):
        for name, value in asdict(self).items():
            if value is not None:
                finite(value, name)


@dataclass(frozen=True)
class ProfileStamp:
    kind: str
    topology_epoch: int
    device_generation: int
    fingerprint: str
    created_at: float
    ttl: float

    def __post_init__(self):
        if self.kind not in ('provider', 'thermal', 'performance', 'topology', 'reliability', 'placement', 'benchmark', 'vector-shard'):
            raise ValueError('invalid profile kind')
        integer(self.topology_epoch)
        integer(self.device_generation)
        nonempty(self.fingerprint)
        finite(self.created_at)
        finite(self.ttl)

    def fresh(self, now, epoch, generation, fingerprint):
        finite(now)
        return (self.topology_epoch == epoch and self.device_generation == generation and
                self.fingerprint == fingerprint and self.created_at <= now < self.created_at + self.ttl)


@dataclass(frozen=True)
class PermissionGate:
    level: str = 'S0'
    capability: bool = False
    permission: bool = False
    opt_in: bool = False
    evidence_accepted: bool = False
    rollback_available: bool = False

    def __post_init__(self):
        if self.level not in ('S0', 'S1', 'S2'):
            raise ValueError('invalid authority level')
        if any(type(v) is not bool for k, v in asdict(self).items() if k != 'level'):
            raise ValueError('authority flags must be booleans')

    def require(self, level):
        if level == 'S0':
            return
        allowed = self.capability and self.permission and self.rollback_available
        if level == 'S1':
            allowed = allowed and self.level in ('S1', 'S2')
        elif level == 'S2':
            allowed = allowed and self.level == 'S2' and self.opt_in and self.evidence_accepted
        else:
            raise ValueError('unknown authority level')
        if not allowed:
            raise PermissionError(level + ' capability/permission/rollback gate rejected')
