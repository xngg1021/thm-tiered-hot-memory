"""Declarative provider families; no vendor imports or large core dispatch chain."""
from .contracts import ProviderSpec


def spec(name, vendor, family, cls, *, dependencies=(), devices=('cpu',), os=('Linux', 'Windows', 'Darwin'),
         operations=('inference',), options=(), compile=False, resident=False, maturity=4, priority=0):
    return ProviderSpec(name, vendor, family, 'thm.runtime.fabric.' + cls,
                        dependencies, devices, ('fp32',), operations, os, priority,
                        compile=compile, resident_handle=resident, telemetry=True, maturity=maturity,
                        options=tuple(options))


BUILTINS = [
    spec('host.device', 'generic', 'os', 'hardware:HostDeviceProvider', operations=('device',)),
    spec('host.exact', 'generic', 'numpy', 'indexes:ExactHost', dependencies=('numpy',), operations=('vector-search',), resident=True, priority=100),
    spec('host.hnsw', 'generic', 'hnswlib', 'indexes:HNSWGeneric', dependencies=('hnswlib',), operations=('vector-search',), resident=True),
    spec('host.transfer', 'generic', 'memory', 'transfer:HostTransfer', operations=('transfer',)),
    spec('cpu.inference', 'generic', 'torch', 'inference:TorchInference', dependencies=('torch', 'sentence-transformers'), options=(('device', 'cpu'),)),
]

# Each architecture has its own capability/heuristic options; this is not a grid.
for vendor, device, extension, runtime, systems, extra in [
    ('nvidia', 'cuda', None, 'CUDA', ('Linux', 'Windows'), (('require_cuda', True),)),
    ('amd', 'cuda', None, 'ROCm-HIP', ('Linux', 'Windows'), (('require_hip', True),)),
    ('intel', 'xpu', None, 'XPU', ('Linux', 'Windows'), ()),
    ('apple', 'mps', None, 'MPS', ('Darwin',), ()),
    ('ascend', 'npu', 'torch_npu', 'CANN-TorchNPU', ('Linux',), ()),
    ('musa', 'musa', 'torch_musa', 'MUSA', ('Linux',), ()),
    ('cambricon', 'mlu', 'torch_mlu', 'CNRT-CNNL', ('Linux',), ()),
    ('metax', 'cuda', None, 'MXMACA-mcPyTorch', ('Linux',), (('require_maca', True),)),
]:
    options = (('device', device), ('extension', extension)) + extra
    deps = ('torch',) + ((extension.replace('_', '-'),) if extension else ())
    BUILTINS.extend([
        spec(vendor+'.inference', vendor, runtime, 'inference:TorchInference', dependencies=deps+('sentence-transformers',), devices=('gpu', 'npu'), os=systems, options=options),
        spec(vendor+'.exact', vendor, runtime, 'indexes:ExactAccelerator', dependencies=deps, devices=('gpu', 'npu'), os=systems, operations=('vector-search',), options=options, resident=True),
        spec(vendor+'.transfer', vendor, runtime, 'transfer:TorchTransfer', dependencies=deps, devices=('gpu', 'npu'), os=systems, operations=('transfer',), options=options),
    ])

