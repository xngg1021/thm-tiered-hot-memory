"""Regression evidence for the final publication, descriptor and callback fixes."""
from contextlib import contextmanager, ExitStack
from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from thm.evaluation.memory import AgentMemory
from thm.evaluation.environment import EnvironmentIdentity, EnvironmentRunner
from thm.evaluation.contracts import Task
from thm.evaluation.fixtures import DeterministicEnvironment, deterministic_environment_policy
from thm._bounded_files import bounded_file_bytes, validated_descriptor
from thm.physical.backends import BackendConfig, FixtureTransport, MountedFilesystemTransport, S3Transport, StorageBackend
from thm.physical.contracts import TransferExtent
from thm.runtime.fabric.extensions import ExtensionConfig, ExtensionSession, FunctionBinding, bounded_artifact_digest


class BlockingTransport(FixtureTransport):
    def __init__(self, hang, marker=None):
        super().__init__()
        self.hang, self.marker = hang, marker
        self.objects[hashlib.sha256(b'abc').hexdigest()] = b'abc'

    def pause(self, stage):
        if self.hang == stage:
            if self.marker:
                helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
                Path(self.marker).write_text(str(helper.pid))
            while True:
                time.sleep(.05)

    def stage(self, *args):
        self.pause('stage'); return super().stage(*args)

    def commit(self, *args):
        self.pause('commit')
        if self.hang == 'abort':
            raise OSError('commit failed')
        return super().commit(*args)

    def size(self, *args):
        self.pause('size'); return super().size(*args)

    def read(self, *args):
        self.pause('read'); return super().read(*args)

    def abort(self, *args):
        self.pause('abort'); return super().abort(*args)

    def close(self):
        self.pause('close'); return super().close()


class HangingMountedStage(MountedFilesystemTransport):
    def stage(self, *args):
        super().stage(*args)
        while True:
            time.sleep(.05)


def attempt_detached_helper(marker):
    helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'], start_new_session=True)
    try:
        Path(marker).write_text(str(helper.pid))
    finally:
        helper.terminate(); helper.wait(timeout=3)


class DetachedEnvironment(DeterministicEnvironment):
    def reset(self, task_id):
        attempt_detached_helper(self.marker)
        return super().reset(task_id)


class DetachedTransport(FixtureTransport):
    def __init__(self, marker):
        super().__init__(); self.marker = marker

    def stage(self, *args):
        attempt_detached_helper(self.marker)
        return super().stage(*args)


class LostMountedAcknowledgement(MountedFilesystemTransport):
    def commit(self, transaction):
        super().commit(transaction)
        raise OSError('publication acknowledgement lost')


