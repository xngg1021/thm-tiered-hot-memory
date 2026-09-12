# Provider support matrix — Unreleased

Catalog and source audit checked on 2026-09-09. Package/stable remains 1.4.0. Machine-readable provenance: [provider-sources.json](provider-sources.json). The matrix records callable implementation maturity; installed versions and observed devices are discovered locally. No row has hardware acceptance (L5).

| Level | Meaning |
| --- | --- |
| L0 | Documented extension contract |
| L1 | Discoverable library or explicit extension bridge |
| L2 | Artifact preparation/build/export |
| L3 | Executable provider operation |
| L4 | Executable lifecycle with structured receipts |
| L5 | Exact hardware/runtime/task evidence accepted |

Counts: L0: 7, L1: 12, L2: 1, L4: 51.

## Executable and preparable providers

| Provider | Runtime | Level | OS | Optional distribution / SDK |
| --- | --- | --- | --- | --- |
| `nvidia.cublaslt` | [cuBLASLt-nvmath](https://docs.nvidia.com/cuda/nvmath-python/latest/host-apis/linalg/generated/nvmath.linalg.advanced.Matmul-class.html) | L4 | Linux, Windows | nvmath-python |
| `nvidia.cuda-graph` | [CUDA-Graph](https://docs.pytorch.org/docs/stable/generated/torch.cuda.CUDAGraph.html) | L4 | Linux, Windows | torch |
| `nvidia.nvml` | [NVML](https://docs.nvidia.com/deploy/nvml-api/group__nvmlDeviceQueries.html) | L4 | Linux, Windows, Darwin | nvidia-ml-py |
| `amd.smi` | [AMD-SMI](https://github.com/ROCm/rocm-systems/tree/develop/projects/amdsmi) | L4 | Linux, Windows | amdsmi |
| `host.device` | [os](https://docs.python.org/3/library/index.html) | L4 | Linux, Windows, Darwin | locally installed vendor SDK / system API |
| `host.exact` | [numpy](https://numpy.org/doc/stable/reference/generated/numpy.matmul.html) | L4 | Linux, Windows, Darwin | numpy |
| `host.hnsw` | [hnswlib](https://github.com/nmslib/hnswlib) | L4 | Linux, Windows, Darwin | hnswlib |
| `host.transfer` | [memory](https://docs.python.org/3/library/index.html) | L4 | Linux, Windows, Darwin | locally installed vendor SDK / system API |
| `cpu.onnxruntime` | [ONNX-Runtime-CPU](https://onnxruntime.ai/docs/api/python/api_summary.html) | L4 | Linux, Windows, Darwin | onnxruntime |
| `intel.openvino-cpu` | [OpenVINO-CPU](https://docs.openvino.ai/2026/openvino-workflow.html) | L4 | Linux, Windows, Darwin | openvino |
| `cpu.inference` | [torch](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows, Darwin | torch, sentence-transformers |
| `nvidia.inference` | [CUDA](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch, sentence-transformers |
| `nvidia.exact` | [CUDA](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `nvidia.transfer` | [CUDA](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `amd.inference` | [ROCm-HIP](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch, sentence-transformers |
| `amd.exact` | [ROCm-HIP](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `amd.transfer` | [ROCm-HIP](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `intel.inference` | [XPU](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch, sentence-transformers |
| `intel.exact` | [XPU](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `intel.transfer` | [XPU](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Linux, Windows | torch |
| `apple.inference` | [MPS](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Darwin | torch, sentence-transformers |
| `apple.exact` | [MPS](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Darwin | torch |
| `apple.transfer` | [MPS](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | L4 | Darwin | torch |
| `ascend.inference` | [CANN-TorchNPU](https://github.com/Ascend/pytorch) | L4 | Linux | torch, torch-npu, sentence-transformers |
| `ascend.exact` | [CANN-TorchNPU](https://github.com/Ascend/pytorch) | L4 | Linux | torch, torch-npu |
| `ascend.transfer` | [CANN-TorchNPU](https://github.com/Ascend/pytorch) | L4 | Linux | torch, torch-npu |
| `musa.inference` | [MUSA](https://docs.mthreads.com/musa-sdk/version-5.2.0/introduction/) | L4 | Linux | torch, torch-musa, sentence-transformers |
| `musa.exact` | [MUSA](https://docs.mthreads.com/musa-sdk/version-5.2.0/introduction/) | L4 | Linux | torch, torch-musa |
| `musa.transfer` | [MUSA](https://docs.mthreads.com/musa-sdk/version-5.2.0/introduction/) | L4 | Linux | torch, torch-musa |
| `cambricon.inference` | [CNRT-CNNL](https://github.com/Cambricon/torch_mlu) | L4 | Linux | torch, torch-mlu, sentence-transformers |
| `cambricon.exact` | [CNRT-CNNL](https://github.com/Cambricon/torch_mlu) | L4 | Linux | torch, torch-mlu |
| `cambricon.transfer` | [CNRT-CNNL](https://github.com/Cambricon/torch_mlu) | L4 | Linux | torch, torch-mlu |
| `metax.inference` | [MXMACA-mcPyTorch](https://developer.metax-tech.com/api/client/document/preview/355/C500_mcFaissManual_CN.html) | L4 | Linux | torch, sentence-transformers |
| `metax.exact` | [MXMACA-mcPyTorch](https://developer.metax-tech.com/api/client/document/preview/355/C500_mcFaissManual_CN.html) | L4 | Linux | torch |
| `metax.transfer` | [MXMACA-mcPyTorch](https://developer.metax-tech.com/api/client/document/preview/355/C500_mcFaissManual_CN.html) | L4 | Linux | torch |
| `nvidia.rtx-native` | [TensorRT-RTX-AOT-JIT](https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/inference-library/python-api-docs.html) | L4 | Linux, Windows | tensorrt-rtx |
| `nvidia.tensorrt-rtx` | [TensorRT-RTX-EP-ABI](https://onnxruntime.ai/docs/execution-providers/TensorRTRTX-ExecutionProvider.html) | L4 | Linux, Windows | onnxruntime |
| `amd.migraphx` | [MIGraphX](https://rocm.docs.amd.com/projects/AMDMIGraphX/en/develop/reference/MIGraphX-py.html) | L4 | Linux | migraphx |
| `amd.migraphx-ep` | [MIGraphX-EP](https://rocm.docs.amd.com/projects/AMDMIGraphX/en/develop/reference/MIGraphX-py.html) | L4 | Linux, Windows | onnxruntime |
| `intel.openvino` | [OpenVINO-AUTO](https://docs.openvino.ai/2026/openvino-workflow.html) | L4 | Linux, Windows, Darwin | openvino |
| `apple.coreml` | [CoreML](https://developer.apple.com/documentation/coreml/mlcomputeunits) | L4 | Darwin | coremltools |
| `qualcomm.qnn` | [QNN-HTP](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html) | L4 | Windows, Linux | onnxruntime-qnn |
| `windows.directml` | [DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html) | L4 | Windows | onnxruntime-directml |
| `nvidia.cuvs.brute_force` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-brute-force) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.cagra` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-cagra) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.ivf_flat` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-ivf-flat) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.ivf_pq` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-ivf-pq) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.ivf_sq` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-ivf-sq) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.tiered_index` | [cuVS](https://docs.nvidia.com/cuvs/api-reference/python-api-neighbors-tiered-index) | L4 | Linux | cuvs-cu12 |
| `nvidia.cuvs.vamana` | [cuVS](https://docs.nvidia.com/cuvs/user-guide/api-guides/indexing-guide/vamana) | L2 | Linux | cuvs-cu12 |
| `metax.mcfaiss` | [MXMACA-mcFaiss](https://developer.metax-tech.com/api/client/document/preview/355/C500_mcFaissManual_CN.html) | L4 | Linux | locally installed vendor SDK / system API |
| `windows.catalog` | [WindowsML](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/api-reference) | L4 | Windows | locally installed vendor SDK / system API |

## Extension seams

| Provider | Runtime | Level | Implemented boundary |
| --- | --- | --- | --- |
| `nvidia.cufile` | cuFile-GDS | L1 | ctypes.util.find_library and explicit extension bridge |
| `amd.hipblaslt` | hipBLASLt | L1 | ctypes.util.find_library and explicit extension bridge |
| `amd.rocblas` | rocBLAS | L1 | ctypes.util.find_library and explicit extension bridge |
| `intel.onednn` | oneDNN | L1 | ctypes.util.find_library and explicit extension bridge |
| `intel.onemkl` | oneMKL | L1 | ctypes.util.find_library and explicit extension bridge |
| `intel.levelzero` | LevelZero | L1 | ctypes.util.find_library and explicit extension bridge |
| `apple.mpsgraph` | MPSGraph-MPS | L1 | ctypes.util.find_library and explicit extension bridge |
| `apple.bnns` | Accelerate-BNNS | L1 | ctypes.util.find_library and explicit extension bridge |
| `ascend.acl` | AscendCL-ACLNN | L1 | ctypes.util.find_library and explicit extension bridge |
| `musa.runtime` | MUSA-muBLAS-muDNN | L1 | ctypes.util.find_library and explicit extension bridge |
| `cambricon.cnrt` | CNRT-CNNL-CNDrv | L1 | ctypes.util.find_library and explicit extension bridge |
| `metax.runtime` | MXMACA-mcBLAS-mcTriton | L1 | ctypes.util.find_library and explicit extension bridge |
| `google.pjrt` | google.pjrt | L0 | documented extension contract; no native API execution |
| `aws.neuron` | aws.neuron | L0 | documented extension contract; no native API execution |
| `tenstorrent.ttnn` | tenstorrent.ttnn | L0 | documented extension contract; no native API execution |
| `portable.vulkan` | portable.vulkan | L0 | documented extension contract; no native API execution |
| `portable.opencl` | portable.opencl | L0 | documented extension contract; no native API execution |
| `diskann` | diskann | L0 | documented extension contract; no native API execution |
| `multi-device` | multi-device | L0 | documented extension contract; no native API execution |

## API and evidence boundaries

- TensorRT-RTX native AOT/JIT and its ORT EP are separate implementations. The standalone EP path uses local library registration, EP devices and `SessionOptions.add_provider_for_devices`; it never installs a catalog package. Native engine caches bind source, compiler options, precision, runtime/driver and device capability.
- cuVS brute force, CAGRA, IVF-Flat/PQ/SQ and TieredIndex execute their public APIs. CAGRA ACE uses host input and explicit host/GPU budgets. TieredIndex search uses CAGRA search parameters. Vamana supplies build/export; multi-GPU search remains a contract. Quantized/ANN indexes require explicit approximate policy and separate quality receipts.
- cuBLASLt uses nvmath Matmul with a single heuristic plan and pedantic FP32 compute. CUDA Graph capture requires an already prepared fixed operation; it is not enabled across arbitrary request shapes. cuFile is an L1 bridge, so ordinary mmap is never described as GDS.
- AMD uses HIP provenance checks, executable MIGraphX/ORT/Torch paths and public AMD SMI counters. The deprecated ROCm EP is not a substitute for current MIGraphX support. hipBLASLt/rocBLAS remain explicit L1 bridges.
- OpenVINO accepts CPU/GPU/NPU/AUTO/MULTI/BATCH and records execution devices when exposed. PyTorch XPU has a separate resident exact path. oneDNN, oneMKL and Level Zero are L1 bridges.
- Core ML allowed compute units are distinct from observed ANE operator placement. MPS inference/exact transfer paths execute through Torch; MPSGraph/BNNS remain explicit L1 bridges.
- QNN requires a locally installed backend and named model tensor inputs. Windows ML enumerates READY local EP packages and uses the ORT plugin ABI; it does not call the package download/preparation lifecycle.
- Ascend, MUSA, Cambricon and MetaX have separate framework inference, exact-index and transfer implementations. Native C SDK families remain L1. MetaX mcFaiss requires MACA runtime provenance; ordinary CUDA Faiss cannot satisfy that claim.
- Automatic text-model preparation uses the existing local SentenceTransformer contract and creates a separate vector profile in a disposable index replica. Raw tensor adapters remain available to callers with explicit preprocessing/pooling contracts. Unknown GPU memory prevents automatic model admission under a GPU memory constraint.

## Optional dependency and license audit

Core installation adds no Torch, CUDA, ROCm, TensorRT-RTX, OpenVINO, QNN, CANN, MUSA, MLU or MACA SDK. No model or vendor binary is redistributed. SDK versions are null here because this source audit is not an installed-device inventory. Tests use NumPy and tiktoken plus explicit SDK fixtures; they neither download models nor certify those SDK licenses.

| Component | Source license boundary |
| --- | --- |
| THM | MIT |
| ONNX Runtime | MIT; execution-provider SDKs have separate terms |
| OpenVINO, cuVS, nvmath-python, hnswlib | Apache-2.0 sources; linked runtime terms remain separate |
| MIGraphX, AMD SMI, CuPy | MIT sources; linked runtime terms remain separate |
| coremltools | BSD-3-Clause; Apple SDK terms remain separate |
| PyTorch, torch_npu, torch_musa | BSD-style source licenses; verify the exact installed fork/version |
| torch_mlu / MetaX packages | Exact installed distribution license must be checked; no license borrowed from another fork |
| CUDA / TensorRT-RTX / QNN / CANN / MUSA / MLU / MACA | Vendor SDK terms; optional and not redistributed |

Official repository license sources were inspected where available. Unverified exact package SPDX values stay explicitly unresolved; absence of a GitHub license API response is not evidence of a license. See each provider source row for its actual API and distribution boundary.
