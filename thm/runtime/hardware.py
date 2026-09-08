"""Conservative OS observations. Support is never evidence of kernel dispatch."""
from dataclasses import asdict, dataclass, field
from importlib.metadata import version, PackageNotFoundError
import json
import math
import os
import platform
from pathlib import Path
import subprocess

ISA = {'avx2':('avx2',), 'avx512f':('avx512f',), 'avx512_vnni':('avx512_vnni','avx512vnni'),
       'avx_vnni':('avx_vnni',), 'bf16':('avx512_bf16','bf16'), 'fp16':('avx512_fp16','fphp','asimdhp'),
       'amx_int8':('amx_int8',), 'amx_bf16':('amx_bf16',), 'neon':('neon','asimd'),
       'dotprod':('asimddp',), 'i8mm':('i8mm',), 'sve':('sve',), 'sve2':('sve2',),
       'sme':('sme',), 'sme2':('sme2',), 'power10_mma':('mma',), 'rvv':('rvv',)}


def read(path):
    try: return Path(path).read_text().strip()
    except (OSError, UnicodeError): return None


def cpulist(text):
    values = set()
    for part in (text or '').split(','):
        if not part: continue
        ends = part.split('-')
        if len(ends) not in (1,2): raise ValueError('invalid CPU list')
        low, high = int(ends[0]), int(ends[-1])
        if low < 0 or high < low or high-low > 65536: raise ValueError('invalid CPU range')
        values.update(range(low, high+1))
    return sorted(values)


def quota_limit(text):
    try:
        quota, period = text.split()
        if quota == 'max': return None
        q, p = int(quota), int(period)
        return q/p if q > 0 and p > 0 else None
    except (ValueError, AttributeError): return None


def versions():
    out = {}
    for name in ('torch','sentence-transformers','onnxruntime','onnxruntime-gpu','openvino','numpy','optimum','nncf'):
        try: out[name] = version(name)
        except PackageNotFoundError: out[name] = None
    return out


@dataclass
class HardwareProfile:
    architecture: str
    os: str
    kernel: str
    vendor: str | None = None
    model: str | None = None
    installed_logical_cpus: int | None = None
    os_visible_cpus: int | None = None
    process_available_cpus: int | None = None
    physical_cores_if_known: int | None = None
    cpu_affinity: list | None = None
    cgroup_quota_cpus: float | None = None
    cpuset: list | None = None
    processor_groups: list | None = None
    sockets: int | None = None
    numa_nodes: dict = field(default_factory=dict)
    core_types: dict | None = None
    ram_total: int | None = None
    ram_available: int | None = None
    cache_hierarchy: list = field(default_factory=list)
    hardware_reports_support: dict = field(default_factory=dict)
    backend_reports_support: dict = field(default_factory=dict)
    observed_kernel_dispatch: object = None
    accelerators: list = field(default_factory=list)
    schema: int = 1

    def identity(self): return asdict(self)


