"""Power observations, sustainable envelopes and conservative backpressure."""
from dataclasses import asdict, dataclass, fields, replace
import importlib
import math
from pathlib import Path
import time
from typing import Protocol
from .contracts import finite, integer, nonempty

DURATION_WINDOWS = (.1, 1., 10., 60., 300.)


@dataclass(frozen=True)
class ThermalSample:
    device: str
    sample_timestamp: float
    sample_window: float
    source: str
    temperature_c: float | None = None
    power_w: float | None = None
    energy_j: float | None = None
    effective_clock_hz: float | None = None
    requested_clock_hz: float | None = None
    utilization: float | None = None
    thermal_headroom_c: float | None = None
    power_headroom_w: float | None = None
    throttle_reason: str | None = None
    throttle_residency: float | None = None
    fan_state: str | None = None
    performance_state: str | None = None
    energy_preference: str | None = None
    design_power: float | None = None
    configured_power_limit: float | None = None
    observed_average_power: float | None = None
    memory_bandwidth: float | None = None
    evidence: str = 'hardware-observed'

    def __post_init__(self):
        for name in ('device', 'source'):
            nonempty(getattr(self, name))
        for name, value in asdict(self).items():
            if isinstance(value, (int, float)):
                finite(value, name, -273.15 if name == 'temperature_c' else
                       -1e6 if name in ('thermal_headroom_c', 'power_headroom_w') else 0)
        for name in ('utilization', 'throttle_residency'):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError('fraction outside [0,1]')
        if self.evidence not in ('hardware-observed', 'simulated', 'callable-fixture', 'unobservable-public-api'):
            raise ValueError('invalid thermal evidence')

    def public(self):
        return {**asdict(self), 'energy_wh': None if self.energy_j is None else self.energy_j / 3600,
                'observed_instant_power': self.power_w, 'energy_integral': self.energy_j}


class ThermalPowerProvider(Protocol):
    def sample(self) -> ThermalSample: ...
    def close(self): ...


def read_number(path, divisor=1):
    try:
        with Path(path).open() as stream:
            text=stream.read(129)
        if len(text)>128:return None
        value = float(text.strip()) / divisor
        return value if math.isfinite(value) else None
    except (OSError, ValueError):
        return None


class LinuxThermalPowerProvider:
    """One sensor per sample; never combine unrelated sockets/zones."""
    def __init__(self, root='/sys'):
        self.root = Path(root)

    def samples(self):
        stamp = time.monotonic()
        result = []
        for zone in sorted((self.root / 'class/thermal').glob('thermal_zone*'))[:256]:
            result.append(ThermalSample(str(zone), stamp, 0, 'thermal-sysfs',
                                        temperature_c=read_number(zone/'temp', 1000)))
        for hwmon in sorted((self.root/'class/hwmon').glob('hwmon*'))[:256]:
            for sensor in sorted(hwmon.glob('power*_input'))[:64]:
                result.append(ThermalSample(str(sensor), stamp, 0, 'hwmon', power_w=read_number(sensor, 1e6)))
            for sensor in sorted(hwmon.glob('temp*_input'))[:64]:
                result.append(ThermalSample(str(sensor), stamp, 0, 'hwmon', temperature_c=read_number(sensor, 1000)))
        for energy in sorted((self.root/'class/powercap').glob('*/energy_uj'))[:256]:
            result.append(ThermalSample(str(energy.parent), stamp, 0, 'powercap-rapl', energy_j=read_number(energy, 1e6),
                configured_power_limit=read_number(energy.parent/'constraint_0_power_limit_uw', 1e6)))
        for freq in sorted((self.root/'devices/system/cpu/cpufreq').glob('policy*'))[:1024]:
            # scaling_cur_freq can be a requested P-state. Only cpuinfo_cur_freq is observed.
            try:
                preference = (freq/'energy_performance_preference').read_text()[:128].strip()
            except OSError:
                preference = None
            result.append(ThermalSample(str(freq), stamp, 0, 'cpufreq',
                effective_clock_hz=read_number(freq/'cpuinfo_cur_freq', .001),
                requested_clock_hz=read_number(freq/'scaling_cur_freq', .001), energy_preference=preference))
        if self.root!=Path('/sys'):
            result=[replace(row,evidence='callable-fixture') for row in result]
        return result

    def sample(self):
        rows = self.samples()
        return rows[0] if rows else ThermalSample('linux', time.monotonic(), 0, 'public-sysfs', evidence='unobservable-public-api')

    def close(self):
        pass


