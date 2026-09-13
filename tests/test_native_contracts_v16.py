import ctypes as c
import hashlib
import sys
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from thm.systems.thermal import NvmlThermalPowerProvider, AmdSmiThermalPowerProvider
from thm.systems.cuda import GpuVirtualResidency, DemandPagingProvider
from thm.systems.contracts import PermissionGate
from thm.systems.apple import MPSGraphBinding
from thm.systems.buffers import OwnedBuffer
from thm.systems.topology import DynamicTopologyFabric, TopologyObserver
from thm.runtime.fabric.hardware import DeviceNode, HardwareGraph


class NativeContracts(unittest.TestCase):
    def test_nvml_public_units_and_close(self):
        class API:
            def nvmlInit(self):self.active=True
            def nvmlShutdown(self):self.active=False
            def nvmlDeviceGetHandleByIndex(self,index):return index
            def nvmlDeviceGetUUID(self,h):return b'fixture-gpu'
            def nvmlDeviceGetPowerUsage(self,h):return 50000
            def nvmlDeviceGetTotalEnergyConsumption(self,h):return 2500
            def nvmlDeviceGetTemperature(self,h,sensor):return 70
            def nvmlDeviceGetClockInfo(self,h,kind):return 1500
            def nvmlDeviceGetUtilizationRates(self,h):return types.SimpleNamespace(gpu=25)
        api=API();provider=NvmlThermalPowerProvider(api=api)
        sample=provider.sample();provider.close()
        self.assertEqual(sample.power_w,50);self.assertEqual(sample.energy_j,2.5)
        self.assertEqual(sample.effective_clock_hz,1.5e9);self.assertEqual(sample.utilization,.25)
        self.assertEqual(sample.evidence,'callable-fixture');self.assertFalse(api.active)

    def test_amdsmi_public_metrics_do_not_invent_missing_power(self):
        class API:
            def amdsmi_init(self):pass
            def amdsmi_shut_down(self):pass
            def amdsmi_get_processor_handles(self):return [1]
            def amdsmi_get_gpu_metrics_info(self,h):return {'temperature_edge':65,'average_socket_power':75,'current_socket_power':65535}
        provider=AmdSmiThermalPowerProvider(api=API());sample=provider.sample();provider.close()
        self.assertIsNone(sample.power_w);self.assertEqual(sample.observed_average_power,75)

    def test_cuda_vmm_lifecycle_and_source_identity(self):
        ns=types.SimpleNamespace
        class Driver:
            fixture=True
            def __init__(self):
                self.calls=[]
                self.api=ns(CUmemAllocationProp=lambda:ns(location=ns()),CUmemAccessDesc=lambda:ns(),
                    CUmemAllocationType=ns(CU_MEM_ALLOCATION_TYPE_PINNED=1),CUmemLocationType=ns(CU_MEM_LOCATION_TYPE_DEVICE=1),
                    CUmemAllocationHandleType=ns(CU_MEM_HANDLE_TYPE_NONE=0),
                    CUmemAllocationGranularity_flags=ns(CU_MEM_ALLOC_GRANULARITY_MINIMUM=0),
                    CUmemAccess_flags=ns(CU_MEM_ACCESS_FLAGS_PROT_READWRITE=3))
            def call(self,name,*args):
                self.calls.append(name)
                return {'cuMemGetAllocationGranularity':4096,'cuMemAddressReserve':4096,'cuMemCreate':7}.get(name,())
        driver=Driver();residency=GpuVirtualResidency(driver,'source','index')
        with self.assertRaises(PermissionError):residency.reserve(100)
        gate=PermissionGate('S2',True,True,True,True,True)
        self.assertEqual(residency.reserve(100,gate)['size'],4096)
        self.assertEqual(residency.remap('source','index',gate)['generation'],2)
        with self.assertRaises(ValueError):residency.remap('other','index',gate)
        residency.close();self.assertEqual(driver.calls[-1],'cuMemAddressFree')

    def test_demand_paging_backing_is_owned_and_opt_in(self):
        class Binding:
            def register(self,key,size):pass
            def copy(self,key,offset,data):return data
            def unregister(self,key):self.unregistered=key
            def close(self):self.closed=True
        b=Binding()
        with self.assertRaises(PermissionError):DemandPagingProvider(b)
        provider=DemandPagingProvider(b,experimental=True);provider.register('shard',b'backing')
        self.assertEqual(provider.resolve('shard',1,3),b'ack')
        provider.close();self.assertTrue(b.closed)

    def test_registered_buffer_releases_registration_before_memory(self):
        class Binding:
            def register(self,address,size):self.address=address;return 1
            def unregister(self,token):self.removed=token
        b=Binding();buffer=OwnedBuffer(4096);buffer.register(b)
        self.assertFalse(buffer.receipt()['zero_copy'])
        buffer.close();self.assertEqual(b.removed,1)

    def test_mpsgraph_public_operation_contract_fixture(self):
        import numpy as np
        class Data:
            @staticmethod
            def dataWithBytes_length_(data,length):return data[:length]
        class Result:
            def __init__(self,value):self.value=value
            def mpsndarray(self):return self
            def readBytes_strideBytes_(self,out,strides):out[:]=self.value
        class Graph:
            @classmethod
            def alloc(cls):return cls()
            def init(self):return self
            def constantWithData_shape_dataType_(self,data,shape,dtype):return np.frombuffer(data,dtype=np.float32).reshape(shape)
            def matrixMultiplicationWithPrimaryTensor_secondaryTensor_name_(self,a,b,name):self.result=a@b;return 'tensor'
            def runWithFeeds_targetTensors_targetOperations_(self,feeds,tensors,ops):return {'tensor':Result(self.result)}
        foundation=types.ModuleType('Foundation');foundation.NSData=Data
        with patch.dict(sys.modules,Foundation=foundation):
            bridge=MPSGraphBinding(types.SimpleNamespace(MPSGraph=Graph))
            np.testing.assert_array_equal(bridge.matmul([[1,2]],[[3],[4]]),[[11]])
            bridge.close()

    def test_topology_observer_changes_epoch_on_native_capacity_change(self):
        class Provider:
            count=2
            def discover(self):return HardwareGraph([DeviceNode('cpu','cpu',True,True,True,{'count':self.count})],[],'fixture','0','fixture')
        provider=Provider();fabric=DynamicTopologyFabric();observer=TopologyObserver(fabric,provider)
        first=observer.poll();self.assertTrue(first['events']);epoch=fabric.epoch
        self.assertFalse(observer.poll()['events']);self.assertEqual(fabric.epoch,epoch)
        provider.count=4;self.assertTrue(observer.poll()['events']);self.assertGreater(fabric.epoch,epoch)


