"""Content-addressed storage transports and explicit specialized backend sessions.

Mounted SMB/NFS/parallel filesystems use the filesystem transport. Native storage
fabrics use an explicitly supplied transport implementing the same transactional
contract. Fixture transports are always identified as simulations in receipts.
"""
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import threading
import time
import uuid

from thm.runtime.fabric.contracts import identity
from .adapters import EXTENSIONS
from .contracts import TransferExtent


FAMILIES = tuple(dict.fromkeys((*EXTENSIONS, 'sata', 'sas', 'stacked-block', 'storage-spaces',
                               'raid', 'pinned-host', 'staging', 'direct-io', 'async-io')))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('content SHA256 required')


@dataclass(frozen=True)
class BackendConfig:
    family: str
    target_identity: str
    generation: str
    max_object_bytes: int = 64 * 1024 * 1024
    readonly: bool = False
    durability: str = 'unknown'
    driver_identity: str = 'unknown'
    timeout_seconds: float = 30

    def __post_init__(self):
        import math
        if self.family not in FAMILIES or not self.target_identity or not self.generation:
            raise ValueError('registered family/target/generation required')
        if type(self.max_object_bytes) is not int or not 1 <= self.max_object_bytes <= 2**30:
            raise ValueError('bounded object size required')
        if type(self.readonly) is not bool or type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 300:
            raise ValueError('invalid storage limits')


class FixtureTransport:
    """Real state machine in memory; injected faults exercise failure/recovery."""
    evidence = 'fixture-validated'
    def __init__(self):
        self.objects, self.pending = {}, {}
        self.fail_at = None
        self.lock = threading.RLock()

    def _fault(self, stage):
        if self.fail_at == stage:
            raise OSError('injected ' + stage)

    def stage(self, transaction, key, data):
        with self.lock:
            self._fault('stage')
            self.pending[transaction] = (key, bytes(data))

    def commit(self, transaction):
        with self.lock:
            self._fault('commit')
            key, data = self.pending[transaction]
            if key in self.objects and self.objects[key] != data:
                raise ValueError('immutable object collision')
            self.objects[key] = data
            del self.pending[transaction]

    def abort(self, transaction):
        with self.lock:
            self.pending.pop(transaction, None)

    def read(self, key, offset, length):
        self._fault('read')
        return self.objects[key][offset:offset+length]

    def size(self, key):
        return len(self.objects[key])

    def close(self):
        self.pending.clear()


class MountedFilesystemTransport:
    """Atomic local/mounted publication; durability depends on the mounted service."""
    evidence = 'environment-unvalidated'
    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError('existing non-symlink mounted root required')
        self.pending = {}

    def _path(self, key):
        check_sha(key)
        path = self.root / (key + '.seg')
        if path.is_symlink():
            raise ValueError('symlink object refused')
        return path

    def stage(self, transaction, key, data):
        check_sha(key)
        path = self.root / ('.thm-' + uuid.uuid4().hex + '.pending')
        try:
            with path.open('xb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            self.pending[transaction] = (path, key)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def commit(self, transaction):
        path, key = self.pending[transaction]
        destination = self._path(key)
        if sha(path.read_bytes()) != key:
            raise ValueError('staged content changed')
        try:
            os.link(path, destination)  # create-only publication; no overwrite race
        except FileExistsError:
            if sha(destination.read_bytes()) != key:
                raise ValueError('existing object corrupt')
        path.unlink()
        del self.pending[transaction]

    def abort(self, transaction):
        value = self.pending.pop(transaction, None)
        if value:
            value[0].unlink(missing_ok=True)

    def read(self, key, offset, length):
        with self._path(key).open('rb') as f:
            f.seek(offset)
            return f.read(length)

    def size(self, key):
        return self._path(key).stat().st_size

    def close(self):
        for transaction in list(self.pending):
            self.abort(transaction)


class S3Transport:
    """An explicit preconfigured S3 client; no credentials, client creation or install."""
    evidence = 'environment-unvalidated'
    def __init__(self, client, bucket, prefix='thm/'):
        if not bucket or prefix.startswith('/') or '..' in prefix.split('/'):
            raise ValueError('invalid S3 destination')
        self.client, self.bucket, self.prefix, self.pending = client, bucket, prefix, {}
        self.evidence = 'fixture-validated' if getattr(client, 'evidence', None) == 'fixture-validated' else 'environment-unvalidated'

    def _key(self, key):
        check_sha(key)
        return self.prefix + key + '.seg'

    def stage(self, transaction, key, data):
        self.pending[transaction] = (key, bytes(data))

    def commit(self, transaction):
        key, data = self.pending[transaction]
        # Content-addressed, create-only object. Conditional conflict is propagated;
        # callers can verify/reuse an existing object separately.
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, IfNoneMatch='*',
                               Metadata={'sha256': key})
        del self.pending[transaction]

    def abort(self, transaction):
        self.pending.pop(transaction, None)

    def read(self, key, offset, length):
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key),
                                         Range=f'bytes={offset}-{offset+length-1}')
        body = response['Body']
        try:
            return body.read(length+1)
        finally:
            body.close()

    def size(self, key):
        return self.client.head_object(Bucket=self.bucket, Key=self._key(key))['ContentLength']

    def close(self):
        self.pending.clear()  # supplied client remains caller-owned