class NvmlThermalPowerProvider:
    """Direct NVML calls. Optional pynvml package; no command text parsing."""
    def __init__(self, index=0, api=None):
        self.api = api if api is not None else importlib.import_module('pynvml')
        self.fixture = api is not None
        self.api.nvmlInit()
        self.closed = False
        try:
            self.handle = self.api.nvmlDeviceGetHandleByIndex(index)
        except BaseException:
            self.close()
            raise

    def _get(self, name, *args, scale=1):
        try:
            value = getattr(self.api, name)(self.handle, *args)
            return value / scale if isinstance(value, (int, float)) else value
        except Exception as exc:
            if 'GpuIsLost' in type(exc).__name__ or 'GPU_IS_LOST' in str(exc):
                raise RuntimeError('device-lost') from exc
            return None

    def sample(self):
        if self.closed:
            raise ValueError('closed telemetry provider')
        utilization = self._get('nvmlDeviceGetUtilizationRates')
        uuid = self._get('nvmlDeviceGetUUID')
        if isinstance(uuid, bytes):
            uuid = uuid.decode()
        return ThermalSample(str(uuid or 'nvidia-unknown'), time.monotonic(), 0, 'NVML',
            temperature_c=self._get('nvmlDeviceGetTemperature', 0),
            power_w=self._get('nvmlDeviceGetPowerUsage', scale=1000),
            energy_j=self._get('nvmlDeviceGetTotalEnergyConsumption', scale=1000),
            configured_power_limit=self._get('nvmlDeviceGetEnforcedPowerLimit', scale=1000),
            effective_clock_hz=self._get('nvmlDeviceGetClockInfo', 0, scale=1e-6),
            utilization=None if utilization is None else utilization.gpu / 100,
            throttle_reason=str(self._get('nvmlDeviceGetCurrentClocksThrottleReasons')),
            evidence='callable-fixture' if self.fixture else 'hardware-observed')

    def close(self):
        if not getattr(self, 'closed', True):
            self.api.nvmlShutdown()
            self.closed = True


class AmdSmiThermalPowerProvider:
    def __init__(self, index=0, api=None):
        self.api = api if api is not None else importlib.import_module('amdsmi')
        self.fixture = api is not None
        self.api.amdsmi_init()
        self.closed = False
        try:
            self.handle = self.api.amdsmi_get_processor_handles()[index]
        except BaseException:
            self.close()
            raise

    def sample(self):
        if self.closed:
            raise ValueError('closed telemetry provider')
        metrics = self.api.amdsmi_get_gpu_metrics_info(self.handle)
        # AMD SMI public metrics use watts and MHz for these named fields.
        def number(key, factor=1):
            value = metrics.get(key)
            return value * factor if isinstance(value, (int, float)) and value not in (65535, 4294967295) else None
        return ThermalSample(str(self.handle), time.monotonic(), 0, 'AMD-SMI',
            temperature_c=number('temperature_edge'), power_w=number('current_socket_power'),
            observed_average_power=number('average_socket_power'), effective_clock_hz=number('current_gfxclk', 1e6),
            utilization=number('average_gfx_activity', .01), throttle_reason=str(metrics.get('throttle_status')),
            evidence='callable-fixture' if self.fixture else 'hardware-observed')

    def close(self):
        if not self.closed:
            self.api.amdsmi_shut_down()
            self.closed = True


