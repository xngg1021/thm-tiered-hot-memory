"""Experimental CUDA Driver VMM. Representation identity survives backing changes."""
from dataclasses import dataclass
import importlib
from .contracts import PermissionGate, integer, nonempty


class CudaDriver:
    def __init__(self, api=None):
        self.api = api if api is not None else importlib.import_module('cuda.bindings.driver')
        self.fixture = api is not None
        self.call('cuInit', 0)

    def call(self, name, *args):
        status, *results = getattr(self.api, name)(*args)
        if int(status) != 0:
            raise RuntimeError(f'CUDA Driver {name} failed: {status}')
        return results[0] if len(results) == 1 else tuple(results)

    def probe(self, ordinal=0):
        device = self.call('cuDeviceGet', ordinal)
        vmm = self.call('cuDeviceGetAttribute', self.api.CUdevice_attribute.CU_DEVICE_ATTRIBUTE_VIRTUAL_ADDRESS_MANAGEMENT_SUPPORTED, device)
        uuid = self.call('cuDeviceGetUuid', device)
        return {'device': ordinal, 'identity': str(uuid), 'vmm': bool(vmm),
                'driver_version': self.call('cuDriverGetVersion'), 'evidence': 'callable-fixture' if self.fixture else 'native-executed'}


class GpuVirtualResidency:
    def __init__(self, driver, source_identity, index_identity, *, device=0):
        self.driver = driver
        self.source_identity = nonempty(source_identity)
        self.index_identity = nonempty(index_identity)
        self.device = device
        self.address = self.backing = None
        self.size = 0
        self.generation = 0
        self.mapped = False
        self.closed = False

    def reserve(self, size, gate=PermissionGate()):
        gate.require('S2')
        integer(size, minimum=1)
        if self.closed or self.address is not None:
            raise ValueError('closed/already reserved')
        api = self.driver.api
        prop = api.CUmemAllocationProp()
        prop.type = api.CUmemAllocationType.CU_MEM_ALLOCATION_TYPE_PINNED
        prop.location.type = api.CUmemLocationType.CU_MEM_LOCATION_TYPE_DEVICE
        prop.location.id = self.device
        prop.requestedHandleTypes = api.CUmemAllocationHandleType.CU_MEM_HANDLE_TYPE_NONE
        granularity = self.driver.call('cuMemGetAllocationGranularity', prop, api.CUmemAllocationGranularity_flags.CU_MEM_ALLOC_GRANULARITY_MINIMUM)
        self.size = ((size+granularity-1)//granularity)*granularity
        self.address = self.driver.call('cuMemAddressReserve', self.size, granularity, 0, 0)
        self.prop = prop
        try:
            self.map(gate)
        except BaseException:
            self.close()
            raise
        return self.receipt()

    def map(self, gate=PermissionGate()):
        gate.require('S2')
        if self.closed or self.address is None or self.mapped:
            raise ValueError('invalid map lifecycle')
        api = self.driver.api
        self.backing = self.driver.call('cuMemCreate', self.size, self.prop, 0)
        try:
            self.driver.call('cuMemMap', self.address, self.size, 0, self.backing, 0)
            self.mapped = True
            access = api.CUmemAccessDesc()
            access.location = self.prop.location
            access.flags = api.CUmemAccess_flags.CU_MEM_ACCESS_FLAGS_PROT_READWRITE
            self.driver.call('cuMemSetAccess', self.address, self.size, [access], 1)
            self.generation += 1
        except BaseException:
            self.unmap()
            raise

    def unmap(self):
        if self.mapped:
            self.driver.call('cuMemUnmap', self.address, self.size)
            self.mapped = False
        if self.backing is not None:
            self.driver.call('cuMemRelease', self.backing)
            self.backing = None

    def remap(self, source_identity, index_identity, gate=PermissionGate()):
        if (source_identity, index_identity) != (self.source_identity, self.index_identity):
            raise ValueError('source/index identity mismatch')
        gate.require('S2')
        self.unmap()
        self.map(gate)
        return self.receipt()

    def receipt(self):
        return {'source_identity': self.source_identity, 'index_identity': self.index_identity,
                'generation': self.generation, 'size': self.size, 'mapped': self.mapped,
                'content_restored': False, 'rebuild_required': True, 'exported_handle': None,
                'evidence': 'callable-fixture' if self.driver.fixture else 'native-executed',
                'hardware_acceptance': False}

    def close(self):
        self.unmap()
        if self.address is not None:
            self.driver.call('cuMemAddressFree', self.address, self.size)
            self.address = None
        self.closed = True


class DemandPagingProvider:
    """Opt-in userfaultfd research contract, with an owned backing snapshot."""
    def __init__(self, binding, *, experimental=False):
        if experimental is not True:
            raise PermissionError('userfaultfd research is disabled by default')
        self.binding = binding
        self.regions = {}

    def register(self, identity, backing):
        nonempty(identity)
        if identity in self.regions or not isinstance(backing, bytes) or len(backing) > 1048576:
            raise ValueError('bounded distinct backing required')
        self.binding.register(identity, len(backing))
        self.regions[identity] = backing

    def resolve(self, identity, offset, length):
        backing = self.regions[identity]
        integer(offset, maximum=len(backing))
        integer(length, minimum=1, maximum=len(backing)-offset)
        return self.binding.copy(identity, offset, backing[offset:offset+length])

    def close(self):
        for identity in tuple(self.regions):
            self.binding.unregister(identity)
            self.regions.pop(identity)
        self.binding.close()
