"""Thread-safe hotplug state machine with epoch/generation-bound admission."""
from dataclasses import asdict, dataclass, field
from enum import Enum
import threading
from .contracts import digest, finite, integer, nonempty


class DeviceState(str, Enum):
    ABSENT = 'ABSENT'
    PRESENT = 'PRESENT'
    PROBING = 'PROBING'
    ONLINE = 'ONLINE'
    DRAINING = 'DRAINING'
    OFFLINE = 'OFFLINE'
    LOST = 'LOST'
    RECOVERING = 'RECOVERING'
    QUARANTINED = 'QUARANTINED'


EVENTS = ('cpu-online', 'cpu-offline', 'memory-online', 'memory-offline', 'gpu-appeared',
          'gpu-disappeared', 'gpu-reset', 'gpu-lost', 'egpu', 'usb-accelerator',
          'thunderbolt', 'nvme-hotplug', 'storage-disappeared', 'storage-reconnect',
          'network-storage-reconnect', 'sleep', 'wake', 'dock-reconnect',
          'driver-reload', 'vm-resize', 'provider-appeared', 'provider-disappeared', 'reprobe')


@dataclass(frozen=True)
class TopologyEvent:
    kind: str
    device_id: str
    sequence: int
    fingerprint: str = ''
    driver: str = 'unknown'
    capabilities: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in EVENTS:
            raise ValueError('unknown topology event')
        nonempty(self.device_id)
        integer(self.sequence)
        if len(self.capabilities) > 256:
            raise ValueError('capability bound')


@dataclass(frozen=True)
class ResidentHandle:
    device_id: str
    topology_epoch: int
    generation: int
    fingerprint: str
    source_identity: str
    index_identity: str
    serial: int


@dataclass
class Device:
    identity: str
    generation: int = 0
    state: DeviceState = DeviceState.ABSENT
    fingerprint: str = ''
    driver: str = 'unknown'
    capabilities: tuple[str, ...] = ()
    health: str = 'unknown'
    qualified: bool = False
    inflight: dict = field(default_factory=dict)