def probe():
    h = HardwareProfile(platform.machine().lower(), platform.system(), platform.release())
    h.os_visible_cpus = os.cpu_count()
    try: h.cpu_affinity = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError): pass
    h.process_available_cpus = len(h.cpu_affinity) if h.cpu_affinity is not None else h.os_visible_cpus
    flags = None
    if h.os == 'Linux':
        raw = read('/proc/cpuinfo') or ''
        records = [dict(line.split(':',1) for line in block.splitlines() if ':' in line) for block in raw.split('\n\n') if block]
        records = [{k.strip():v.strip() for k,v in r.items()} for r in records]
        available = [r for r in records if h.cpu_affinity is None or int(r.get('processor','-1')) in h.cpu_affinity]
        first = available[0] if available else {}
        h.vendor, h.model = first.get('vendor_id'), first.get('model name') or first.get('Processor')
        reported = [set((r.get('flags') or r.get('Features')).split()) for r in available if r.get('flags') or r.get('Features')]
        if reported and len(reported) == len(available): flags = set.intersection(*reported)
        try: h.installed_logical_cpus = len(cpulist(read('/sys/devices/system/cpu/present'))) or None
        except ValueError: pass
        if available and all('physical id' in r and 'core id' in r for r in available):
            h.physical_cores_if_known = len({(r['physical id'],r['core id']) for r in available})
            h.sockets = len({r['physical id'] for r in available})
        # Resolve this process's v2 cgroup and all visible ancestors; never use host count as quota.
        group = next((line[3:] for line in (read('/proc/self/cgroup') or '').splitlines() if line.startswith('0::')), '/')
        root = Path('/sys/fs/cgroup'); path = root / group.lstrip('/')
        if not path.is_dir(): path = root
        quotas = []
        while path == root or root in path.parents:
            q = quota_limit(read(path/'cpu.max'))
            if q is not None: quotas.append(q)
            try:
                allowed = cpulist(read(path/'cpuset.cpus.effective'))
                if allowed: h.cpuset = allowed if h.cpuset is None else sorted(set(h.cpuset)&set(allowed))
            except ValueError: pass
            if path == root: break
            path = path.parent
        h.cgroup_quota_cpus = min(quotas) if quotas else None
        limits = [h.process_available_cpus] if h.process_available_cpus else []
        if h.cpuset is not None: limits.append(len(h.cpuset))
        if quotas: limits.append(max(1, math.floor(min(quotas))))
        h.process_available_cpus = min(limits) if limits else None
        for node in sorted(Path('/sys/devices/system/node').glob('node[0-9]*')):
            try: h.numa_nodes[node.name] = cpulist(read(node/'cpulist'))
            except ValueError: pass
        mem = dict(line.split(':',1) for line in (read('/proc/meminfo') or '').splitlines() if ':' in line)
        for key, name in [('MemTotal','ram_total'),('MemAvailable','ram_available')]:
            try: setattr(h,name,int(mem[key].split()[0])*1024)
            except (KeyError,ValueError): pass
        for c in Path('/sys/devices/system/cpu/cpu0/cache').glob('index*'):
            h.cache_hierarchy.append({k:read(c/k) for k in ('level','type','size','shared_cpu_list')})
        # Public core_type is optional, and 0 means unknown.
        types = {str(cpu):read(f'/sys/devices/system/cpu/cpu{cpu}/topology/core_type') for cpu in (h.cpu_affinity or [])}
        if types and all(v in ('1','2') for v in types.values()): h.core_types = types
    elif h.os == 'Darwin':
        try:
            raw = subprocess.run(['sysctl','-a'],capture_output=True,text=True,timeout=5,check=True).stdout
            info = dict(line.split(': ',1) for line in raw.splitlines() if ': ' in line)
            h.model = info.get('machdep.cpu.brand_string')
            h.ram_total = int(info['hw.memsize']); h.physical_cores_if_known = int(info['hw.physicalcpu'])
            h.installed_logical_cpus = int(info['hw.logicalcpu_max'])
            h.core_types = {k:v for k,v in info.items() if k.startswith('hw.perflevel') and k.endswith(('name','physicalcpu','logicalcpu'))} or None
            flags = set((info.get('machdep.cpu.features','')+' '+info.get('machdep.cpu.leaf7_features','')).lower().split()) or None
        except (OSError,ValueError,KeyError,subprocess.SubprocessError): pass
    elif h.os == 'Windows':
        # Public Win32 API. Process mask is a conservative subset when groups span CPUs.
        try:
            import ctypes
            from ctypes import wintypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetCurrentProcess.restype=wintypes.HANDLE
            kernel.GetActiveProcessorCount.argtypes=[wintypes.WORD]
            h.os_visible_cpus=int(kernel.GetActiveProcessorCount(0xffff)) or None
            process_mask=ctypes.c_size_t();system_mask=ctypes.c_size_t()
            kernel.GetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
            if kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(),ctypes.byref(process_mask),ctypes.byref(system_mask)) and process_mask.value:
                h.cpu_affinity=[i for i in range(ctypes.sizeof(process_mask)*8) if process_mask.value & (1<<i)]
                h.process_available_cpus=len(h.cpu_affinity)
            else:h.process_available_cpus=None
            count=wintypes.USHORT(64);groups=(wintypes.USHORT*64)()
            if kernel.GetProcessGroupAffinity(kernel.GetCurrentProcess(),ctypes.byref(count),groups):h.processor_groups=list(groups[:count.value])
        except (AttributeError,OSError,ValueError):h.process_available_cpus=None
        try:
            command='Get-CimInstance Win32_Processor | Select-Object Manufacturer,Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress'
            data=json.loads(subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=8,check=True).stdout)
            rows=data if isinstance(data,list) else [data]
            h.vendor=rows[0].get('Manufacturer');h.model=rows[0].get('Name');h.sockets=len(rows)
            h.installed_logical_cpus=sum(int(r['NumberOfLogicalProcessors']) for r in rows)
            h.physical_cores_if_known=sum(int(r['NumberOfCores']) for r in rows)
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
    # Driver utility observations are lightweight; no tensor import or model load.
    try:
        import shutil
        command=shutil.which('nvidia-smi')
        if command:
            raw=subprocess.run([command,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3,check=True).stdout
            for line in raw.splitlines():
                model,memory,driver=[part.strip() for part in line.split(',')]
                h.accelerators.append({'kind':'NVIDIA-driver-reported','model':model,'vram_total':int(memory)*1024*1024,'driver':driver,'observed_kernel_dispatch':None})
    except (OSError,ValueError,subprocess.SubprocessError):pass
    h.hardware_reports_support = {k:(any(v in flags for v in values) if flags is not None else None) for k,values in ISA.items()}
    h.backend_reports_support = {'installed_versions':versions(), 'execution_providers':None}
    # No torch import, CUDA initialization or external process benchmark here.
    return h