class AttackedMountedPublication(MountedFilesystemTransport):
    def commit(self, transaction):
        from thm.physical import _atomic_publication as publication
        publish = publication._publish_fd
        def attack(fd, destination, directory_fd, **kwargs):
            # A real same-credential process targets the review's discoverable
            # private payload. Kernel lease conflict must stop publication.
            path = str(self.root / ('.thm-' + transaction + '.publication') / 'payload')
            subprocess.run([sys.executable, '-c',
                'import os,sys; fd=os.open(sys.argv[1],os.O_WRONLY|os.O_NONBLOCK); os.write(fd,b"bad")',
                path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            return publish(fd, destination, directory_fd, **kwargs)
        with mock.patch.object(publication, '_publish_fd', attack):
            return super().commit(transaction)


class FakeS3Client:
    def __init__(self):
        self.objects = {}

    def put_object(self, **kw):
        if kw['IfNoneMatch'] != '*':
            raise ValueError('missing create-only condition')
        self.objects[kw['Key']] = kw['Body']

    def get_object(self, **kw):
        a, b = map(int, kw['Range'][6:].split('-'))
        return {'Body': io.BytesIO(self.objects[kw['Key']][a:b+1])}

    def head_object(self, **kw):
        return {'ContentLength': len(self.objects[kw['Key']])}


class LostS3Acknowledgement(FakeS3Client):
    def put_object(self, **kw):
        super().put_object(**kw)
        raise OSError('PUT acknowledgement lost')


class MountedPublicationTests(unittest.TestCase):
    def test_replaced_root_is_rejected_before_first_operation_and_worker_transfer(self):
        import pickle
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            root = Path(tmp)/'root'; root.mkdir()
            transport = MountedFilesystemTransport(root); cleanup.callback(transport.close)
            transferred = pickle.loads(pickle.dumps(transport)); cleanup.callback(transferred.close)
            root.rename(Path(tmp)/'original'); root.mkdir()
            for candidate in (transport, transferred):
                with self.assertRaisesRegex(ValueError, 'root identity changed'):
                    candidate.stage('a'*32, hashlib.sha256(b'abc').hexdigest(), b'abc')
            self.assertEqual(list(root.iterdir()), [])

    def test_open_root_identity_survives_rename_or_windows_denies_it(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            root = Path(tmp)/'root'; root.mkdir(); moved = Path(tmp)/'original'
            transport = MountedFilesystemTransport(root); cleanup.callback(transport.close)
            data = b'abc'; key = hashlib.sha256(data).hexdigest(); transaction = 'e'*32
            transport.stage(transaction, key, data)
            if os.name == 'nt':
                with self.assertRaises(OSError): root.rename(moved)
                actual = root
            else:
                root.rename(moved); root.mkdir(); actual = moved
            if sys.platform == 'darwin':
                with self.assertRaises(OSError): transport.commit(transaction)
                transport.abort(transaction)
                (actual/(key+'.seg')).write_bytes(data)
            else:
                transport.commit(transaction)
            self.assertEqual(transport.size(key), len(data))
            self.assertEqual(transport.read(key, 0, len(data)), data)
            self.assertEqual((actual/(key+'.seg')).read_bytes(), data)
            if os.name == 'posix': self.assertEqual(list(root.iterdir()), [])

    def test_pending_growth_and_substitution_are_bounded_before_publication(self):
        for kind in ('growth', 'symlink', 'fifo'):
            if kind == 'fifo' and not hasattr(os, 'mkfifo'):
                continue
            if kind == 'symlink' and os.name == 'nt':
                continue
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
                transport=MountedFilesystemTransport(tmp);cleanup.callback(transport.close);transaction='a'*32
                data=b'abc';key=hashlib.sha256(data).hexdigest()
                transport.stage(transaction,key,data)
                path=transport.pending[transaction][0]
                if kind=='growth':path.write_bytes(b'x'*4096)
                else:
                    path.unlink()
                    if kind=='fifo':os.mkfifo(path)
                    else:
                        target=Path(tmp)/'foreign';target.write_bytes(data);path.symlink_to(target)
                with mock.patch('thm.physical.backends.os.link', side_effect=AssertionError('must reject before publishing')):
                    with self.assertRaises((ValueError,OSError)):
                        transport.commit(transaction)
                self.assertFalse((Path(tmp)/(key+'.seg')).exists())
                transport.abort(transaction)

    def test_only_frozen_private_inode_is_linked_and_existing_reads_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            transport=MountedFilesystemTransport(tmp);cleanup.callback(transport.close);transaction='b'*32
            data=b'original';key=hashlib.sha256(data).hexdigest()
            transport.stage(transaction,key,data);pending=transport.pending[transaction][0]
            if sys.platform == 'darwin':
                with self.assertRaises(OSError):transport.commit(transaction)
                self.assertFalse((Path(tmp)/(key+'.seg')).exists())
                transport.abort(transaction)
                return
            link=os.link
            def replace_original(source,destination,**kwargs):
                self.assertNotEqual(Path(source),pending)
                pending.write_bytes(b'replaced original while publishing')
                inode=os.stat(source,dir_fd=kwargs.get('src_dir_fd')).st_ino
                link(source,destination,**kwargs)
                self.assertEqual(os.stat(destination,dir_fd=kwargs.get('dst_dir_fd')).st_ino,inode)
            with mock.patch('thm.physical.backends.os.link',replace_original):
                transport.commit(transaction)
            destination=Path(tmp)/(key+'.seg')
            self.assertEqual(destination.read_bytes(),data)
            self.assertEqual(list(Path(tmp).iterdir()),[destination])
            transport.stage(transaction,key,data);destination.write_bytes(b'x'*4096)
            with self.assertRaises(ValueError):transport.commit(transaction)
            transport.abort(transaction)
            self.assertEqual(list(Path(tmp).iterdir()),[destination])

    @unittest.skipUnless(os.name == 'posix', 'POSIX kernel lease capability gate')
    def test_missing_kernel_protection_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            transport=MountedFilesystemTransport(tmp);cleanup.callback(transport.close);transaction='c'*32
            key=hashlib.sha256(b'abc').hexdigest();transport.stage(transaction,key,b'abc')
            with mock.patch('fcntl.fcntl',side_effect=OSError('lease unavailable')):
                with self.assertRaisesRegex(OSError,'kernel-protected'):
                    transport.commit(transaction)
            self.assertFalse((Path(tmp)/(key+'.seg')).exists())
            transport.abort(transaction);self.assertFalse(any(Path(tmp).iterdir()))

    @unittest.skipUnless(os.name == 'nt', 'Windows mandatory share denial')
    def test_windows_payload_stays_write_protected_until_handle_rename(self):
        from thm.physical import _atomic_publication as publication
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            transport=MountedFilesystemTransport(tmp);cleanup.callback(transport.close);transaction='d'*32
            data=b'abc';key=hashlib.sha256(data).hexdigest();transport.stage(transaction,key,data)
            publish=publication._publish_fd
            def attack(fd,destination,directory_fd,**kwargs):
                path=Path(tmp)/('.thm-'+transaction+'.publication')/'payload'
                with self.assertRaises(OSError):
                    with path.open('wb') as writer:writer.write(b'bad')
                return publish(fd,destination,directory_fd,**kwargs)
            with mock.patch.object(publication,'_publish_fd',attack):transport.commit(transaction)
            self.assertEqual((Path(tmp)/(key+'.seg')).read_bytes(),data)


def s3_factory():
    return S3Transport(FakeS3Client(), 'fixture')


s3_factory.evidence = 'fixture-validated'


class FailingEnvironment(DeterministicEnvironment):
    def _delay(self, stage):
        if self.delay_stage == stage:
            raise OSError('environment failure')

    def close(self):
        if self.marker:
            Path(self.marker).write_text('closed')
        super().close()


def failing_policy(*args):
    raise ValueError('policy failure')


class EnvironmentFailureTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'POSIX session escape prevention')
    def test_environment_cannot_launch_a_detached_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp)/'escaped'
            runner = EnvironmentRunner(DetachedEnvironment(marker=str(marker)),
                EnvironmentIdentity('fixture','fixture','a'*64), wall_seconds=3)
            with self.assertRaisesRegex(RuntimeError, 'PermissionError'):
                runner.run(Task('a','scope','query',()), deterministic_environment_policy)
            self.assertFalse(marker.exists())

    def test_callback_exceptions_and_close_failure_never_publish_success(self):
        for stage in ('reset','policy','step','close'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                marker=Path(tmp)/'closed'
                runner=EnvironmentRunner(FailingEnvironment(stage,str(marker)),
                    EnvironmentIdentity('fixture','fixture','a'*64),wall_seconds=3)
                with self.assertRaises(RuntimeError):
                    runner.run(Task('a','s','q',()),failing_policy if stage=='policy' else deterministic_environment_policy)
                self.assertEqual(marker.read_text(),'closed')

    def test_environment_expired_launch_never_runs_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'reset'
            runner=EnvironmentRunner(DeterministicEnvironment('reset',str(marker)),
                EnvironmentIdentity('fixture','fixture','a'*64),wall_seconds=.00000001)
            with self.assertRaises(TimeoutError):
                runner.run(Task('a','s','q',()),deterministic_environment_policy)
            self.assertFalse(marker.exists())


class SnapshotDescriptorTests(unittest.TestCase):
    def test_short_write_exception_and_publication_failure_are_retryable(self):
        for failure in ('short', 'write-error', 'publish-error'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); memory = AgentMemory(root/'index.db', 's')
                self.addCleanup(memory.close); memory.add('保存完整的字节')
                real_fdopen = os.fdopen
                @contextmanager
                def injected(fd, mode):
                    with real_fdopen(fd, mode) as handle:
                        proxy = mock.Mock(wraps=handle)
                        def write(data):
                            handle.write(data[:5])
                            if failure == 'write-error':
                                raise OSError('disk full')
                            return 5
                        proxy.write = write
                        yield proxy
                patch = (mock.patch('os.link', side_effect=OSError('publication failed')) if failure == 'publish-error'
                         else mock.patch('os.fdopen', side_effect=injected))
                with patch, self.assertRaises(OSError):
                    memory.save(root/'snapshot')
                self.assertEqual(list((root/'snapshot').iterdir()), [])
                memory.save(root/'snapshot')
                other = AgentMemory(root/'other.db', 's'); self.addCleanup(other.close)
                other.restore(root/'snapshot'); self.assertEqual(other.documents, memory.documents)

    def test_opened_snapshot_size_and_growth_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'snapshot'; path.write_bytes(b'abc')
            real_read = os.read
            def grow(fd, length):
                with path.open('ab') as out:
                    out.write(b'x'*20)
                return real_read(fd, length)
            with mock.patch('os.read', side_effect=grow), self.assertRaises(ValueError):
                bounded_file_bytes(path, 10)
            with self.assertRaises(ValueError):
                bounded_file_bytes(path, 10)

    @unittest.skipUnless(os.name == 'posix', 'POSIX FIFO/no-follow replacement')
    def test_snapshot_symlink_and_fifo_substitution_never_read(self):
        for kind in ('symlink', 'fifo'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'snapshot'; path.write_bytes(b'abc')
                target = Path(tmp)/'target'; target.write_bytes(b'x'*100)
                real_open = os.open
                def swap(name, flags, **kw):
                    if Path(name) == path:
                        path.unlink()
                        if kind == 'symlink': path.symlink_to(target)
                        else: os.mkfifo(path)
                    return real_open(name, flags, **kw)
                start = time.monotonic()
                with mock.patch('os.open', side_effect=swap), self.assertRaises((OSError, ValueError)):
                    bounded_file_bytes(path, 10)
                self.assertLess(time.monotonic()-start, 1)

    def test_nonregular_descriptors_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((OSError, ValueError)):
                bounded_file_bytes(Path(tmp), 10)


class ArtifactDescriptorTests(unittest.TestCase):
    def test_siblings_freeze_and_receipt_matches_consumed_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'model').write_bytes(b'model')
            (root/'weights').write_bytes(b'weights')
            source_hash = bounded_artifact_digest(root, 12)
            cfg = ExtensionConfig('fixture', 'g', source_hash, 'sdk', '1', 'cpu', max_input_bytes=12)
            binding = FunctionBinding(operations=('inference',), prepare=lambda p,c:p,
                compile=lambda p,c:p, load=lambda p,c:p,
                execute=lambda p,o,x:(p/'model').read_bytes()+(p/'weights').read_bytes(), close=lambda:None)
            session = ExtensionSession(cfg, binding); self.addCleanup(session.close)
            frozen = session.prepare(root)
            (root/'model').unlink(); (root/'model').write_bytes(b'replaced and grown')
            (root/'weights').write_bytes(b'changed sibling')
            session.compile(); session.load()
            self.assertEqual(session.execute('inference', b'', generation='g'), b'modelweights')
            self.assertEqual(session.receipt()['config']['source_sha256'], bounded_artifact_digest(frozen, 12))
            session.close(); self.assertFalse(frozen.exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX stat/open substitution')
    def test_artifact_swap_to_fifo_symlink_or_regular_rejected(self):
        for kind in ('fifo', 'symlink', 'regular'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root/'model'; path.write_bytes(b'abc')
                expected = bounded_artifact_digest(path, 3)
                cfg = ExtensionConfig('fixture', 'g', expected, 'sdk', '1', 'cpu', max_input_bytes=3)
                binding = mock.Mock()
                session = ExtensionSession(cfg, binding)
                real_open = os.open
                def swap(name, flags, **kw):
                    if name == 'model':
                        path.unlink()
                        if kind == 'fifo': os.mkfifo(path)
                        elif kind == 'symlink': path.symlink_to('/dev/zero')
                        else: path.write_bytes(b'xyz')
                    return real_open(name, flags, **kw)
                start = time.monotonic()
                with mock.patch('os.open', side_effect=swap), self.assertRaises((OSError, ValueError)):
                    session.prepare(path)
                binding.prepare.assert_not_called()
                self.assertIsNone(session._artifact_directory)
                self.assertLess(time.monotonic()-start, 1)

    def test_binding_failure_cleans_frozen_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'model'; path.write_bytes(b'abc'); captured=[]
            def fail(p, c):
                captured.append(p); raise RuntimeError('binding failed')
            binding=FunctionBinding(operations=('inference',),prepare=fail,compile=lambda p,c:p,
                                    load=lambda p,c:p,execute=lambda h,o,x:x,close=lambda:None)
            cfg=ExtensionConfig('fixture','g',bounded_artifact_digest(path,3),'sdk','1','cpu')
            session=ExtensionSession(cfg,binding)
            with self.assertRaises(RuntimeError): session.prepare(path)
            self.assertFalse(captured[0].exists()); self.assertEqual(session.state,'quarantined')


class TransportDeadlineTests(unittest.TestCase):
    def backend(self, transport, seconds=.7):
        backend = StorageBackend(BackendConfig('s3','target','g',timeout_seconds=seconds), transport)
        self.addCleanup(backend.worker.stop)
        return backend

    @unittest.skipUnless(os.name == 'posix', 'POSIX session escape prevention')
    def test_storage_cannot_launch_a_detached_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp)/'escaped'
            b = self.backend(DetachedTransport(str(marker)), 3)
            with self.assertRaises(PermissionError): b.write(b'abc', generation='g')
            self.assertEqual(b.bytes_written, 0)
            self.assertFalse(marker.exists())
            b.close()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux inherited syscall filter')
    def test_linux_descendants_inherit_group_and_session_restrictions(self):
        child = "import os; denied=0\nfor call in (lambda:os.setsid(),lambda:os.setpgid(0,0)):\n try: call()\n except PermissionError: denied+=1\nassert denied==2\n"
        parent = ('from thm._process_containment import install_descendant_containment\n'
                  'import subprocess,sys,threading\n'
                  'install_descendant_containment()\n'
                  'thread=threading.Thread(target=lambda:None);thread.start();thread.join()\n'
                  'subprocess.run([sys.executable,"-c",'+repr(child)+'],check=True)\n')
        result = subprocess.run([sys.executable, '-c', parent], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_all_transport_callbacks_are_interruptible(self):
        for stage in ('stage', 'commit', 'size', 'read', 'abort', 'close'):
            with self.subTest(stage=stage):
                b = self.backend(BlockingTransport(stage))
                start = time.monotonic()
                if stage == 'close':
                    b.write(b'abc', generation='g')
                    with self.assertRaises(TimeoutError): b.close()
                elif stage == 'abort':
                    with self.assertRaises(OSError): b.write(b'abc', generation='g')
                    self.assertEqual(b.journal[-1]['cleanup_error'], 'TimeoutError')
                else:
                    with self.assertRaises(TimeoutError): b.write(b'abc', generation='g')
                    self.assertEqual(b.journal[-1]['state'], 'indeterminate-timeout')
                self.assertLess(time.monotonic()-start, 4)
                self.assertEqual(b.bytes_written, 0 if stage != 'close' else 3)
                self.assertIn(b.state, ('closed','quarantined'))
                self.assertIsNone(b.worker.process)

    def test_read_verify_recover_have_independent_deadlines(self):
        key=hashlib.sha256(b'abc').hexdigest()
        for operation in ('read','verify','recover'):
            with self.subTest(operation=operation):
                b=self.backend(BlockingTransport('read'))
                with self.assertRaises(TimeoutError):
                    if operation=='read': b.read(TransferExtent(key,0,1),generation='g')
                    elif operation=='verify': b.verify(key)
                    else: b.recover(key,generation='g')
                self.assertEqual(b.state,'quarantined');self.assertIsNone(b.worker.process)

    def test_expired_deadline_never_starts_callback(self):
        b=self.backend(BlockingTransport('stage'))
        with self.assertRaises(TimeoutError): b.worker.call('stage',(),time.monotonic()-1)
        self.assertIsNone(b.worker.process)

    def test_mounted_timeout_cleans_owned_pending_file(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            b=self.backend(HangingMountedStage(tmp))
            cleanup.callback(b.close)
            with self.assertRaises(TimeoutError): b.write(b'abc',generation='g')
            b.close()
            self.assertIsNone(b.worker.process)
            self.assertIsNone(b.worker.budget)
            self.assertIsNone(b.transport._root_fd)
            self.assertEqual(list(Path(tmp).iterdir()),[])
            if os.name == 'nt':
                # Confirm the directory really becomes deletable after owned
                # process termination. Only transient sharing violations retry;
                # a persistent leaked handle still fails within one second.
                deadline = time.monotonic() + 1
                while True:
                    try:
                        os.rmdir(tmp)
                        break
                    except PermissionError as exc:
                        if getattr(exc, 'winerror', None) != 32 or time.monotonic() >= deadline:
                            raise
                        time.sleep(.01)

    def test_s3_factory_preserves_state_and_receipt(self):
        b=self.backend(s3_factory,3)
        key=b.write(b'abcdef',generation='g')
        self.assertEqual(b.read(TransferExtent(key,2,2),generation='g'),b'cd')
        self.assertEqual(b.receipt()['execution_boundary'],'owned-process-tree')
        b.close();self.assertIsNone(b.worker.process)

    def test_lost_commit_acknowledgement_remains_indeterminate(self):
        data = b'published before acknowledgement'
        key = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            for transport in (LostMountedAcknowledgement(tmp),
                              S3Transport(LostS3Acknowledgement(), 'bucket')):
                with self.subTest(transport=type(transport).__name__):
                    b = self.backend(transport, 3)
                    with self.assertRaises(OSError):
                        b.write(data, generation='g')
                    self.assertEqual(b.receipt()['journal'][-1]['state'], 'indeterminate-commit')
                    self.assertEqual(b.bytes_written, 0)
                    if sys.platform == 'darwin' and isinstance(transport, MountedFilesystemTransport):
                        self.assertFalse((Path(tmp)/(key+'.seg')).exists())
                        b.close()
                        continue
                    self.assertTrue(b.recover(key, generation='g')['verified'])
                    self.assertEqual(b.read(TransferExtent(key, 0, len(data)), generation='g'), data)
                    self.assertEqual(b.receipt()['journal'][-1]['state'], 'indeterminate-commit')
                    b.close()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux real kernel lease attack')
    def test_same_credential_writer_cannot_corrupt_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=self.backend(AttackedMountedPublication(tmp),3)
            with self.assertRaises(RuntimeError):b.write(b'abc',generation='g')
            self.assertEqual(b.bytes_written,0)
            self.assertEqual(b.journal[-1]['state'],'indeterminate-commit')
            self.assertFalse((Path(tmp)/(hashlib.sha256(b'abc').hexdigest()+'.seg')).exists())
            self.assertIsNone(b.worker.process)

    def test_nonpickleable_transport_fails_explicitly(self):
        with self.assertRaises(TypeError):
            self.backend(S3Transport(mock.Mock(),'bucket'))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'procfs helper liveness')
    def test_timeout_terminates_descendant_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/'helper'
            b=self.backend(BlockingTransport('stage',str(marker)),1)
            with self.assertRaises(TimeoutError): b.write(b'abc',generation='g')
            self.assertTrue(marker.exists())
            status=Path('/proc')/marker.read_text()/'stat'
            if status.exists(): self.assertEqual(status.read_text().rsplit(')',1)[1].split()[0],'Z')
            b.close()


if __name__ == '__main__':
    unittest.main()
