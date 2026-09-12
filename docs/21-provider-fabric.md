# Provider Fabric — Unreleased

The fabric separates capability discovery, model inference, vector indexing and data transfer. Provider instances receive execution inputs and immutable identities; they have no memory-activity or source-authority handle. Optional SDKs load only when a provider is actually probed or invoked.

## Contracts

| Contract | Lifecycle / operations |
| --- | --- |
| `DeviceProvider` | discover hardware graph, report capabilities and process availability |
| `InferenceProvider` | probe, prepare, compile/load local artifact, encode, telemetry, close |
| `VectorIndexProvider` | probe, build/load immutable handle, search, update/rebuild, memory usage, close |
| `TransferProvider` | discover transfer capability, move explicitly owned buffers, synchronize, receipt |

`ProviderSpec` declares vendor/family, factory, optional distributions, operating systems, device classes, precisions, operations, compilation/residency support, priority and maturity. A declarative catalog replaces vendor condition chains in the service. The registry isolates unavailable imports and duplicate IDs. `thm.providers` entry points are metadata-only until explicitly trusted; arbitrary third-party entry points never become automatic candidates.

The [matrix](provider-matrix.md) and [JSON source audit](provider-sources.json) distinguish L0 documentation, L1 discovery/extension, L2 preparation, L3 execution, L4 receipt-complete lifecycle and L5 exact hardware acceptance. L4 fixtures do not imply L5. Ordinary CUDA/PyTorch paths cannot stand in for a vendor-native API implementation.

## Hardware graph and availability

The graph represents CPUs, memory, NUMA relationships, visible accelerators and supplied storage targets. Installed capacity, OS-visible capacity and the current process allocation are separate observations. Linux affinity/cgroup quotas/cpusets and Windows process affinity constrain CPU planning. Native discovery publishes sanitized version/device facts back from a bounded child.

Driver/runtime identities use public APIs where available. CUDA/HIP probes separate the driver version from the framework's build runtime. Metal is tied to the OS build. If a native driver cannot be observed, a process-specific freshness epoch prevents cross-process reuse of an old performance profile. Missing PCIe/CXL/NPU topology, thermal/battery signals and device counters stay unknown; no fabricated fabric edge implies an executable transfer.

## Inference artifacts

Local model identity binds source bytes, derived bytes, provider version, precision, transformation and execution options. Directory manifests conservatively include external ONNX tensors and OpenVINO XML/BIN bundles. Caches must be outside the immutable source bundle. SentenceTransformer adapters use `local_files_only=True` and disable remote code.

Native TensorRT-RTX implements ONNX parsing, AOT engine construction, deserialization/JIT startup, explicit named input/output buffers and asynchronous execution followed by synchronization. Its immutable cache binds source, transformation, provider version, driver/runtime, device capability, precision and compiler options. Dynamic shape profiles and workspace limits are explicit. Its ORT EP is a separate path.

ORT requests the actual installed EP, disables implicit CPU EP fallback and can register a local standalone EP library through the plugin ABI. OpenVINO reports permitted and observed execution devices separately. Core ML allowed compute units do not prove ANE placement. MIGraphX calls its public parse/compile/run lifecycle. QNN requires an installed local backend. Windows ML enumerates READY packages and registers their local libraries without downloading/preparing packages.

Automatic text preparation uses the source model's tokenizer/pooling contract and a separate vector profile in a private replica. Raw tensor adapters retain explicit named-input contracts; they do not silently substitute a different embedding architecture.

## Index and transfer ownership

An index identity includes scope, generation, embedding profile, provider/version, index parameters, precision, device, placement, runtime and training identity. Handles own immutable buffers. Publication checks current generation and capacity; in-flight handles survive until their readers release them. Failed allocations close the unpublished handle and retain valid existing state.

Accelerator indexes keep the document matrix/index resident. Search transfers query vectors and bounded top-k IDs/scores. Host/pinned/asynchronous transfers have explicit synchronization and byte receipts. A transfer descriptor is not proof that GDS, P2P, CXL, RDMA or a native DMA path executed.

## Measurement and licensing

Normalized samples distinguish request latency, stage clocks, process CPU seconds, device counters, RAM/VRAM, transfer bytes, startup/compile, energy and observed dispatch. Missing values remain null. NVML energy is a board counter; it cannot be attributed to one query without a matching measurement method. AMD SMI reports supported public activity values; no energy estimate is fabricated.

No vendor SDK or model is part of core installation or redistributed by THM. The source audit records each upstream API and license boundary, including uncertain exact fork licenses. Vendor SDK terms remain separate from open-source wrapper licenses. See [optimizer evidence](22-runtime-optimizer.md) for admission and [source audit](provider-sources.json) for provenance.
