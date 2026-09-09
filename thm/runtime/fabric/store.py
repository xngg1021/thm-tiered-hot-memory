"""Versioned local execution evidence. No query text, serial or model locator."""
from dataclasses import asdict, dataclass
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from .contracts import identity, finite


@dataclass(frozen=True)
class ProfileKey:
    hardware: str
    os_build: str
    driver: str
    provider_version: str
    model_source: str
    model_artifact: str
    dimension: int
    precision: str
    index_implementation: str
    corpus_bucket: str
    index_config: str
    placement: str
    workload: str
    semantic_policy: str
    semantic_implementation: str
    shape_bucket: str = 'default'

    def __post_init__(self):
        if self.workload not in ('interactive', 'bulk', 'background'):
            raise ValueError('invalid workload')
        if self.semantic_policy not in ('reference', 'auto-safe', 'auto-throughput', 'approximate-performance'):
            raise ValueError('invalid semantic policy')
        if type(self.dimension) is not int or self.dimension < 0:
            raise ValueError('invalid dimension')

    @property
    def id(self):
        return identity(asdict(self))

    def public(self):
        # Inputs may contain user-supplied identifiers; public values are hashes.
        return {k: v if k in ('dimension', 'workload', 'semantic_policy', 'precision') else identity(v)
                for k, v in asdict(self).items()}


def scale_bucket(count, dimension, memory_budget):
    """Allocation-relative octave bucket, not a permanent vector-count cutoff."""
    import math
    for value in (count, dimension, memory_budget):
        finite(value, 'scale')
    if not count:
        return 'empty'
    footprint = count * max(1, dimension) * 4
    return 'fit:' + str(math.floor(math.log2(max(footprint, 1) / max(memory_budget, 1))))


class ProfileStore:
    SCHEMA = 2

    def __init__(self, path, *, clock=time.time):
        path = Path(path)
        if path.is_symlink():
            raise ValueError('symlink profile store refused')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.path = path
        self.db = sqlite3.connect(path, timeout=5, check_same_thread=False)
        self.db.execute('PRAGMA busy_timeout=5000')
        import threading
        self.lock = threading.RLock()
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, self.SCHEMA):
            self.db.close()
            raise ValueError('unsupported profile schema')
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS observations (key TEXT, candidate TEXT, payload TEXT, checksum TEXT, first_seen REAL, validated REAL, PRIMARY KEY(key,candidate))')
            self.db.execute('CREATE TABLE IF NOT EXISTS quarantine (key TEXT, provider TEXT, failures INTEGER, until REAL, reason TEXT, PRIMARY KEY(key,provider))')
            self.db.execute('CREATE TABLE IF NOT EXISTS invalidated (key TEXT PRIMARY KEY)')
            self.db.execute('PRAGMA user_version=2')

    def put(self, key, candidate, measurement, *, semantic_status, material_gain, pareto=False):
        # Whitelist both fields and types; arbitrary provider stdout never persists.
        allowed = {'p50', 'p95', 'p99', 'throughput', 'cpu_seconds', 'gpu_seconds', 'ram', 'vram',
                   'transfer', 'io', 'startup', 'compile', 'energy', 'failure_probability',
                   'sample_count', 'noise', 'confidence', 'absolute_gain', 'relative_gain', 'conservative_gain'}
        if set(measurement) - allowed:
            raise ValueError('unrecognized measurement field')
        for name, value in measurement.items():
            if value is not None:
                finite(value, name)
        if semantic_status not in ('strict', 'reference', 'approximate', 'rejected'):
            raise ValueError('invalid semantic status')
        if material_gain not in ('accepted', 'retain-current', 'rejected'):
            raise ValueError('invalid material gain')
        payload = {'schema': self.SCHEMA, 'key': key.public(), 'candidate': identity(candidate),
                   'measurement': measurement, 'semantic_status': semantic_status,
                   'material_gain_status': material_gain, 'pareto': bool(pareto)}
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        now = self.clock()
        with self.lock, self.db:
            self.db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?) ON CONFLICT(key,candidate) DO UPDATE SET payload=excluded.payload,checksum=excluded.checksum,validated=excluded.validated',
                            (key.id, identity(candidate), encoded, identity(payload), now, now))

    def observations(self, key):
        with self.lock:
            if self.db.execute('SELECT 1 FROM invalidated WHERE key=?', (key.id,)).fetchone():
                return []
            rows = self.db.execute('SELECT payload,checksum,first_seen,validated FROM observations WHERE key=? ORDER BY candidate', (key.id,)).fetchall()
        result = []
        for raw, checksum, first, validated in rows:
            try:
                data = json.loads(raw)
                if identity(data) != checksum or data['key'] != key.public() or data['schema'] != self.SCHEMA:
                    continue
                result.append({**data, 'first_seen': first, 'last_validated': validated})
            except (ValueError, KeyError, TypeError):
                continue
        return result

    def invalidate(self, key):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO invalidated VALUES(?)', (key.id,))

    def failure(self, key, provider, reason, *, cooldown=60):
        if reason not in ('compile', 'oom', 'driver', 'timeout', 'semantic', 'unstable', 'execution'):
            reason = 'execution'
        finite(cooldown, 'cooldown')
        with self.lock, self.db:
            row = self.db.execute('SELECT failures FROM quarantine WHERE key=? AND provider=?', (key.id, identity(provider))).fetchone()
            n = (row[0] if row else 0) + 1
            until = self.clock() + min(3600, cooldown * 2 ** min(n - 1, 6))
            self.db.execute('INSERT OR REPLACE INTO quarantine VALUES(?,?,?,?,?)', (key.id, identity(provider), n, until, reason))

    def quarantined(self, key, provider):
        with self.lock:
            row = self.db.execute('SELECT until FROM quarantine WHERE key=? AND provider=?', (key.id, identity(provider))).fetchone()
        return bool(row and row[0] > self.clock())

    def summary(self):
        with self.lock:
            return {'schema': self.SCHEMA, 'observations': self.db.execute('SELECT count(*) FROM observations').fetchone()[0],
                    'quarantined': self.db.execute('SELECT count(*) FROM quarantine WHERE until>?', (self.clock(),)).fetchone()[0]}

    def close(self):
        with self.lock:
            self.db.close()


