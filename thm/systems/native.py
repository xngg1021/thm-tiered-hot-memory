"""Public OS resource controls; process-local hints and explicit actuation gates."""
import ctypes as c
import ctypes.util
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import select
import time
from .contracts import PermissionGate, finite, integer


def psi_snapshot(path='/proc/pressure'):
    root = Path(path)
    output = {}
    for resource in ('cpu', 'memory', 'io'):
        try:
            candidate = root/resource if root.name == 'pressure' else root/(resource+'.pressure')
            text = candidate.read_text()[:4096]
            rows = {}
            for line in text.splitlines():
                name, *values = line.split()
                if name not in ('some', 'full'):
                    raise ValueError('unknown PSI class')
                row = dict(item.split('=', 1) for item in values)
                parsed = {key: int(row[key]) if key == 'total' else float(row[key]) for key in ('avg10', 'avg60', 'avg300', 'total')}
                for key, value in parsed.items():
                    finite(value)
                    if key != 'total' and value > 100:
                        raise ValueError('PSI fraction out of range')
                rows[name] = parsed
            output[resource] = {'status': 'observed', 'rows': rows}
        except (OSError, ValueError, KeyError):
            output[resource] = {'status': 'unavailable', 'rows': None}
    return {'source': 'linux-psi', 'sample_timestamp': time.monotonic(), 'resources': output}


class PSIThreshold:
    def __init__(self, path, *, stall_us=10000, window_us=1000000, kind='some'):
        integer(window_us, minimum=500000, maximum=10000000)
        integer(stall_us, minimum=1, maximum=window_us)
        if kind not in ('some', 'full'):
            raise ValueError('invalid PSI class')
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        try:
            trigger = f'{kind} {stall_us} {window_us}'.encode()
            if os.write(self.fd, trigger) != len(trigger):
                raise OSError('short PSI trigger')
            self.poller = select.poll()
            self.poller.register(self.fd, select.POLLPRI | select.POLLERR)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def wait(self, timeout=.1):
        finite(timeout)
        if timeout > 10 or self.fd is None:
            raise ValueError('closed trigger or unbounded wait')
        return bool(self.poller.poll(int(timeout*1000)))

    def close(self):
        if self.fd is not None:
            self.poller.unregister(self.fd)
            os.close(self.fd)
            self.fd = None


class CgroupDomain:
    """Caller-owned, delegated cgroup v2 directory. Never creates a root domain."""
    def __init__(self, directory, qos='background'):
        if qos not in ('interactive', 'background', 'research', 'maintenance'):
            raise ValueError('invalid domain')
        self.root = Path(directory).resolve()
        self.qos = qos
        self.previous = {}

    def observe(self):
        values = {}
        for name in ('cpu.stat', 'cpu.weight', 'cpu.max', 'memory.current', 'memory.max', 'io.stat', 'cgroup.events'):
            try:
                values[name] = (self.root/name).read_text()[:16384]
            except OSError:
                values[name] = None
        return {'domain': self.qos, 'values': values, 'psi': psi_snapshot(self.root)}

    def configure(self, changes, gate=PermissionGate()):
        levels = {'cpu.weight': 'S1', 'cpu.max': 'S2', 'memory.max': 'S2'}
        if not changes or not set(changes) <= set(levels):
            raise ValueError('unsupported cgroup controls')
        for name, value in changes.items():
            gate.require(levels[name])
            if name == 'cpu.weight':
                integer(value, minimum=1, maximum=10000)
            elif name == 'memory.max':
                if value != 'max':
                    integer(value, minimum=1)
            else:
                parts = str(value).split()
                if len(parts) != 2:
                    raise ValueError('cpu.max requires quota and period')
                integer(int(parts[1]), minimum=1000, maximum=1000000)
                if parts[0] != 'max':
                    integer(int(parts[0]), minimum=1000)
        try:
            for name, value in changes.items():
                path = self.root/name
                if path.is_symlink():
                    raise ValueError('cgroup control symlink rejected')
                self.previous.setdefault(name, path.read_text())
                with path.open('w') as stream:
                    stream.write(str(value))
        except BaseException:
            self.rollback()
            raise
        return {'applied': dict(changes), 'domain': self.qos, 'rollback': True}

    def rollback(self):
        for name in tuple(self.previous):
            with (self.root/name).open('w') as stream:
                stream.write(self.previous[name])
            self.previous.pop(name)


