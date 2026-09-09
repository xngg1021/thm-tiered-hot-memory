"""Process-constrained device graph. Fast bootstrap never probes native runtimes."""
from dataclasses import asdict, dataclass, field
import os
import platform
from pathlib import Path
from .contracts import identity


@dataclass(frozen=True)
class DeviceNode:
    id: str
    kind: str
    installed: bool | None = None
    os_visible: bool | None = None
    process_available: bool | None = None
    properties: dict = field(default_factory=dict)


@dataclass
class HardwareGraph:
    nodes: list
    edges: list
    os: str
    build: str
    architecture: str
    schema: int = 1

    def public(self):
        return asdict(self)

    @property
    def fingerprint(self):
        return identity(self.public())

    def available(self, kind=None):
        return [n for n in self.nodes if n.process_available is True and (kind is None or n.kind == kind)]

    @classmethod
    def from_profile(cls, profile, *, storage_targets=()):
        """Existing installed/visible/available distinctions survive conversion."""
        p = profile.identity() if hasattr(profile, 'identity') else dict(profile)
        allowed = p.get('process_available_cpus')
        nodes = [DeviceNode('cpu', 'cpu', p.get('installed_logical_cpus') is not None,
                            p.get('os_visible_cpus') is not None, bool(allowed) if allowed is not None else None,
                            {'installed_count': p.get('installed_logical_cpus'),
                             'visible_count': p.get('os_visible_cpus'), 'available_count': allowed,
                             'affinity': p.get('cpu_affinity'), 'cpuset': p.get('cpuset'),
                             'quota': p.get('cgroup_quota_cpus'), 'groups': p.get('processor_groups'),
                             'core_types': p.get('core_types')})]
        nodes.append(DeviceNode('dram', 'memory', None, True, True, {'bytes': p.get('ram_total'), 'unified': None}))
        edges = [('cpu', 'dram', 'access')]
        affinity = p.get('cpu_affinity')
        for name, cpus in sorted(p.get('numa_nodes', {}).items()):
            usable = sorted(set(cpus) & set(affinity)) if affinity is not None else None
            nodes.append(DeviceNode('numa:' + name, 'numa', True, True, bool(usable) if usable is not None else None,
                                    {'visible_cpus': cpus, 'available_cpus': usable}))
            edges.append(('cpu', 'numa:' + name, 'contains'))
        for i, dev in enumerate(p.get('accelerators', ())):
            key = 'accelerator:' + str(i)
            # Driver-visible is not automatically process-available.
            nodes.append(DeviceNode(key, dev.get('device_class', 'gpu'), True, True,
                                    dev.get('process_available'),
                                    {k: dev.get(k) for k in ('vendor', 'driver', 'vram_total', 'pci_parent', 'unified_memory')}))
            edges.append((key, 'dram', 'transfer-unknown'))
        for target in storage_targets:
            # Reuse StorageTarget identity, never copy its private locator.
            key = 'storage:' + target.target_id
            nodes.append(DeviceNode(key, 'storage', None, True, True,
                                    {'target_id': target.target_id, 'transport': getattr(target, 'transport', None)}))
            edges.append((key, 'dram', 'filesystem'))
        return cls(nodes, edges, p['os'], p.get('kernel', 'unknown'), p['architecture'])


class HostDeviceProvider:
    def __init__(self, spec=None):
        self.spec = spec

    def discover(self):
        # sysctl/PowerShell/driver utilities are diagnostic-only, not bootstrap.
        from ..hardware import HardwareProfile, cpulist, quota_limit, read
        h = HardwareProfile(platform.machine().lower(), platform.system(), platform.release())
        h.os_visible_cpus = os.cpu_count()
        try:
            h.cpu_affinity = sorted(os.sched_getaffinity(0))
        except (OSError, AttributeError):
            pass
        h.process_available_cpus = len(h.cpu_affinity) if h.cpu_affinity is not None else h.os_visible_cpus
        if h.os == 'Linux':
            group = next((s[3:] for s in (read('/proc/self/cgroup') or '').splitlines() if s.startswith('0::')), '/')
            root = Path('/sys/fs/cgroup'); path = root / group.lstrip('/')
            if not path.is_dir():
                path = root
            quotas = []
            while path == root or root in path.parents:
                quota = quota_limit(read(path / 'cpu.max'))
                if quota is not None:
                    quotas.append(quota)
                try:
                    cpus = cpulist(read(path / 'cpuset.cpus.effective'))
                    if cpus:
                        h.cpuset = cpus if h.cpuset is None else sorted(set(h.cpuset) & set(cpus))
                except ValueError:
                    pass
                if path == root:
                    break
                path = path.parent
            if quotas:
                h.cgroup_quota_cpus = min(quotas)
            limits = [h.process_available_cpus or 1]
            if h.cpuset is not None:
                limits.append(len(h.cpuset))
            if quotas:
                limits.append(max(1, int(min(quotas))))
            h.process_available_cpus = min(limits)
        elif h.os == 'Windows':
            # Public process affinity, without WMI or PowerShell startup.
            try:
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
                mask = ctypes.c_size_t(); system = ctypes.c_size_t()
                if kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(), ctypes.byref(mask), ctypes.byref(system)):
                    h.cpu_affinity = [i for i in range(ctypes.sizeof(mask)*8) if mask.value & (1 << i)]
                    h.process_available_cpus = len(h.cpu_affinity) or None
                else:
                    h.process_available_cpus = None
            except (AttributeError, OSError):
                h.process_available_cpus = None
        self.graph = HardwareGraph.from_profile(h)
        return self.graph

    def probe(self):
        return {'provider': 'host.device', 'availability': 'available',
                'devices': self.discover().public(), 'observed_kernel_dispatch': None}

    def fingerprint(self):
        return self.discover().fingerprint

    def topology(self):
        return self.discover().public()

    def capabilities(self):
        return {'native_init': False, 'system_mutation': False, 'process_constraints': True}

    def telemetry(self):
        return {'cpu_seconds': __import__('time').process_time(), 'joules': None, 'power': None}

    def close(self):
        pass
