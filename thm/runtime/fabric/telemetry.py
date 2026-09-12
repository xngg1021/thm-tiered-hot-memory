"""Optional public vendor counters. Board-wide energy is never per-query energy."""
import math


def number(value, scale=1):
    return value*scale if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


class NVMLTelemetry:
    def __init__(self, spec=None):
        self.spec = spec; self.api = None

    def probe(self):
        import pynvml
        self.api = pynvml; pynvml.nvmlInit()
        return {'availability': 'available', 'provider': 'nvidia.nvml',
                'devices': ['nvml:'+str(i) for i in range(pynvml.nvmlDeviceGetCount())],
                'driver_runtime': str(pynvml.nvmlSystemGetDriverVersion()), 'observed_kernel_dispatch': None}

    def telemetry(self, device_index=0):
        if self.api is None:
            self.probe()
        api = self.api; handle = api.nvmlDeviceGetHandleByIndex(device_index)
        def get(function, scale=1):
            try:
                return number(function(handle), scale)
            except Exception:
                return None
        try:
            utilization = number(api.nvmlDeviceGetUtilizationRates(handle).gpu)
        except Exception:
            utilization = None
        try:
            memory = api.nvmlDeviceGetMemoryInfo(handle)
            used, total = memory.used, memory.total
        except Exception:
            used = total = None
        return {'gpu_utilization': utilization, 'vram_used': used, 'vram_total': total,
                'power_watts': get(api.nvmlDeviceGetPowerUsage, .001),
                'cumulative_board_joules': get(api.nvmlDeviceGetTotalEnergyConsumption, .001),
                'energy_source': 'NVML-board-counter', 'query_joules': None, 'observed_kernel_dispatch': None}

    def close(self):
        if self.api:
            self.api.nvmlShutdown(); self.api = None

    def topology(self):
        """Public NVML parent/partition observations; no raw UUIDs leave this API."""
        from .contracts import identity
        if self.api is None:
            self.probe()
        api = self.api; nodes, edges = [], []
        for i in range(api.nvmlDeviceGetCount()):
            handle = api.nvmlDeviceGetHandleByIndex(i)
            parent = 'nvml:' + str(i)
            nodes.append({'id': parent, 'kind': 'physical-device'})
            try:
                mode, pending = api.nvmlDeviceGetMigMode(handle)
                maximum = api.nvmlDeviceGetMaxMigDeviceCount(handle) if mode else 0
            except Exception:
                nodes[-1]['partition_observation'] = 'unknown'
                continue
            nodes[-1].update(partition_mode=bool(mode), pending_mode=bool(pending))
            for slot in range(maximum):
                try:
                    child = api.nvmlDeviceGetMigDeviceHandleByIndex(handle, slot)
                    raw = api.nvmlDeviceGetUUID(child)
                    cid = identity(raw.decode() if isinstance(raw, bytes) else str(raw))
                    nodes.append({'id': cid, 'kind': 'observed-MIG-partition'})
                    edges.append({'source': parent, 'target': cid, 'relation': 'partition'})
                except Exception:
                    continue
        return {'nodes': nodes, 'edges': edges, 'resource_isolation_accepted': False}


class AMDSystemTelemetry:
    def __init__(self, spec=None):
        self.spec = spec; self.api = None

    def probe(self):
        import amdsmi
        self.api = amdsmi; amdsmi.amdsmi_init()
        self.handles = amdsmi.amdsmi_get_processor_handles()
        try:
            driver = str(amdsmi.amdsmi_get_gpu_driver_info(self.handles[0]).get('driver_version')) if self.handles else None
        except Exception:
            driver = None
        return {'availability': 'available' if self.handles else 'device-unavailable',
                'provider': 'amd.smi', 'devices': ['amdsmi:'+str(i) for i in range(len(self.handles))],
                'driver_identity': driver,
                'observed_kernel_dispatch': None}

    def telemetry(self, device_index=0):
        if self.api is None:
            self.probe()
        try:
            activity = self.api.amdsmi_get_gpu_activity(self.handles[device_index])
        except Exception:
            activity = {}
        return {'gpu_utilization': number(activity.get('gfx_activity')),
                'memory_utilization': number(activity.get('umc_activity')),
                'query_joules': None, 'energy_source': None, 'source': 'AMD-SMI', 'observed_kernel_dispatch': None}

    def close(self):
        if self.api:
            self.api.amdsmi_shut_down(); self.api = None
