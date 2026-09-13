"""Read-only public Level Zero Sysman energy and temperature observations."""
import ctypes as c
import ctypes.util
import os
import time
from .thermal import ThermalSample


class LevelZeroSysman:
    def __init__(self, api=None):
        if api is None:
            library=ctypes.util.find_library('ze_loader')
            if not library:
                raise OSError('Level Zero loader unavailable')
            self.api=(c.WinDLL if os.name=='nt' else c.CDLL)(library)
            self.fixture=False
        else:
            self.api=api; self.fixture=True
        if not self.fixture:
            self.api.zesInit.argtypes=[c.c_uint32]; self.api.zesInit.restype=c.c_uint32
            for name in ('zesDriverGet','zesDeviceGet','zesDeviceEnumPowerDomains','zesDeviceEnumTemperatureSensors'):
                function=getattr(self.api,name)
                function.argtypes=([c.c_void_p] if name!='zesDriverGet' else [])+[c.POINTER(c.c_uint32),c.POINTER(c.c_void_p)]
                function.restype=c.c_uint32
        self._check(self.api.zesInit(0))

    @staticmethod
    def _check(status):
        if status != 0:
            raise OSError('Level Zero Sysman call failed: '+str(status))

    def _handles(self,name,parent=None):
        function=getattr(self.api,name); count=c.c_uint32()
        prefix=() if parent is None else (parent,)
        self._check(function(*prefix,c.byref(count),None))
        if count.value>256:
            raise ValueError('Sysman enumeration bound')
        if not count.value:
            return []
        handles=(c.c_void_p*count.value)(); capacity=count.value
        self._check(function(*prefix,c.byref(count),handles))
        if count.value>capacity:
            raise ValueError('Sysman enumeration changed')
        return list(handles)[:count.value]

    def samples(self):
        class Energy(c.Structure):
            _fields_=[('energy',c.c_uint64),('timestamp',c.c_uint64)]
        if not self.fixture:
            self.api.zesPowerGetEnergyCounter.argtypes=[c.c_void_p,c.POINTER(Energy)]
            self.api.zesPowerGetEnergyCounter.restype=c.c_uint32
            self.api.zesTemperatureGetState.argtypes=[c.c_void_p,c.POINTER(c.c_double)]
            self.api.zesTemperatureGetState.restype=c.c_uint32
        output=[]
        for driver in self._handles('zesDriverGet'):
            for device in self._handles('zesDeviceGet',driver):
                for domain in self._handles('zesDeviceEnumPowerDomains',device):
                    energy=Energy(); self._check(self.api.zesPowerGetEnergyCounter(domain,c.byref(energy)))
                    output.append(ThermalSample(str(domain),time.monotonic(),0,'Level-Zero-Sysman',energy_j=energy.energy/1e6,
                                  evidence='callable-fixture' if self.fixture else 'hardware-observed'))
                for sensor in self._handles('zesDeviceEnumTemperatureSensors',device):
                    temperature=c.c_double(); self._check(self.api.zesTemperatureGetState(sensor,c.byref(temperature)))
                    output.append(ThermalSample(str(sensor),time.monotonic(),0,'Level-Zero-Sysman',temperature_c=temperature.value,
                                  evidence='callable-fixture' if self.fixture else 'hardware-observed'))
        return output

    def sample(self):
        samples=self.samples()
        if not samples:
            raise OSError('no Sysman observations available')
        return samples[0]

    def close(self):
        # Sysman handles are driver-owned; there is no public destroy operation.
        pass