@dataclass(frozen=True)
class NumaReceipt:
    requested_node: int | None
    observed_node: int | None
    cpu_affinity: tuple[int, ...]
    device_locality: int | None = None
    migration_count: int = 0
    local_remote_evidence: dict | None = None
    status: str = 'unavailable'


class NumaPolicy:
    def __init__(self):
        self.previous_affinity = None
        self.lib = None
        if platform.system() == 'Linux':
            path = ctypes.util.find_library('numa')
            if path:
                self.lib = c.CDLL(path, use_errno=True)

    def affinity(self, cpus, gate=PermissionGate()):
        gate.require('S1')
        cpus = set(integer(x, maximum=65535) for x in cpus)
        if not cpus or len(cpus) > 65536:
            raise ValueError('invalid CPU set')
        if not hasattr(os, 'sched_getaffinity'):
            return NumaReceipt(None, None, (), status='unavailable')
        old = os.sched_getaffinity(0)
        os.sched_setaffinity(0, cpus)
        self.previous_affinity = old
        observed = tuple(sorted(os.sched_getaffinity(0)))
        return NumaReceipt(None, None, observed, status='native-executed')

    def bind_buffer(self, buffer, node, gate=PermissionGate(), *, migrate=False):
        gate.require('S2' if migrate else 'S1')
        integer(node, maximum=4095)
        if not self.lib:
            return NumaReceipt(node, None, (), status='unavailable')
        address = c.addressof(buffer)
        length = c.sizeof(buffer)
        if address % os.sysconf('SC_PAGE_SIZE'):
            raise ValueError('NUMA requires page-aligned owned memory')
        bits = c.sizeof(c.c_ulong)*8
        mask = (c.c_ulong * (node//bits+1))()
        mask[node//bits] = 1 << (node%bits)
        self.lib.mbind.argtypes = [c.c_void_p, c.c_ulong, c.c_int, c.POINTER(c.c_ulong), c.c_ulong, c.c_uint]
        self.lib.mbind.restype = c.c_long
        if self.lib.mbind(address, length, 2, mask, node+1, 2 if migrate else 0):
            raise OSError(c.get_errno(), 'mbind unavailable')
        observed = c.c_int(-1)
        self.lib.get_mempolicy.argtypes = [c.POINTER(c.c_int), c.c_void_p, c.c_ulong, c.c_void_p, c.c_ulong]
        got = self.lib.get_mempolicy(c.byref(observed), None, 0, address, 3)
        return NumaReceipt(node, observed.value if got == 0 else None,
                           tuple(sorted(os.sched_getaffinity(0))), status='native-executed')

    def rollback(self):
        if self.previous_affinity is not None:
            os.sched_setaffinity(0, self.previous_affinity)
            self.previous_affinity = None


class NativeQoS:
    """Current-thread QoS, restored at scope exit. No system power-plan edits."""
    def __init__(self):
        self.undo = None

    def apply(self, qos, gate=PermissionGate()):
        gate.require('S1')
        if qos not in ('interactive', 'bulk', 'background', 'research', 'maintenance'):
            raise ValueError('invalid QoS')
        if self.undo is not None:
            raise ValueError('restore existing QoS first')
        if platform.system() == 'Darwin':
            lib = c.CDLL('/usr/lib/libSystem.B.dylib')
            lib.pthread_self.restype = c.c_void_p
            lib.pthread_get_qos_class_np.argtypes = [c.c_void_p, c.POINTER(c.c_int)]
            lib.pthread_get_qos_class_np.restype = c.c_uint
            lib.pthread_set_qos_class_self_np.argtypes = [c.c_uint, c.c_int]
            relative = c.c_int()
            previous = lib.pthread_get_qos_class_np(lib.pthread_self(), c.byref(relative))
            target = 0x19 if qos == 'interactive' else 0x11 if qos == 'bulk' else 0x09
            if lib.pthread_set_qos_class_self_np(target, 0):
                raise OSError('pthread QoS rejected')
            self.undo = lambda: lib.pthread_set_qos_class_self_np(previous, relative.value)
            return {'path': 'pthread-qos', 'requested': qos, 'native_executed': True}
        if platform.system() == 'Windows':
            from ctypes import wintypes as w
            class State(c.Structure):
                _fields_ = [('version', w.ULONG), ('control', w.ULONG), ('state', w.ULONG)]
            lib = c.WinDLL('kernel32', use_last_error=True)
            lib.GetCurrentThread.restype = w.HANDLE
            lib.GetThreadInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
            lib.SetThreadInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
            handle = lib.GetCurrentThread()
            previous = State(1, 0, 0)
            if not lib.GetThreadInformation(handle, 3, c.byref(previous), c.sizeof(previous)):
                raise c.WinError(c.get_last_error())
            desired = State(1, 1, 0 if qos == 'interactive' else 1)
            if not lib.SetThreadInformation(handle, 3, c.byref(desired), c.sizeof(desired)):
                raise c.WinError(c.get_last_error())
            self.undo = lambda: lib.SetThreadInformation(handle, 3, c.byref(previous), c.sizeof(previous))
            return {'path': 'EcoQoS', 'requested': qos, 'native_executed': True}
        # Linux per-worker affinity/domain hints are handled by NumaPolicy/CgroupDomain.
        return {'path': 'portable', 'requested': qos, 'native_executed': False, 'reason': 'use delegated cgroup or affinity'}

    def close(self):
        if self.undo is not None:
            self.undo()
            self.undo = None


def apple_observations(torch_api=None):
    result = {'platform': platform.system(), 'temperature_c': None, 'energy_j': None,
              'sensor_status': 'unobservable-public-api', 'thermal_state': None,
              'mps_allocated': None, 'mps_driver_allocated': None, 'unified_memory_zero_copy': False}
    if platform.system() != 'Darwin':
        return {**result, 'status': 'platform-unavailable'}
    try:
        from Foundation import NSProcessInfo
        result['thermal_state'] = int(NSProcessInfo.processInfo().thermalState())
    except (ImportError, AttributeError):
        pass
    if torch_api is not None and torch_api.backends.mps.is_available():
        result['mps_allocated'] = int(torch_api.mps.current_allocated_memory())
        result['mps_driver_allocated'] = int(torch_api.mps.driver_allocated_memory())
    return {**result, 'status': 'observed-public-subset'}


class ProbeContract:
    """Bounded eBPF/ETW attribution stream; caller owns native probe lifecycle."""
    KINDS = ('syscall', 'block-io', 'scheduler', 'page-fault', 'process', 'tcp', 'tracepoint', 'context-switch')

    def __init__(self, binding, *, platform_name, capacity=1024):
        if platform_name not in ('ebpf', 'etw'):
            raise ValueError('unknown native tracer')
        integer(capacity, minimum=1, maximum=100000)
        self.binding, self.platform_name, self.capacity = binding, platform_name, capacity
        self.closed = False

    def collect(self, timeout=.1):
        finite(timeout)
        if timeout > 5 or self.closed:
            raise ValueError('closed or unbounded probe')
        rows = list(self.binding.poll(timeout, self.capacity))
        if len(rows) > self.capacity or any(r.get('kind') not in self.KINDS for r in rows):
            raise ValueError('probe contract violation')
        return {'backend': self.platform_name, 'events': rows, 'evidence': self.binding.evidence,
                'purpose': 'attribution', 'scheduler_mutation': False}

    def close(self):
        if not self.closed:
            self.binding.close()
            self.closed = True