class CompiledArtifactStore:
    """Atomic immutable bytes keyed by every compiler/device/model dependency."""
    REQUIRED = {'model_source', 'transformation', 'provider_version', 'driver_runtime',
                'device_capability', 'precision', 'compiler_options'}

    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ValueError('symlink artifact root')
        self.root.mkdir(parents=True, exist_ok=True)

    def key(self, dependencies):
        if set(dependencies) != self.REQUIRED:
            raise ValueError('complete compiled artifact dependencies required')
        return identity(dependencies)

    def publish(self, dependencies, data):
        import hashlib
        key = self.key(dependencies)
        if not isinstance(data, bytes) or not data:
            raise ValueError('nonempty compiled bytes required')
        digest = hashlib.sha256(data).hexdigest()
        envelope = json.dumps({'key': key, 'sha256': digest, 'length': len(data)}).encode() + b'\n' + data
        fd, temp = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(envelope); out.flush(); os.fsync(out.fileno())
            target = self.root / (key + '.artifact')
            # Same dependency key must never silently replace different bytes.
            if target.exists():
                if self.load(dependencies) != data:
                    raise ValueError('compiled artifact identity conflict')
            else:
                try:
                    os.link(temp, target)
                except FileExistsError:
                    if self.load(dependencies) != data:
                        raise ValueError('compiled artifact publish conflict')
            return key
        finally:
            os.unlink(temp)

    def load(self, dependencies):
        import hashlib
        key = self.key(dependencies)
        path = self.root / (key + '.artifact')
        if path.is_symlink():
            raise ValueError('symlink artifact refused')
        try:
            with path.open('rb') as stream:
                header = json.loads(stream.readline(4096)); data = stream.read()
            if header != {'key': key, 'sha256': hashlib.sha256(data).hexdigest(), 'length': len(data)}:
                raise ValueError('compiled artifact checksum mismatch')
            return data
        except FileNotFoundError:
            return None


def map_legacy_profile(profile):
    """Read existing RuntimeProfile without changing its identity or freshness key."""
    from ..profiles import from_dict
    value = from_dict(profile) if isinstance(profile, dict) else profile
    return {'legacy_id': value.id, 'fingerprint': value.fingerprint,
            'candidate': value.identity(), 'source': 'manual',
            'material_gain_status': 'retain-current', 'automatic_promotion': False}