class StorageBackend:
    def __init__(self, config, transport, *, clock=time.monotonic, _worker=False):
        if not isinstance(config, BackendConfig):
            raise TypeError('BackendConfig required')
        for method in ('stage', 'commit', 'abort', 'read', 'size', 'close'):
            if not callable(transport) and not callable(getattr(transport, method, None)):
                raise TypeError('complete storage transport required')
        if not callable(transport) and getattr(transport, 'evidence', None) not in ('fixture-validated', 'environment-unvalidated'):
            raise ValueError('transport provenance required')
        self.config, self.transport, self.clock = config, transport, clock
        self.lock, self.state = threading.RLock(), 'ready'
        self.journal = []
        self.bytes_read = self.bytes_written = self.bytes_requested = 0
        self._remote = None
        # The built-in deterministic in-memory fixture has no external callbacks.
        # Every other transport runs behind an owned process deadline.
        if not _worker and type(transport) is not FixtureTransport:
            from .backend_worker import BackendWorker
            self._remote = BackendWorker(config, transport)

    def _remote_call(self, operation, *args, **kwargs):
        with self.lock:
            try:
                return self._remote.call(operation, *args, **kwargs)
            except TimeoutError:
                self.state = 'quarantined'
                raise
            finally:
                receipt = self._remote.receipt
                if not self._remote.closed:self.state = receipt.get('state', self.state)
                self.bytes_read = receipt.get('bytes_read', self.bytes_read)
                self.bytes_written = receipt.get('bytes_written', self.bytes_written)
                self.bytes_requested = receipt.get('bytes_requested', self.bytes_requested)
                self.journal = receipt.get('journal', self.journal)

    def _guard(self, generation):
        if self.state != 'ready' or generation != self.config.generation:
            raise ValueError('closed/quarantined/stale storage backend')

    def write(self, data, *, generation):
        if self._remote is not None:
            self._guard(generation)
            if self.config.readonly:raise PermissionError('read-only backend')
            if not 0 < len(data) <= self.config.max_object_bytes:raise ValueError('storage object exceeds budget')
            return self._remote_call('write', bytes(data), generation=generation)
        with self.lock:
            self._guard(generation)
            if self.config.readonly:
                raise PermissionError('read-only backend')
            data = bytes(data)
            if not 0 < len(data) <= self.config.max_object_bytes:
                raise ValueError('storage object exceeds budget')
            key, transaction, start = sha(data), uuid.uuid4().hex, self.clock()
            row = {'transaction': transaction, 'object_sha256': key, 'state': 'staging'}
            self.journal.append(row)
            self.journal[:] = self.journal[-128:]
            try:
                self.transport.stage(transaction, key, data)
                if self.clock()-start > self.config.timeout_seconds:
                    raise TimeoutError('storage stage deadline')
                row['state'] = 'commit-requested'
                self.transport.commit(transaction)
                row['state'] = 'published-unverified'
                if not self.verify(key):
                    raise ValueError('published content checksum mismatch')
                if self.clock()-start > self.config.timeout_seconds:
                    raise TimeoutError('storage commit deadline')
                row['state'] = 'verified'
                self.bytes_written += len(data)
                return key
            except Exception as exc:
                try:
                    self.transport.abort(transaction)
                except Exception:
                    row['cleanup_failed'] = True
                row['error'] = type(exc).__name__
                if row['state'] == 'staging' or type(self.transport) is FixtureTransport:
                    row['state'] = 'aborted'
                elif row['state'] == 'commit-requested':
                    row['state'] = 'publication-unknown'
                # A committed-but-unverified immutable object can be recovered;
                # no logical placement or source authority was published here.
                raise

    def _verified_data(self, key):
        check_sha(key)
        size = self.transport.size(key)
        if type(size) is not int or not 0 < size <= self.config.max_object_bytes:
            raise ValueError('object exceeds verification budget')
        data = self.transport.read(key, 0, size)
        self.bytes_read += len(data)
        if len(data) != size or sha(data) != key:
            raise ValueError('content verification failed')
        return data

    def verify(self, key):
        if self._remote is not None:
            return self._remote_call('verify', key)
        try:
            self._verified_data(key)
            return True
        except (ValueError, KeyError, FileNotFoundError):
            return False

    def read(self, extent, *, generation):
        if self._remote is not None:
            self._guard(generation)
            if not isinstance(extent, TransferExtent):raise TypeError('TransferExtent required')
            return self._remote_call('read', asdict(extent), generation=generation)
        with self.lock:
            self._guard(generation)
            if not isinstance(extent, TransferExtent):
                raise TypeError('TransferExtent required')
            check_sha(extent.object_sha256)
            start = self.clock()
            try:
                whole = self._verified_data(extent.object_sha256)
            except ValueError:
                self.state = 'quarantined'
                raise ValueError('corrupt storage object')
            if extent.offset + extent.length > len(whole):
                raise ValueError('transfer exceeds object')
            data = whole[extent.offset:extent.offset+extent.length]
            if len(data) != extent.length:
                raise ValueError('short storage read')
            if self.clock()-start > self.config.timeout_seconds:
                raise TimeoutError('storage read deadline')
            self.bytes_requested += extent.length
            return data

    def recover(self, key, *, generation):
        if self._remote is not None:
            self._guard(generation)
            return self._remote_call('recover', key, generation=generation)
        with self.lock:
            self._guard(generation)
            if not self.verify(key):
                raise ValueError('recovery checksum mismatch')
            return {'object_sha256': key, 'verified': True, 'logical_placement_changed': False}

    def receipt(self):
        if self._remote is not None:
            value = {k:v for k,v in self._remote.receipt.items() if k != 'receipt_sha256'}
            value.update(state=self.state, timeout_enforcement='owned-process-tree')
            return {**value, 'receipt_sha256':identity(value)}
        value = {'schema': 'thm-storage-backend/1', 'family': self.config.family,
                 'target_identity': identity(self.config.target_identity), 'generation': identity(self.config.generation),
                 'state': self.state, 'evidence': self.transport.evidence, 'bytes_read': self.bytes_read,
                 'bytes_written': self.bytes_written, 'bytes_requested': self.bytes_requested, 'journal': list(self.journal),
                 'direct_dma': None, 'zero_copy': None, 'hardware_accepted': False,
                 'logical_mutation': False, 'fallback': 'local-filesystem', 'durability': self.config.durability}
        return {**value, 'receipt_sha256': identity(value)}

    def close(self):
        with self.lock:
            try:
                if self._remote is not None:self._remote.close()
                else:self.transport.close()
            finally:
                self.state = 'closed'


def backend_census():
    return [{'family': name, 'implementation': 'configured-transport-lifecycle',
             'fixture_entrypoint': 'thm.physical.backends:FixtureTransport',
             'hardware_evidence': 'environment-unvalidated'} for name in FAMILIES]