if __name__=='__main__':unittest.main()

class ResearchNativeContracts(unittest.TestCase):
    def test_userfault_defaults_off_and_lib_bpf_consumed_identity(self):
        from thm.systems.linux_research import UserfaultfdBinding,LibbpfProbe
        from thm.systems.contracts import PermissionGate
        with self.assertRaises(PermissionError):UserfaultfdBinding()
        gate=PermissionGate('S2',True,True,True,True,True)
        with self.assertRaisesRegex(ValueError,'identity'):
            LibbpfProbe(b'ELF','0'*64,lambda data:data,gate=gate,api=object())

    def test_libbpf_owned_callback_bound_and_cleanup(self):
        import ctypes as c
        import hashlib
        from thm.systems.linux_research import LibbpfProbe
        from thm.systems.contracts import PermissionGate
        class API:
            closed=[]
            def bpf_object__open_mem(self,data,size,opts):return 1
            def libbpf_get_error(self,ptr):return 0
            def bpf_object__load(self,obj):return 0
            def bpf_object__next_program(self,obj,previous):return 2 if previous is None else None
            def bpf_program__attach(self,program):return 3
            def bpf_object__find_map_fd_by_name(self,obj,name):return 4
            def ring_buffer__new(self,fd,callback,context,opts):self.callback=callback;return 5
            def ring_buffer__poll(self,ring,timeout):
                data=c.create_string_buffer(b'event');return self.callback(None,data,5)
            def ring_buffer__free(self,ring):self.closed.append('ring')
            def bpf_link__destroy(self,link):self.closed.append('link');return 0
            def bpf_object__close(self,obj):self.closed.append('object')
        api=API();gate=PermissionGate('S2',True,True,True,True,True)
        probe=LibbpfProbe(b'ELF',hashlib.sha256(b'ELF').hexdigest(),lambda data:{'kind':'scheduler','raw':data.decode()},gate=gate,api=api)
        self.assertEqual(probe.poll(.01,1)[0]['raw'],'event')
        self.assertEqual(probe.evidence,'callable-fixture')
        probe.close();self.assertEqual(api.closed,['ring','link','object'])

    def test_etw_unique_session_stop_and_xml_bound(self):
        from thm.systems.windows_trace import EtwProbe
        from thm.systems.contracts import PermissionGate
        gate=PermissionGate('S2',True,True,True,True,True)
        with patch('thm.systems.windows_trace.platform.system',return_value='Windows'),patch.dict(os.environ,{'SystemRoot':'C:/Windows'}):
            probe=EtwProbe('00000000-0000-0000-0000-000000000001',gate=gate)
        commands=[]
        def native(command,timeout=5):
            commands.append(command)
            if command[0]==probe.tracerpt:
                Path(command[command.index('-o')+1]).write_text('<Events><Event><EventID>42</EventID></Event></Events>')
        with patch.object(probe,'_run',native):
            rows=probe.poll(0,2);probe.close()
        self.assertEqual(rows[0]['fields']['EventID']['text'],'42')
        self.assertEqual(commands[1],[probe.logman,'stop',probe.name,'-ets'])
        self.assertFalse(probe.root.exists())