def quantiles(values):
    values = sorted(finite(x) for x in values)
    if not values:
        return {key: None for key in ('p50', 'p90', 'p95', 'p99', 'p99.9', 'max')}
    out = {}
    for name, fraction in (('p50', .5), ('p90', .9), ('p95', .95), ('p99', .99), ('p99.9', .999)):
        position = (len(values)-1)*fraction
        lo = int(position)
        hi = min(lo+1, len(values)-1)
        out[name] = values[lo] + (values[hi]-values[lo])*(position-lo)
    return {**out, 'max': values[-1]}


@dataclass(frozen=True)
class SustainablePerformanceEnvelope:
    device: str
    workload: str
    concurrency: int
    batch_size: int
    duration: float
    thermal_state: str
    power_state: str
    latencies: tuple[float, ...]
    queue_wait: tuple[float, ...] = ()
    thermal: tuple[ThermalSample, ...] = ()
    topology_epoch: int = 0

    def __post_init__(self):
        integer(self.concurrency, minimum=1)
        integer(self.batch_size, minimum=1)
        integer(self.topology_epoch)
        finite(self.duration, minimum=1e-9)
        if self.thermal_state not in ('cold', 'warm', 'thermally_soaked'):
            raise ValueError('invalid soak state')
        if len(self.latencies) > 1_000_000 or len(self.queue_wait)>1_000_000 or len(self.thermal) > 10000:
            raise ValueError('envelope bounds')
        if any(row.device!=self.device for row in self.thermal):
            raise ValueError('thermal envelope requires one device identity')
        for value in self.latencies + self.queue_wait:
            finite(value)

    def public(self):
        def mean(name):
            vals = [getattr(t, name) for t in self.thermal if getattr(t, name) is not None]
            return sum(vals)/len(vals) if vals else None
        energy = None
        counters=[row for row in self.thermal if row.energy_j is not None]
        if len(counters)>=2 and len({row.source for row in counters})==1:
            continuous=all(after.sample_timestamp>before.sample_timestamp and after.energy_j>=before.energy_j
                           for before,after in zip(counters,counters[1:]))
            if continuous:energy=counters[-1].energy_j-counters[0].energy_j
        return {'device': self.device, 'workload': self.workload, 'concurrency': self.concurrency,
            'batch_size': self.batch_size, 'duration': self.duration, 'thermal_state': self.thermal_state,
            'power_state': self.power_state, 'topology_epoch': self.topology_epoch,
            'operations': len(self.latencies), 'throughput': len(self.latencies)/self.duration,
            **quantiles(self.latencies), 'queue_wait': quantiles(self.queue_wait),
            'effective_clock': mean('effective_clock_hz'), 'temperature': mean('temperature_c'),
            'power': mean('power_w'), 'energy_per_operation': energy/len(self.latencies) if energy is not None and self.latencies else None,
            'throttle_residency': mean('throttle_residency'), 'memory_bandwidth': mean('memory_bandwidth'),
            'power_sources': sorted({t.source for t in self.thermal}),
            'energy_attribution': 'device-counter-window divided by completed operations; workload exclusivity not established',
            'evidence_classes': sorted({t.evidence for t in self.thermal})}


class ThermalActuator:
    """Explicit S2 controls with read-before-write, rollback and audit receipts."""
    CONTROLS=('power-cap','clock-range','fan-policy','cpu-quota','gpu-frequency','device-allocation')

    def __init__(self,binding):
        self.binding=binding
        self.previous=[]

    def apply(self,control,value,gate):
        gate.require('S2')
        if control not in self.CONTROLS or not self.binding.supports(control):
            raise ValueError('unsupported native actuation')
        previous=self.binding.read(control)
        self.binding.validate(control,value)
        self.previous.append((control,previous))
        try:
            self.binding.write(control,value)
            observed=self.binding.read(control)
        except BaseException:
            self.rollback()
            raise
        return {'control':control,'requested':value,'observed':observed,'previous':previous,
                'level':'S2','opt_in':True,'rollback_available':True,'evidence':self.binding.evidence}

    def rollback(self):
        while self.previous:
            control,value=self.previous[-1]
            self.binding.write(control,value)
            self.previous.pop()


