"""Public driver observations, made only inside explicit native probes."""
import ctypes
import ctypes.util
import platform


def torch_runtime(torch, device):
    runtime = getattr(torch, 'version', None)
    facts = {'runtime': {k: getattr(runtime, k, None) for k in ('cuda', 'hip', 'maca')},
             'driver': None, 'device_capability': None}
    if device == 'mps':
        facts['driver'] = {'source': 'os-managed-metal', 'os_build': platform.version()}
    elif device == 'cuda' and not facts['runtime']['maca']:
        hip = bool(facts['runtime']['hip'])
        name, symbol = ('amdhip64', 'hipDriverGetVersion') if hip else ('cuda', 'cuDriverGetVersion')
        try:
            library = ctypes.CDLL(ctypes.util.find_library(name) or ('nvcuda.dll' if platform.system() == 'Windows' and not hip else 'lib'+name+'.so'))
            function = getattr(library, symbol); function.argtypes = [ctypes.POINTER(ctypes.c_int)]
            function.restype = ctypes.c_int; value = ctypes.c_int()
            if function(ctypes.byref(value)) == 0 and value.value > 0:
                facts['driver'] = {'source': symbol, 'version': value.value}
        except (OSError, AttributeError):
            pass
    api = getattr(torch, device, None)
    if api and hasattr(api, 'get_device_properties'):
        try:
            prop = api.get_device_properties(0)
            facts['device_capability'] = {k: getattr(prop, k, None) for k in
                                         ('name', 'total_memory', 'major', 'minor', 'multi_processor_count')}
        except (RuntimeError, TypeError, AttributeError):
            pass
    return facts
