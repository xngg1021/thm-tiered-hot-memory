# Vector index providers — 1.5 implementation

Vector index choice is independent of model inference and physical source placement. The provider owns an immutable profile/generation-specific replica; canonical scope/source identity remains in THM. Default strict policies require exact FP32 candidates.

## Executable paths

| Provider | Search / build | Admission boundary |
| --- | --- | --- |
| Host NumPy | FP32 flat inner product with stable ties | Strict reference comparison |
| Torch CUDA/HIP/XPU/MPS/NPU/MUSA/MLU/MACA | Resident matrix; device matmul and stable top-k | Actual vendor provenance, device availability and numeric/structural gate |
| cuVS brute force | Native exact GPU index/search | Strict observed gate |
| cuVS CAGRA | Native graph build/search, bounded ACE host/GPU build parameters | Explicit approximate policy and quality deltas |
| cuVS IVF-Flat/PQ/SQ | Native trained coarse/quantized index/search | Explicit approximate policy; index/training identity separated |
| cuVS TieredIndex | Native tiered CAGRA API with CAGRA search parameters | Explicit approximate policy; staging/hot/cold costs explicit |
| cuVS Vamana | GPU build and DiskANN-compatible export | L2; no implemented GPU serving search |
| mcFaiss | MACA-provenanced GPU flat index/resources/add/search | Ordinary CUDA Faiss cannot satisfy this provider |
| cuBLASLt | nvmath Matmul with pedantic FP32 and one vendor heuristic plan | Bounded workspace; no exhaustive autotune grid |
| hnswlib | Native host HNSW build/query | Explicit approximate policy |

Multi-device, DiskANN serving and portable Vulkan/OpenCL remain catalog contracts. GDS/cuFile is an extension bridge, not an implicit property of a disk-backed index. See the [support matrix](provider-matrix.md) for exact maturity and official source URLs.

## Identity, residency and rebuild

`IndexIdentity` binds scope, generation, embedding profile, provider/version, metric/configuration, precision, device, placement, runtime and optional training SHA. Public scope values are hashed. A matrix does not become reusable merely because dimension and model name match.

The handle manager checks the current generation and per-device budget before publication. Immutable replicas can be reused across requests; readers pin their handle while executing. Invalidated in-flight handles close only after release. Failed allocations clean up candidate resources. Capacity failures leave the previous live handle intact.

A warm accelerator query transfers the query and bounded top-k IDs/scores. It does not reconstruct or upload the document matrix on every query. Receipts record resident hit, first-load cost, resident bytes, transfer bytes, provider identity and search duration. Some native graph workspace/allocator totals remain estimates or unknown, so no claim equates matrix bytes with total device peak.

Model-provider changes create an independent embedding profile and a private derived index. Original source vectors are never overwritten or mixed with the new query profile. Generation changes invalidate the private replica before it can serve a stale result.

## Physical integration

The joint planner records inference provider, vector provider, current source placement, target residency, transfer provider, device, batch/workload policy and known costs. It reads the existing physical-placement manifest and validates generation/target before returning a result. A placement change can invalidate a performance profile even when logical source IDs remain the same.

Buffered/mmap local storage, immutable segments and explicit migrations retain their existing contracts. A runtime recommendation never performs an unrequested authority mutation, relocates canonical memory, changes T0–T3 activity, or counts a prefetch/retrieval as an explicit hit.

## Quality and measurement

Strict comparison includes finite dimension-aware score tolerances, exact ranked/selected IDs, hashes, sources, completeness, generation, budget and packed context. ANN candidates record exact-neighbor overlap, recall against exact, selected/rank deltas and packed-context change. These measurements do not establish agent outcomes or universal semantic equivalence.

Validation uses SDK-shaped lifecycle fixtures and bounded real host execution. Native GPU/NPU hardware validation remains separate and explicitly unaccepted. Historical local CPU/CUDA receipts in the repository retain their original commit identities; they are not relabeled as native cuVS/mcFaiss/RTX measurements.

## 1.5 implementation and evidence contract

[1.5 implementation surface](24-full-power-implementation.md) defines the executable configured provider/storage lifecycle, allocation and joint-planning APIs, explicit actuator, five benchmark/environment/outcome interfaces, independent CE bridge, and LangGraph/Deep Agents lifecycle. Automatic memory mutation remains false and rejected features remain default-off. Hardware, full-research and real task evidence are separately recorded in the [completion ledger](../reports/2026-09-12-thm-full-power-completion.md).
