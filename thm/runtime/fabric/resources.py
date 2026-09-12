"""Read-only process-tree accounting and a Windows Job Object for bounded children."""
import os
from pathlib import Path
import sys


class ProcessGroupAccountingUnavailable(RuntimeError):
    """A candidate cannot prove its owned process-group resource budget."""


def linux_worker_lifetime():
    """Return durable Linux usage evidence before the trusted worker exits.

    Parent-side ``/proc`` scans can observe live process-group members, but an
    already reaped helper disappears between samples.  The trusted THM worker
    therefore publishes its own lifetime counters.  Linux ``RUSAGE_CHILDREN``
    preserves CPU/peak-resource evidence for waited children, but it cannot
    provide the byte-exact ``rchar/wchar`` accounting used by THM.  Any observed
    reaped-child activity is consequently fail-closed by ``check_lifetime``
    unless a future lifetime-scoped OS primitive (for example a delegated
    cgroup) supplies complete accounting.
    """
    if not sys.platform.startswith('linux'):
        return None
    import resource
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    io = {}
    try:
        io = dict(line.split(':', 1) for line in Path('/proc/self/io').read_text().splitlines() if ':' in line)
    except (FileNotFoundError, PermissionError, OSError):
        pass
    child_fields = (
        children.ru_utime, children.ru_stime, children.ru_maxrss,
        children.ru_minflt, children.ru_majflt, children.ru_inblock,
        children.ru_oublock, children.ru_nvcsw, children.ru_nivcsw,
    )
    return {
        'schema': 1,
        'source': 'linux-getrusage-self-children+proc-self-io',
        'self_cpu_seconds': float(own.ru_utime + own.ru_stime),
        'self_maxrss_bytes': int(own.ru_maxrss) * 1024,
        'self_bytes_read': int(io.get('rchar', 0)),
        'self_bytes_written': int(io.get('wchar', 0)),
        'child_cpu_seconds': float(children.ru_utime + children.ru_stime),
        'child_maxrss_bytes': int(children.ru_maxrss) * 1024,
        'child_block_reads': int(children.ru_inblock),
        'child_block_writes': int(children.ru_oublock),
        'child_activity': any(bool(value) for value in child_fields),
    }


