"""Read-only process accounting and a Windows Job Object for shadow children."""
import os
from pathlib import Path
import sys


class ChildBudget:
    def __init__(self, process, *, memory, cpu, io):
        self.process = process; self.memory = memory; self.cpu = cpu; self.io = io
        self.job = None; self.last = {}
        if os.name == 'nt':
            self._windows_job()

    def _windows_job(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
                        ('min_working', c.c_size_t), ('max_working', c.c_size_t), ('active', w.DWORD),
                        ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read','write','other')]
        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError('shadow job unavailable')
        limits = Extended(); limits.basic.flags = 0x2000 | 0x200 | 0x4
        limits.basic.job_time = int(self.cpu*10_000_000); limits.job_memory = self.memory
        if not kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, w.HANDLE(int(self.process._handle))):
            kernel.CloseHandle(job); raise OSError('shadow job limits unavailable')
        self.job = job; self.kernel = kernel; self.extended = Extended

    def _darwin_usage(self):
        import ctypes as c
        class Usage(c.Structure):
            _fields_ = [('uuid', c.c_uint8 * 16)] + [(name, c.c_uint64) for name in (
                'user_time', 'system_time', 'pkg_idle_wkups', 'interrupt_wkups', 'pageins',
                'wired_size', 'resident_size', 'phys_footprint', 'proc_start_abstime',
                'proc_exit_abstime', 'child_user_time', 'child_system_time',
                'child_pkg_idle_wkups', 'child_interrupt_wkups', 'child_pageins',
                'child_elapsed_abstime', 'diskio_bytesread', 'diskio_byteswritten')]
        library = c.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        library.proc_pid_rusage.argtypes = [c.c_int, c.c_int, c.c_void_p]
        library.proc_pid_rusage.restype = c.c_int
        usage = Usage()
        if library.proc_pid_rusage(self.process.pid, 2, c.byref(usage)):
            if self.process.poll() is not None:
                return None
            raise OSError(c.get_errno(), 'shadow process accounting unavailable')
        return {'ram_bytes': usage.resident_size,
                'cpu_seconds': (usage.user_time + usage.system_time + usage.child_user_time + usage.child_system_time)/1e9,
                'bytes_read': usage.diskio_bytesread, 'bytes_written': usage.diskio_byteswritten,
                'resource_source': 'darwin-proc-pid-rusage-v2-physical-io'}

    def check(self):
        if sys.platform.startswith('linux'):
            root = Path('/proc') / str(self.process.pid)
            try:
                status = dict(line.split(':', 1) for line in (root/'status').read_text().splitlines() if ':' in line)
                rss = int(status.get('VmRSS', '0 kB').split()[0])*1024
                # rchar includes cached filesystem reads; read_bytes alone hides them.
                io = dict(line.split(':', 1) for line in (root/'io').read_text().splitlines())
                read = int(io.get('rchar', 0)); written = int(io.get('wchar', 0))
                fields = (root/'stat').read_text().rsplit(')', 1)[1].split()
                cpu = (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
            except FileNotFoundError:
                return
            self.last = {'ram_bytes': rss, 'cpu_seconds': cpu, 'bytes_read': read, 'bytes_written': written,
                         'resource_source': 'procfs-child'}
            if rss > self.memory or cpu > self.cpu or read+written > self.io:
                raise RuntimeError('shadow observed resource budget exceeded')
        elif sys.platform == 'darwin':
            observed = self._darwin_usage()
            if observed is None:
                return
            self.last = observed
            if (observed['ram_bytes'] > self.memory or observed['cpu_seconds'] > self.cpu
                    or observed['bytes_read'] + observed['bytes_written'] > self.io):
                raise RuntimeError('shadow observed resource budget exceeded')
        elif self.job:
            import ctypes as c
            limits = self.extended()
            if not self.kernel.QueryInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits), None):
                raise OSError('shadow job accounting failed')
            self.last = {'ram_bytes': limits.peak_job, 'bytes_read': limits.io.read,
                         'bytes_written': limits.io.write, 'resource_source': 'windows-job'}
            if limits.io.read+limits.io.write > self.io:
                raise RuntimeError('shadow I/O budget exceeded')

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job); self.job = None