class NvmlPowerControl:
    def __init__(self,telemetry):
        self.telemetry=telemetry
        self.evidence='callable-fixture' if telemetry.fixture else 'native-executed'

    def supports(self,control):
        return control=='power-cap' and hasattr(self.telemetry.api,'nvmlDeviceSetPowerManagementLimit')

    def read(self,control):
        if not self.supports(control):raise ValueError('unsupported NVML control')
        return self.telemetry.api.nvmlDeviceGetPowerManagementLimit(self.telemetry.handle)/1000

    def validate(self,control,value):
        finite(value)
        low,high=self.telemetry.api.nvmlDeviceGetPowerManagementLimitConstraints(self.telemetry.handle)
        if not low<=value*1000<=high:raise ValueError('power cap outside device constraints')

    def write(self,control,value):
        self.validate(control,value)
        self.telemetry.api.nvmlDeviceSetPowerManagementLimit(self.telemetry.handle,int(value*1000))


def operating_points(envelopes):
    rows = sorted((e.public() for e in envelopes), key=lambda e: e['concurrency'])
    if len({(r['device'], r['workload'], r['batch_size'], r['duration'], r['thermal_state'], r['topology_epoch']) for r in rows}) > 1:
        raise ValueError('operating-point comparison requires a common workload/state/epoch')
    result = []
    for before, after in zip(rows, rows[1:]):
        names = []
        if before['throughput'] and after['throughput']/before['throughput'] < 1.1:
            names.append('throughput-knee')
        if before['p95'] and after['p95']/before['p95'] > 1.5:
            names.append('latency-cliff')
        if after['throttle_residency'] is not None and after['throttle_residency'] > .1:
            names.append('thermal-cliff')
        if after['power'] is not None and before['power'] and after['power']/before['power'] < 1.03 and 'throughput-knee' in names:
            names.append('power-plateau')
        if after['memory_bandwidth'] is not None and before['memory_bandwidth'] and after['memory_bandwidth']/before['memory_bandwidth'] < 1.03:
            names.append('bandwidth-saturation')
        if after['queue_wait']['p95'] and after['p95'] and after['queue_wait']['p95'] > after['p95'] / 2:
            names.append('queueing-collapse')
        result.extend({'name': name, 'concurrency': after['concurrency']} for name in names)
    return result


def duration_sweep(durations=DURATION_WINDOWS, *, full_research=False):
    values = tuple(finite(d, minimum=.001) for d in durations)
    if not values or len(values) > 100 or (not full_research and (max(values) > 10 or sum(values) > 15)):
        raise ValueError('long duration sweep requires --full-research')
    return values


def thermal_backpressure(samples, *, now, max_age=5., horizon=2.):
    finite(now)
    finite(horizon)
    finite(max_age)
    samples = tuple(samples)[-16:]
    if not samples or not 0 <= now-samples[-1].sample_timestamp <= max_age:
        return {'background_share': 0., 'reason': 'unknown-or-stale', 'prediction': None}
    last = samples[-1]
    if last.thermal_headroom_c is None:
        return {'background_share': .1, 'reason': 'headroom-unobservable', 'prediction': None}
    slope = 0.
    if len(samples) > 1:
        previous = samples[-2]
        dt = last.sample_timestamp-previous.sample_timestamp
        if previous.device != last.device or dt <= 0:
            return {'background_share': 0., 'reason': 'incomparable-trace', 'prediction': None}
        if previous.temperature_c is not None and last.temperature_c is not None:
            slope = max(0., min(10., (last.temperature_c-previous.temperature_c)/dt))
    predicted = last.thermal_headroom_c - slope * min(horizon, 5.)
    throttle = last.throttle_residency or 0.
    share = 0. if predicted <= 3 or throttle > .05 else .25 if predicted <= 10 else .5
    return {'background_share': share, 'reason': 'bounded-trajectory', 'prediction': predicted}