class ChildBudget:
    def __init__(self, process, *, memory, cpu, io):
        self.process = process; self.memory = memory; self.cpu = cpu; self.io = io
        self.job = None; self.last = {}
        # POSIX workers are launched with start_new_session=True, so the leader
        # PID is also the process-group ID.  Retain it after the leader exits so
        # orphan helpers can still be found and killed/accounted.
        self.pgid = process.pid if sys.platform.startswith('linux') else None
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

    def _linux_usage(self, proc_root=Path('/proc'), pgid=None):
        """Aggregate every *live* observable member of the worker process group."""
        if proc_root == Path('/proc'):
            own_pid = int((proc_root/'self'/'stat').read_text().split(' ', 1)[0])
            if own_pid != os.getpid():
                raise ProcessGroupAccountingUnavailable('procfs PID namespace mismatch')
        if pgid is None:
            pgid = self.pgid
        if pgid is None:
            try:
                pgid = os.getpgid(self.process.pid)
            except ProcessLookupError:
                return None
        ticks = os.sysconf('SC_CLK_TCK')
        rss = 0; cpu = 0.0; read = 0; written = 0; members = 0
        try:
            entries = list(proc_root.iterdir())
        except FileNotFoundError:
            return None
        owned = []
        for root in entries:
            if not root.name.isdigit():
                continue
            try:
                # Filter with the public process-group syscall before opening
                # potentially protected /proc records belonging to other users.
                if os.getpgid(int(root.name)) == int(pgid):
                    owned.append(root)
            except ProcessLookupError:
                continue
        for root in owned:
            try:
                fields = (root/'stat').read_text().rsplit(')', 1)[1].split()
                if len(fields) < 13 or int(fields[2]) != int(pgid):
                    continue
                if fields[0] in ('Z', 'X', 'x'):
                    continue
                status = dict(line.split(':', 1) for line in (root/'status').read_text().splitlines() if ':' in line)
                io = dict(line.split(':', 1) for line in (root/'io').read_text().splitlines() if ':' in line)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError as denied:
                # A snapshot cannot exclude helpers joining after enumeration.
                # Neither leader exit nor a later readable/dead sample proves
                # lifetime group accounting, so never wait and accept here.
                raise ProcessGroupAccountingUnavailable(
                    'shadow process-group lifetime accounting unavailable') from denied
            members += 1
            rss += int(status.get('VmRSS', '0 kB').split()[0])*1024
            cpu += (int(fields[11])+int(fields[12]))/ticks
            read += int(io.get('rchar', 0)); written += int(io.get('wchar', 0))
        if not members:
            return None
        return {'ram_bytes': rss, 'cpu_seconds': cpu, 'bytes_read': read, 'bytes_written': written,
                'processes': members, 'resource_source': 'procfs-process-group-live'}

    def _over(self, observed):
        return (observed.get('ram_bytes', 0) > self.memory
                or observed.get('cpu_seconds', 0) > self.cpu
                or observed.get('bytes_read', 0) + observed.get('bytes_written', 0) > self.io)

    def check(self):
        if sys.platform.startswith('linux'):
            observed = self._linux_usage()
            if observed is None:
                return
            self.last = {**self.last, **observed}
            # A one-shot leader that has exited must not leave a helper alive and
            # still publish its result.  The process-group ID remains known even
            # after Popen has reaped the leader.
            if self.process.poll() is not None and observed.get('processes', 0):
                # The leader may exit between /proc sampling and poll/reap.
                # Re-scan after reaping before classifying a surviving helper.
                remaining = self._linux_usage()
                if remaining and remaining.get('processes', 0):
                    raise RuntimeError('shadow helper survived worker leader')
            if self._over(observed):
                raise RuntimeError('shadow observed resource budget exceeded')
        elif sys.platform == 'darwin':
            observed = self._darwin_usage()
            if observed is None:
                return
            self.last = observed
            if self._over(observed):
                raise RuntimeError('shadow observed resource budget exceeded')
        elif self.job:
            import ctypes as c
            class Accounting(c.Structure):
                _fields_ = [(k,c.c_longlong) for k in ('user','kernel','period_user','period_kernel')] + [(k,c.c_uint32) for k in ('faults','total','active','terminated')]
            accounting = Accounting()
            if not self.kernel.QueryInformationJobObject(self.job, 1, c.byref(accounting), c.sizeof(accounting), None):
                raise OSError('shadow job CPU accounting failed')
            limits = self.extended()
            if not self.kernel.QueryInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits), None):
                raise OSError('shadow job accounting failed')
            self.last = {'ram_bytes': limits.peak_job, 'cpu_seconds': (accounting.user+accounting.kernel)/1e7, 'bytes_read': limits.io.read,
                         'bytes_written': limits.io.write, 'resource_source': 'windows-job'}
            if limits.io.read+limits.io.write > self.io or self.last['cpu_seconds'] > self.cpu:
                raise RuntimeError('shadow I/O budget exceeded')

    def check_lifetime(self, evidence):
        """Validate worker-published lifetime counters before accepting output.

        On Linux this closes the post-exit blind spot of `/proc` sampling.  The
        worker's own CPU/RSS/rchar/wchar counters remain available just before it
        exits.  Reaped helper activity is also detectable through
        RUSAGE_CHILDREN, but byte-exact aggregate helper I/O is not; such a result
        is therefore deferred rather than pretending the budget was proven.
        """
        if not sys.platform.startswith('linux'):
            return
        if not isinstance(evidence, dict) or evidence.get('source') != 'linux-getrusage-self-children+proc-self-io':
            raise RuntimeError('shadow Linux lifetime resource evidence missing')
        observed = {
            'ram_bytes': int(evidence.get('self_maxrss_bytes', 0)),
            'cpu_seconds': float(evidence.get('self_cpu_seconds', 0)),
            'bytes_read': int(evidence.get('self_bytes_read', 0)),
            'bytes_written': int(evidence.get('self_bytes_written', 0)),
            'resource_source': evidence['source'],
            'child_cpu_seconds': float(evidence.get('child_cpu_seconds', 0)),
            'child_maxrss_bytes': int(evidence.get('child_maxrss_bytes', 0)),
            'child_block_reads': int(evidence.get('child_block_reads', 0)),
            'child_block_writes': int(evidence.get('child_block_writes', 0)),
            'reaped_child_activity': bool(evidence.get('child_activity')),
        }
        self.last = {**self.last,
                     'ram_bytes': max(self.last.get('ram_bytes', 0), observed['ram_bytes']),
                     'cpu_seconds': max(self.last.get('cpu_seconds', 0), observed['cpu_seconds']),
                     'bytes_read': max(self.last.get('bytes_read', 0), observed['bytes_read']),
                     'bytes_written': max(self.last.get('bytes_written', 0), observed['bytes_written']),
                     **{k:v for k,v in observed.items() if k not in ('ram_bytes','cpu_seconds','bytes_read','bytes_written')}}
        if observed['reaped_child_activity']:
            raise RuntimeError('shadow reaped-helper byte accounting unavailable')
        if self._over(self.last):
            raise RuntimeError('shadow lifetime resource budget exceeded')

    def renew(self, *, cpu, io):
        """New bounded serving request after a completed bounded preparation."""
        self.cpu = self.last.get('cpu_seconds', 0) + cpu
        self.io = self.last.get('bytes_read', 0) + self.last.get('bytes_written', 0) + io
        if self.job:
            import ctypes as c
            limits = self.extended()
            if not self.kernel.QueryInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits), None):
                raise OSError('job accounting unavailable')
            limits.basic.job_time = int(self.cpu*10_000_000)
            if not self.kernel.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)):
                raise OSError('job request limits unavailable')

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job); self.job = None


def stop_owned_process_tree(process, budget):
    import signal
    import subprocess
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as denied:
            # Darwin may reject the group during the leader's exit/reap window.
            # A bounded wait distinguishes that race from a live denied worker.
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                raise denied
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            except PermissionError:
                raise denied
            else:
                raise denied  # a surviving group is never certified as cleaned
    elif budget is not None:
        budget.close()
    elif process.poll() is None:
        process.kill()  # no supplied code runs before Job Object attachment
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