class DynamicTopologyFabric:
    def __init__(self, *, max_devices=1024, max_inflight=4096):
        integer(max_devices, minimum=1, maximum=10000)
        integer(max_inflight, minimum=1, maximum=100000)
        self.max_devices, self.max_inflight = max_devices, max_inflight
        self.epoch = 0
        self.devices = {}
        self._lock = threading.RLock()
        self._sequence = {}
        self._serial = 0
        self._sessions = {}
        self._handles = {}
        self.failures = []

    def _publish(self):
        for device in self.devices.values():
            self._cancel(device, 'topology-epoch-invalidated')
        self.epoch += 1
        self._handles.clear()

    def event(self, event):
        with self._lock:
            if event.sequence <= self._sequence.get(event.device_id, -1):
                raise ValueError('out-of-order topology event')
            if event.device_id not in self.devices and len(self.devices) >= self.max_devices:
                raise ValueError('device bound')
            device = self.devices.setdefault(event.device_id, Device(event.device_id))
            self._sequence[event.device_id] = event.sequence
            if event.kind in ('gpu-disappeared', 'gpu-reset', 'gpu-lost', 'storage-disappeared', 'provider-disappeared'):
                device.state = DeviceState.LOST
                self._cancel(device, 'device-lost')
                device.state = DeviceState.QUARANTINED
                device.health = 'lost'
            elif event.kind in ('cpu-offline', 'memory-offline', 'sleep'):
                device.state = DeviceState.DRAINING
                self._cancel(device, event.kind)
                device.state = DeviceState.OFFLINE
                device.health = 'offline'
            else:
                self._cancel(device, 'topology-reprobe')
                device.state = DeviceState.RECOVERING if device.generation else DeviceState.PRESENT
                device.generation += 1
                device.fingerprint = event.fingerprint or digest(asdict(event))
                device.driver = event.driver
                device.capabilities = tuple(event.capabilities)
                device.state = DeviceState.PROBING
                device.health = 'requalification-required'
            device.qualified = False
            self._publish()
            return self.snapshot()

    def qualify(self, device_id, generation, fingerprint, *, passed):
        with self._lock:
            device = self.devices[device_id]
            if device.state != DeviceState.PROBING or generation != device.generation or fingerprint != device.fingerprint:
                raise ValueError('stale requalification')
            if type(passed) is not bool:
                raise ValueError('boolean qualification required')
            device.qualified = passed
            device.state = DeviceState.ONLINE if passed else DeviceState.QUARANTINED
            device.health = 'healthy' if passed else 'failed-qualification'
            self._publish()

    def open_session(self, session_id, device_id=None):
        with self._lock:
            nonempty(session_id)
            if session_id in self._sessions:
                raise ValueError('session already pinned')
            if len(self._sessions) >= self.max_inflight:
                raise ValueError('session bound')
            device = self.devices.get(device_id)
            pin = (device_id, device.generation) if device and device.state == DeviceState.ONLINE and device.qualified else ('reference-cpu', 0)
            self._sessions[session_id] = pin
            return pin

    def close_session(self, session_id):
        with self._lock:
            self._sessions.pop(session_id, None)

    def admit(self, session_id, source_identity, index_identity):
        with self._lock:
            nonempty(source_identity)
            nonempty(index_identity)
            device_id, generation = self._sessions[session_id]
            device = self.devices.get(device_id)
            if device is None or device.state != DeviceState.ONLINE or generation != device.generation or not device.qualified:
                self._sessions[session_id] = ('reference-cpu', 0)
                return None
            if sum(len(d.inflight) for d in self.devices.values()) >= self.max_inflight:
                raise OverflowError('admission bound')
            self._serial += 1
            handle = ResidentHandle(device_id, self.epoch, generation, device.fingerprint,
                                    source_identity, index_identity, self._serial)
            device.inflight[handle.serial] = handle
            self._handles[handle.serial] = handle
            return handle

    def validate(self, handle):
        with self._lock:
            device = self.devices.get(handle.device_id)
            if (not device or self._handles.get(handle.serial) != handle or handle.topology_epoch != self.epoch or
                    handle.generation != device.generation or handle.fingerprint != device.fingerprint or
                    device.state not in (DeviceState.ONLINE, DeviceState.DRAINING)):
                raise ValueError('stale or foreign resident handle')
            return True

    def complete(self, handle):
        with self._lock:
            self.validate(handle)
            self.devices[handle.device_id].inflight.pop(handle.serial)
            self._handles.pop(handle.serial)

    def begin_drain(self, device_id):
        with self._lock:
            device = self.devices[device_id]
            if device.state != DeviceState.ONLINE:
                raise ValueError('only online devices drain')
            # Existing work retains its epoch until bounded completion/cancellation.
            device.state = DeviceState.DRAINING
            return tuple(device.inflight.values())

    def finish_drain(self, device_id, *, deadline, now):
        finite(deadline)
        finite(now)
        with self._lock:
            device = self.devices[device_id]
            if device.state != DeviceState.DRAINING:
                raise ValueError('drain required')
            if device.inflight and now < deadline:
                return {'status': 'draining', 'remaining': len(device.inflight)}
            rebuild = tuple(h.source_identity for h in device.inflight.values())
            self._cancel(device, 'drain-deadline')
            device.qualified = False
            device.state = DeviceState.OFFLINE
            self._publish()
            return {'status': 'offline', 'rebuild_from_source': rebuild, 'fallback': 'reference-cpu', 'epoch': self.epoch}

    def _cancel(self, device, reason):
        for serial in device.inflight:
            self.failures.append({'serial': serial, 'reason': reason, 'fallback': 'reference-cpu'})
            self._handles.pop(serial, None)
        self.failures = self.failures[-self.max_inflight:]
        device.inflight.clear()

    def snapshot(self):
        with self._lock:
            rows = [{**asdict(d), 'state': d.state.value, 'inflight': len(d.inflight)} for d in self.devices.values()]
            return {'schema': 'thm-topology/1', 'topology_epoch': self.epoch,
                    'topology_identity': digest([{k:v for k,v in row.items() if k!='inflight'} for row in rows]), 'devices': rows}


class TopologyObserver:
    """Compare native provider observations; changed capabilities require reprobe."""
    def __init__(self,fabric,provider=None):
        self.evidence='hardware-observed' if provider is None else getattr(provider,'evidence','callable-fixture')
        if provider is None:
            from thm.runtime.fabric.hardware import HostDeviceProvider
            provider=HostDeviceProvider()
        self.fabric,self.provider=fabric,provider
        self.previous={}
        self.sequence=0

    def poll(self):
        graph=self.provider.discover()
        rows={node.id:asdict(node) for node in graph.nodes}
        if len(rows)>self.fabric.max_devices:
            raise ValueError('native topology observation bound')
        changes=[]
        for key in sorted(set(rows)|set(self.previous)):
            if rows.get(key)==self.previous.get(key):
                continue
            self.sequence+=1
            if key not in rows:
                event=TopologyEvent('provider-disappeared',key,self.sequence)
            else:
                row=rows[key]
                event=TopologyEvent('reprobe',key,self.sequence,digest(row),str(row['properties'].get('driver','unknown')),
                                    (row['kind'],))
            self.fabric.event(event)
            changes.append(asdict(event))
        self.previous=rows
        return {'events':changes,'topology':self.fabric.snapshot(),'evidence':self.evidence,
                'qualification_automatic':False}
