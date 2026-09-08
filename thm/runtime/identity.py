"""Versioned, local-content identities; no model IDs masquerading as weight hashes."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def bounded_int(value, name, maximum=4096):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{name} must be an integer from 1 to {maximum}')
    return value


def manifest(root):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('existing nonsymlink local model directory required')
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink model content refused')
        if path.is_file() and path.name != 'thm-preparation.json':
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    h.update(chunk)
            files.append({'name': path.relative_to(root).as_posix(), 'sha256': h.hexdigest(), 'bytes': path.stat().st_size})
    if not files:
        raise ValueError('empty local model')
    return {'sha256': digest(files), 'files': files}


def implementation_identity():
    root = Path(__file__).resolve().parents[1]
    return digest({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob('*.py'))})


@dataclass(frozen=True)
class EmbeddingProfile:
    source_manifest_sha256: str
    backend: str
    backend_version: str
    precision: str
    dimension: int
    device: str = 'cpu'
    normalization: str = 'l2-finite-nonzero-v1'
    transformation: str = 'none'
    derived_manifest_sha256: str | None = None
    encoder_input: str = 'speaker-colon-space-text-v1;query-verbatim-v1'
    schema: int = 1

    def __post_init__(self):
        bounded_int(self.dimension, 'dimension', 65536)
        if not isinstance(self.source_manifest_sha256,str):raise ValueError('source manifest SHA256 required')
        for value in (self.source_manifest_sha256, self.derived_manifest_sha256):
            if value is not None and (not isinstance(value,str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
                raise ValueError('invalid manifest SHA256')
        if self.normalization != 'l2-finite-nonzero-v1' or self.precision not in ('fp32', 'int8', 'bf16', 'fp16'):
            raise ValueError('unsupported embedding contract')
        if not self.backend or not self.backend_version or not self.device:
            raise ValueError('incomplete backend identity')

    @property
    def id(self):
        return 'ep1-' + digest(asdict(self))

    def identity(self):
        return {**asdict(self), 'embedding_profile_id': self.id}


def validate_vectors(vectors, profile, expected):
    if len(vectors) != expected:
        raise ValueError('embedding count mismatch')
    for vector in vectors:
        if len(vector) != profile.dimension or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ValueError('invalid vector dimension or finite values')
        norm = math.sqrt(sum(v*v for v in vector))
        if abs(norm - 1) > 1e-4:
            raise ValueError('normalized vector contract violated')
    return vectors
