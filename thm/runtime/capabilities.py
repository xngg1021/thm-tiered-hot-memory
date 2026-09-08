"""Explicit backend capability probe isolated from the library host."""
import json
import subprocess
import sys


def collect():
    from .hardware import versions
    installed=versions();out=[]
    if installed.get('torch'):
        import torch
        cuda=torch.cuda.is_available()
        out.append({'backend':'torch','cuda_available':cuda,'cuda_runtime':torch.version.cuda,'rocm_runtime':torch.version.hip,
                    'cpu_backend_capability':torch.backends.cpu.get_cpu_capability(),'observed_kernel_dispatch':None})
        if cuda:
            for i in range(torch.cuda.device_count()):
                p=torch.cuda.get_device_properties(i)
                out.append({'kind':'ROCm' if torch.version.hip else 'CUDA','device':i,'model':p.name,'vram_total':p.total_memory,
                    'vram_available':torch.cuda.mem_get_info(i)[0],'driver':None,'observed_kernel_dispatch':None})
        if hasattr(torch.backends,'mps'):out.append({'kind':'MPS','available':torch.backends.mps.is_available(),'observed_kernel_dispatch':None})
    if installed.get('onnxruntime') or installed.get('onnxruntime-gpu'):
        import onnxruntime as ort
        out.append({'backend':'onnxruntime','execution_providers':ort.get_available_providers(),'observed_kernel_dispatch':None})
    if installed.get('openvino'):
        import openvino as ov
        out.append({'backend':'openvino','available_devices':ov.Core().available_devices,'observed_kernel_dispatch':None})
    return out


def backend_probe(timeout=30):
    try:
        result=subprocess.run([sys.executable,'-m','thm.runtime.capabilities'],capture_output=True,text=True,timeout=timeout,check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError,ValueError):return [{'status':'unavailable-or-failed','observed_kernel_dispatch':None}]

if __name__=='__main__':print(json.dumps(collect()))
