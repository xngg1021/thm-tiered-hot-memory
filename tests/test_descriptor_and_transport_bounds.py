import functools
import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from thm._bounded_files import open_regular,read_regular
from thm.runtime.fabric.extensions import bounded_artifact_digest
from thm.evaluation.memory import AgentMemory
from thm.physical.backends import BackendConfig,StorageBackend
from thm.physical.fixtures import DelayedTransport


class DescriptorTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','POSIX FIFO/symlink race')
    def test_artifact_swap_to_fifo_or_symlink_does_not_open_unbounded(self):
        from thm import _bounded_files as bounded
        for kind in ('fifo','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=root/'model';path.write_bytes(b'abc')
                real=bounded._open_fd
                def swap(value, **kwargs):
                    path.unlink()
                    if kind=='fifo':os.mkfifo(path)
                    else:path.symlink_to('/dev/zero')
                    return real(value, **kwargs)
                start=time.monotonic()
                with mock.patch.object(bounded,'_open_fd',side_effect=swap):
                    with self.assertRaises((ValueError,OSError)):bounded_artifact_digest(root,100)
                self.assertLess(time.monotonic()-start,1)

    def test_restore_size_checked_on_the_opened_descriptor(self):
        from thm import _bounded_files as bounded
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);small=root/'snapshot';small.mkdir();(small/'thm-memory.json').write_bytes(b'{}')
            large=root/'large';large.write_bytes(b'x'*1024)
            memory=AgentMemory(root/'memory.db','scope');real=bounded._open_fd
            with mock.patch('thm.evaluation.memory.SNAPSHOT_MAX_BYTES',100),mock.patch.object(bounded,'_open_fd',side_effect=lambda p, **kwargs:real(large, **kwargs)):
                with self.assertRaises(ValueError):memory.restore(small)
            memory.close()

    def test_growth_after_open_is_bounded_by_same_descriptor(self):
        from thm import _bounded_files as bounded
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'file';path.write_bytes(b'a');real=os.fstat
            def grow(fd):
                result=real(fd)
                path.write_bytes(b'x'*1024)
                return result
            with mock.patch.object(bounded.os,'fstat',side_effect=grow):
                with self.assertRaises(ValueError):read_regular(path,maximum_bytes=10)


class TransportBoundsTests(unittest.TestCase):
    def test_external_stage_commit_size_and_read_hangs_are_terminated(self):
        for stage in ('stage','commit','size','read'):
            with self.subTest(stage=stage):
                backend=StorageBackend(BackendConfig('s3','fixture','g',timeout_seconds=1),functools.partial(DelayedTransport,stage))
                start=time.monotonic()
                with self.assertRaises(TimeoutError):backend.write(b'abc',generation='g')
                self.assertLess(time.monotonic()-start,7)
                self.assertEqual(backend.state,'quarantined')
                self.assertIsNone(backend.worker.process)
                backend.close()

    def test_external_close_is_interruptible_too(self):
        backend=StorageBackend(BackendConfig('spdk','fixture','g',timeout_seconds=1),functools.partial(DelayedTransport,'close'))
        backend.write(b'abc',generation='g')
        with self.assertRaises(TimeoutError):backend.close()
        self.assertEqual(backend.state,'closed');self.assertTrue(backend.worker.process is None)


if __name__=='__main__':unittest.main()