BUILTINS.extend([
    spec('nvidia.tensorrt-rtx', 'nvidia', 'TensorRT-RTX-EP-ABI', 'inference:OrtInference', dependencies=('onnxruntime',), devices=('gpu',), os=('Linux', 'Windows'), options=(('ep', 'NvTensorRTRTXExecutionProvider'),), compile=True),
    spec('amd.migraphx', 'amd', 'MIGraphX', 'inference:MIGraphXInference', dependencies=('migraphx',), devices=('gpu',), os=('Linux',), compile=True),
    spec('amd.migraphx-ep', 'amd', 'MIGraphX-EP', 'inference:OrtInference', dependencies=('onnxruntime',), devices=('gpu',), os=('Linux', 'Windows'), options=(('ep', 'MIGraphXExecutionProvider'),), compile=True),
    spec('intel.openvino', 'intel', 'OpenVINO-AUTO', 'inference:OpenVINOInference', dependencies=('openvino',), devices=('cpu', 'gpu', 'npu'), options=(('device', 'AUTO'),), compile=True),
    spec('apple.coreml', 'apple', 'CoreML', 'inference:CoreMLInference', dependencies=('coremltools',), devices=('cpu', 'gpu', 'npu'), os=('Darwin',), compile=True),
    spec('qualcomm.qnn', 'qualcomm', 'QNN-HTP', 'inference:OrtInference', dependencies=('onnxruntime-qnn',), devices=('npu',), os=('Windows', 'Linux'), options=(('ep', 'QNNExecutionProvider'),), compile=True),
    spec('windows.directml', 'microsoft', 'DirectML', 'inference:OrtInference', dependencies=('onnxruntime-directml',), devices=('gpu',), os=('Windows',), options=(('ep', 'DmlExecutionProvider'),)),
])

for algorithm in ('brute_force', 'cagra', 'ivf_flat', 'ivf_pq', 'vamana'):
    BUILTINS.append(spec('nvidia.cuvs.'+algorithm, 'nvidia', 'cuVS', 'native:CuvsProvider', dependencies=('cuvs-cu12',),
                         devices=('gpu',), os=('Linux',), operations=('vector-search',), resident=True,
                         options=(('algorithm', algorithm),), maturity=2 if algorithm == 'vamana' else 4))
BUILTINS.extend([
    spec('metax.mcfaiss', 'metax', 'MXMACA-mcFaiss', 'native:McFaissProvider', devices=('gpu',), os=('Linux',), operations=('vector-search',), resident=True),
    spec('windows.catalog', 'microsoft', 'WindowsML', 'native:WindowsMLCatalog', os=('Windows',), devices=('gpu', 'npu', 'cpu'), operations=('device', 'inference'), maturity=1),
])

# Public C/ObjC extension seams have explicit maturity, never masquerade as executable adapters.
for name, vendor, family, libraries in [
    ('nvidia.cublaslt', 'nvidia', 'cuBLASLt', ('cublasLt',)),
    ('nvidia.cufile', 'nvidia', 'cuFile-GDS', ('cufile',)),
    ('amd.hipblaslt', 'amd', 'hipBLASLt', ('hipblaslt',)),
    ('amd.rocblas', 'amd', 'rocBLAS', ('rocblas',)),
    ('intel.onednn', 'intel', 'oneDNN', ('dnnl',)),
    ('intel.onemkl', 'intel', 'oneMKL', ('mkl_rt',)),
    ('intel.levelzero', 'intel', 'LevelZero', ('ze_loader',)),
    ('apple.mpsgraph', 'apple', 'MPSGraph-MPS', ('MetalPerformanceShadersGraph',)),
    ('apple.bnns', 'apple', 'Accelerate-BNNS', ('Accelerate',)),
    ('ascend.acl', 'ascend', 'AscendCL-ACLNN', ('ascendcl', 'nnopbase')),
    ('musa.runtime', 'musa', 'MUSA-muBLAS-muDNN', ('musa', 'mublas', 'mudnn')),
    ('cambricon.cnrt', 'cambricon', 'CNRT-CNNL-CNDrv', ('cnrt', 'cnnl', 'cndrv')),
    ('metax.runtime', 'metax', 'MXMACA-mcBLAS-mcTriton', ('mcr', 'mcblas')),
]:
    BUILTINS.append(spec(name, vendor, family, 'native:NativeExtensionSeam', operations=('extension',),
                         options=(('libraries', libraries),), maturity=1))
for name in ('google.pjrt', 'aws.neuron', 'tenstorrent.ttnn', 'portable.vulkan', 'portable.opencl', 'diskann', 'multi-device'):
    BUILTINS.append(spec(name, name.split('.')[0], name, 'native:NativeExtensionSeam', operations=('extension',), maturity=0))
