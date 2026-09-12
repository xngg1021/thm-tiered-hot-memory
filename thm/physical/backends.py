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
from thm._bounded_files import bounded_file_bytes, validated_descriptor


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

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != 'lock'}

    def __setstate__(self, state):
        self.__dict__.update(state)
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
        self.root = Path(root).absolute()
        with validated_descriptor(self.root, directory=True) as (_, info):
            self.root_identity = (info.st_dev, info.st_ino)
        self._root_fd = None
        self.pending = {}

    def __getstate__(self):
        if self.pending:
            raise TypeError('active mounted transactions cannot be transferred')
        return {**self.__dict__, '_root_fd': None}

    def _root_descriptor(self):
        if self._root_fd is None:
            with validated_descriptor(self.root, directory=True) as (fd, info):
                if (info.st_dev, info.st_ino) != self.root_identity:
                    raise ValueError('configured mounted root identity changed')
                self._root_fd = os.dup(fd)
        return self._root_fd

    def _entry(self, path):
        fd = self._root_descriptor()
        return (Path(path).name, fd) if os.name == 'posix' else (self.root / Path(path).name, None)

    def _descriptor(self, path, *, directory=False):
        name, fd = self._entry(path)
        return validated_descriptor(name, directory=directory, dir_fd=fd)

    def _read_bounded(self, path, maximum):
        name, fd = self._entry(path)
        return bounded_file_bytes(name, maximum, dir_fd=fd)

    def _unlink(self, path):
        name, fd = self._entry(path)
        try:
            os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            pass

    def _remove_publication(self, path, expected=None):
        try:
            with self._descriptor(path, directory=True) as (fd, info):
                if expected is not None and (info.st_dev, info.st_ino) != expected:
                    raise ValueError('owned publication directory identity changed')
                try:
                    if os.name == 'posix':
                        os.unlink('payload', dir_fd=fd)
                    else:
                        (path / 'payload').unlink()
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            return
        name, fd = self._entry(path)
        os.rmdir(name, dir_fd=fd)

    def _path(self, key):
        check_sha(key)
        return self.root / (key + '.seg')

    def _pending_path(self, transaction):
        if len(transaction) != 32 or any(c not in '0123456789abcdef' for c in transaction):
            raise ValueError('owned transaction identity required')
        return self.root / ('.thm-' + transaction + '.pending')

    def stage(self, transaction, key, data):
        check_sha(key)
        path = self._pending_path(transaction)
        name, root_fd = self._entry(path)
        created = False
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
                         0o600, dir_fd=root_fd)
            created = True
            with os.fdopen(fd, 'wb') as f:
                if f.write(data) != len(data):
                    raise OSError('short storage stage write')
                f.flush()
                os.fsync(f.fileno())
            self.pending[transaction] = (path, key, len(data))
        except Exception:
            if created:
                self._unlink(path)
            raise

    def commit(self, transaction):
        path, key, maximum = self.pending[transaction]
        destination = self._path(key)
        # Read the untrusted mounted entry once, through its checked descriptor.
        # Only these bounded, checksum-validated bytes become publication input.
        data = self._read_bounded(path, maximum)
        if sha(data) != key:
            raise ValueError('staged content changed')
        publication = self.root / ('.thm-' + transaction + '.publication')
        name, root_fd = self._entry(publication)
        os.mkdir(name, mode=0o700, dir_fd=root_fd)
        publication_identity = None
        try:
            owned = publication / 'payload'
            with self._descriptor(publication, directory=True) as (directory_fd, info):
                publication_identity = (info.st_dev, info.st_ino)
                from ._atomic_publication import publish_bytes
                try:
                    publish_bytes(owned, data, destination, directory_fd, destination_fd=self._root_descriptor())
                except FileExistsError:
                    if sha(self._read_bounded(destination, maximum)) != key:
                        raise ValueError('existing object corrupt')
        finally:
            self._remove_publication(publication, publication_identity)
        self._unlink(path)
        del self.pending[transaction]

    def abort(self, transaction):
        value = self.pending.pop(transaction, None)
        self._unlink(value[0] if value else self._pending_path(transaction))
        publication = self.root / ('.thm-' + transaction + '.publication')
        self._remove_publication(publication)

    def read(self, key, offset, length):
        with self._descriptor(self._path(key)) as (fd, info):
            if offset + length > info.st_size:
                raise ValueError('short storage extent')
            os.lseek(fd, offset, os.SEEK_SET)
            chunks, remaining = [], length
            while remaining:
                block = os.read(fd, min(remaining, 1024 * 1024))
                if not block:
                    break
                chunks.append(block); remaining -= len(block)
            return b''.join(chunks)

    def size(self, key):
        with self._descriptor(self._path(key)) as (_, info):
            return info.st_size

    def close(self):
        try:
            for transaction in list(self.pending):
                self.abort(transaction)
        finally:
            if self._root_fd is not None:
                os.close(self._root_fd)
                self._root_fd = None

    def __del__(self):
        if getattr(self, '_root_fd', None) is not None:
            try:
                os.close(self._root_fd)
            except OSError:
                pass


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
    def __init__(self, config, transport, *, clock=time.monotonic):
        if not isinstance(config, BackendConfig):
            raise TypeError('BackendConfig required')
        for method in ('stage', 'commit', 'abort', 'read', 'size', 'close'):
            if not callable(transport) and not callable(getattr(transport, method, None)):
                raise TypeError('complete storage transport required')
        if not callable(transport) and getattr(transport, 'evidence', None) not in ('fixture-validated', 'environment-unvalidated'):
            raise ValueError('transport provenance required')
        from .transport_worker import TransportWorker
        self.config, self.transport, self.clock = config, transport, clock
        self.worker = TransportWorker(transport, config.max_object_bytes)
        self.lock, self.state = threading.RLock(), 'ready'
        self.journal = []
        self.bytes_read = self.bytes_written = self.bytes_requested = 0

    def _guard(self, generation):
        if self.state != 'ready' or generation != self.config.generation:
            raise ValueError('closed/quarantined/stale storage backend')

    def _call(self, method, *args, deadline):
        try:
            return self.worker.call(method, args, deadline)
        except TimeoutError:
            self.state = 'quarantined'
            raise

    def _deadline(self):
        return time.monotonic() + self.config.timeout_seconds

    def write(self, data, *, generation):
        with self.lock:
            self._guard(generation)
            if self.config.readonly:
                raise PermissionError('read-only backend')
            data = bytes(data)
            if not 0 < len(data) <= self.config.max_object_bytes:
                raise ValueError('storage object exceeds budget')
            key, transaction, start = sha(data), uuid.uuid4().hex, self.clock()
            deadline = self._deadline()
            row = {'transaction': transaction, 'object_sha256': key, 'state': 'staging'}
            self.journal.append(row)
            self.journal[:] = self.journal[-128:]
            try:
                self._call('stage', transaction, key, data, deadline=deadline)
                if self.clock()-start > self.config.timeout_seconds:
                    raise TimeoutError('storage stage deadline')
                # Publication can succeed even when its acknowledgement fails.
                # Abort only clears pending state; it cannot prove rollback.
                row['state'] = 'indeterminate-commit'
                # Also bound kernel exclusion lifetime below Darwin's lease
                # break interval. Unsupported protection fails before publish.
                commit_deadline = min(deadline, time.monotonic() + self.worker.commit_seconds) if self.worker.commit_seconds else deadline
                self._call('commit', transaction, deadline=commit_deadline)
                row['state'] = 'published-unverified'
                if not self.verify(key, _deadline=deadline):
                    raise ValueError('published content checksum mismatch')
                if self.clock()-start > self.config.timeout_seconds:
                    raise TimeoutError('storage commit deadline')
                row['state'] = 'verified'
                self.bytes_written += len(data)
                return key
            except Exception as exc:
                if isinstance(exc, TimeoutError):
                    row['state'] = 'indeterminate-timeout'
                try:
                    self._call('abort', transaction, deadline=time.monotonic() + min(1, self.config.timeout_seconds))
                except Exception as cleanup:
                    row['cleanup_error'] = type(cleanup).__name__
                    self.worker.stop()
                finally:
                    if self.state == 'quarantined':
                        self.worker.stop()
                row['error'] = type(exc).__name__
                if row['state'] == 'staging':
                    row['state'] = 'aborted'
                # A committed-but-unverified immutable object can be recovered;
                # no logical placement or source authority was published here.
                raise

    def _verified_data(self, key, deadline):
        check_sha(key)
        size = self._call('size', key, deadline=deadline)
        if type(size) is not int or not 0 < size <= self.config.max_object_bytes:
            raise ValueError('object exceeds verification budget')
        data = self._call('read', key, 0, size, deadline=deadline)
        self.bytes_read += len(data)
        if len(data) != size or sha(data) != key:
            raise ValueError('content verification failed')
        return data

    def verify(self, key, *, _deadline=None):
        with self.lock:
            self._guard(self.config.generation)
            try:
                self._verified_data(key, self._deadline() if _deadline is None else _deadline)
                return True
            except (ValueError, KeyError, FileNotFoundError):
                return False

    def read(self, extent, *, generation):
        with self.lock:
            self._guard(generation)
            if not isinstance(extent, TransferExtent):
                raise TypeError('TransferExtent required')
            check_sha(extent.object_sha256)
            start = self.clock()
            try:
                whole = self._verified_data(extent.object_sha256, self._deadline())
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
        with self.lock:
            self._guard(generation)
            if not self.verify(key):
                raise ValueError('recovery checksum mismatch')
            return {'object_sha256': key, 'verified': True, 'logical_placement_changed': False}

    def receipt(self):
        value = {'schema': 'thm-storage-backend/1', 'family': self.config.family,
                 'target_identity': identity(self.config.target_identity), 'generation': identity(self.config.generation),
                 'state': self.state, 'evidence': self.worker.evidence or getattr(self.transport, 'evidence', 'environment-unvalidated'), 'bytes_read': self.bytes_read,
                 'bytes_written': self.bytes_written, 'bytes_requested': self.bytes_requested, 'journal': list(self.journal),
                 'direct_dma': None, 'zero_copy': None, 'hardware_accepted': False,
                 'execution_boundary': 'owned-process-tree', 'timeout_enforcement': 'owned-process-tree', 'timeout_seconds': self.config.timeout_seconds,
                 'protected_mounted_commit_seconds': self.worker.commit_seconds,
                 'descendant_containment': self.worker.containment,
                 'logical_mutation': False, 'fallback': 'local-filesystem', 'durability': self.config.durability}
        return {**value, 'receipt_sha256': identity(value)}

    def close(self):
        with self.lock:
            try:
                if self.worker.process is not None:
                    self._call('close', deadline=time.monotonic() + min(1, self.config.timeout_seconds))
            finally:
                self.worker.stop()
                self.state = 'closed'


def backend_census():
    return [{'family': name, 'implementation': 'configured-transport-lifecycle',
             'fixture_entrypoint': 'thm.physical.backends:FixtureTransport',
             'hardware_evidence': 'environment-unvalidated'} for name in FAMILIES]
