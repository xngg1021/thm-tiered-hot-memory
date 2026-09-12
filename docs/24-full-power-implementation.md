# THM 1.5 implementation surface

The three THM planes are implemented independently: logical T0–T3 memory, compute execution, and physical representation/placement. Context Economics remains a separate project with L0–L6. Implementation, deterministic fixtures, cross-platform checks, host integration, hardware acceptance and real task outcomes are distinct evidence classes. The [completion ledger](../reports/2026-09-12-thm-full-power-completion.md) records source paths and exact release gates.

## Configured provider execution

`NativeExtensionSeam.configure(ExtensionConfig, binding)` supplies a serial, locked prepare → compile → load → execute → invalidate → close session for all 19 extension entries. `discover_extension` checks installed metadata without importing or installing a vendor runtime. The configuration binds provider/runtime/dependency/driver/device, source SHA/generation, precision, options and resource limits. Public identities hash private device/runtime/source-generation fields. Receipts include source shape, actual binding configuration identity, monotonic lifecycle events, resource/error state and explicit reference fallback.

`FunctionBinding` accepts explicit prepare/compile/load/execute/close SDK functions and an operation set. This is the executable integration boundary for version-specific C/ObjC handles, Vulkan pipelines, cuFile, native BLAS/NN, device runtimes and caller-owned storage services. It does not guess a binary ABI, install an SDK or turn symbol discovery into execution. Every catalog extension runs the full lifecycle against a deterministic binding fixture, including generation rejection and cleanup/quarantine.

Five additional public Python bindings call concrete APIs in `thm.runtime.fabric.sdk_extensions`:

| Binding | Executable path | Operating point |
| --- | --- | --- |
| `PJRTBinding` | JAX device placement, lower/compile, resident matrix scoring and synchronization | Explicit backend/device; FP32 |
| `NeuronBinding` | Load/eval an explicitly prepared local TorchScript Neuron artifact, inference, CPU result | Precompiled artifact; no hidden compiler or model download |
| `TTNNBinding` | Open device, tiled from_torch, matmul, result materialization/deallocation, close device | Explicit BF16; independent quality admission required |
| `OpenCLBinding` | Context/queue/buffers, compile exact dot kernel, launch, wait/copy, release | FP32; no dispatch/performance acceptance |
| `DiskANNBinding` | Owned temporary memory-index build, StaticMemoryIndex load/search, cleanup | Approximate L2 candidates; explicit quality gate |

Public contracts are checked against [JAX](https://docs.jax.dev/en/latest/aot.html), [Neuron](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/frameworks/torch/torch-neuronx/api-reference-guide/inference/api-torch-neuronx-trace.html), [TTNN](https://docs.tenstorrent.com/tt-metal/latest/ttnn/ttnn/api/ttnn.from_torch.html), [PyOpenCL](https://documen.tician.de/pyopencl/runtime_program.html) and [diskannpy](https://microsoft.github.io/DiskANN/docs/python/latest/diskannpy.html). Fixtures exercise these call shapes without proprietary binaries. A configured lifecycle is L4 contract coverage; the catalog's automatic/native maturity remains separately reported. No entry gains L5 from this work.

Extension input/output/call/lifetime budgets reject oversized or late results. Path artifacts include their complete immutable parent bundle: traversal is capped at 4096 entries, sizes are checked before hashing and streaming reads enforce the byte ceiling. The validated bytes are copied into a session-owned private directory, and bindings prepare/load only that fixed copy. Closing or quarantining the session releases it. Native calls themselves need the existing `BoundedShadowExplorer` process boundary for hard interruption; an in-process deadline cannot preempt a stuck driver. Unknown driver identity limits freshness to the process. Host code must pass changed driver/dependency/generation identities or invalidate the session. CPU reference authority and semantic admission remain independent of a binding's output.

## Physical transports and allocations

`BackendConfig` and `StorageBackend` provide generation-bound immutable publication, bounded content verification, extent reads, failure journals, committed-object recovery and cleanup for all 42 named families. `FixtureTransport` implements actual stage/commit/abort/read/size state and injected failures. `MountedFilesystemTransport` writes/fsyncs an owned temporary file, publishes create-only, verifies checksums and reopens mounted files. `S3Transport` uses an explicitly supplied client with conditional put, range get and caller-owned connection lifetime.

SMB/NFS/NAS, parallel filesystems and mounted remote block devices can use the mounted transport. DAOS, SPDK, cuFile/GDS, direct-I/O, async I/O, DAX and other specialized services can supply their native transport functions through the same fully executed state machine. The portable path does not claim native protocol, zero-copy, direct DMA or async kernel execution. No configured service is silently replaced with a different transport. Unknown durability remains unknown; a caller-supplied durability declaration is not a measurement.

`AllocationPool` owns representations for host DRAM, pinned host, unified memory, VRAM, staging, PMem, DAX and CXL. Plain host DRAM uses a bytearray; specialized allocation requires an explicit allocator returning data and a release function. Owner, generation, representation, device and capacity are checked. Leases delay eviction until the last reader releases; close does not free memory underneath an active lease. This ownership abstraction cannot change a logical tier.

`MultiDeviceIndex` atomically builds bounded shards using explicitly supplied vector providers. A failed rebuild closes unpublished handles and retains the previous generation. Search merges per-shard results with deterministic global source-order ties; semantic parity must still be checked. `JointComputeDataPlanner.choose` binds logical object, representation, compute profile, physical placement, transfer, resident index and runtime provider. It applies hard capacity/durability/locality/resource constraints, then named latency/throughput/CPU orderings. Compile/startup/transfer costs amortize over an explicit reuse horizon. Missing costs or stale identities produce an explained reference/local fallback.

## Explicit residency actuation

`ResidencyActuator` consumes the canonical shadow recommendation. `ResidencyPlacementStore` is a host-consumable placement replica, not the source content store. Initialize it with source-bound entries and provide `source_is_current(entry)` from the authoritative host. `propose` applies task sufficiency, minimum demand, validity/staleness, pin, cooldown/hysteresis, token benefit/carry cost, replacement capacity, context-pressure and prefetch-pollution gates. Unknown cost or source state fails closed.

`execute(plan, shadow)` defaults to dry-run. Approval mode requires the exact `approved_plan_id`; automatic mode additionally requires `ActuatorPolicy(automatic_mutation=True)` and externally accepted task evidence matching the policy SHA and generation. Evidence acceptance belongs to the host; a fixture must never supply production acceptance. The transaction revalidates authority and snapshot revision, publishes placement only, and records an audit event. Rollback restores the previous placement only if no intervening transaction occurred and records a rollback event. Reopening SQLite recovers committed placement and audit. `replay` evaluates at most 256 scenarios without applying changes. Source content, activity, validity and retrieval semantics remain untouched.

## Evaluation, outcomes and independent economics

`thm.evaluation.runner.run` accepts a typed `RetrievalFeatures` configuration and literal/sparse/dense/hybrid operating point. Dense/hybrid requires an explicit callable encoder and model identity. CLI `--features-json` enables a single channel or deterministic composition. Tests run each of six feature flags separately on all five benchmark fixtures and exercise Track B with a local deterministic encoder. Entity projection, explicit aliases, temporal/date/range hints, segments/parent spans, query grammar and bounded structural association remain default-off. Partial source slices never inherit complete-source evidence credit.

Every adapter retains its native parser, source projection, evaluator-only ground truth, task/dataset/implementation identity, evidence-unit semantics, fixture, error handling and explicit full-research entrypoint. `AgentMemory.save/restore` enforces the same 16 MB UTF-8 snapshot limit before publication and during restore; an owned temporary file is flushed/fsynced and published with an atomic create-only link, so failed writes cannot block retry with a corrupt final file; V2's upstream save/load hooks use it. `EnvironmentRunner` executes trusted, pickleable environment definitions/factories, a top-level policy and an optional memory factory inside an owned subprocess. The parent deadline covers initialization, reset, policy, step, memory and close; timeout kills the process tree. POSIX process groups and a Windows Job Object contain helpers. Lambdas, open SDK handles and other non-pickleable configurations fail explicitly; use importable top-level factories to construct worker-owned resources. No uploaded or untrusted pickle is accepted by this API. `OfficialScorerBridge` invokes a supplied scorer with evaluator-only gold/rubric. Synthetic environment success always has `task_outcome_accepted=false`.

`attach_outcomes(..., allow_partial=True)` binds exact executed task IDs and trace SHA, rejects duplicates/tampered receipts, merges disjoint partial results and reports missing IDs. Available answer scores have macro aggregation; micro aggregation requires explicit numerator/denominator. Environment success, latency, cost and observed counts remain separate. Missing scores remain null; `not-run` is valid. No generation or judge is invoked by the attachment API.

`thm.economics_bridge` exports source/commit-bound measurements with explicit units, denominators and provenance for packed/full-history tokens, recall, miss/reacquisition, carry, prefetch waste, I/O, startup/compile, resources and available outcomes. Unknown inputs remain null. `EconomicAdvice` imports budget ranges, objective, latency/cost envelope and policy advice bound to the exact exported receipt. `configure_session` applies an explicit recommendation only to a new session configuration. THM has no CE import or personal filesystem dependency.

```bash
python -m thm.economics_bridge --help
python -m thm.evaluation --mode smoke --wall-seconds 120 --features-json '{"segment":true}' --output .thm-evaluation/segment-smoke
python -m unittest discover -s tests -p 'test_full_power*' -v
python -m unittest discover -s tests -p test_optional_sdk_bindings.py -v
```

## Harnesses and release gates

Hermes, OpenAI Agents, LangChain, LangGraph, Deep Agents, MCP v2, legacy MCP, OpenClaw, Claude Code, Codex CLI and Gemini CLI share canonical THM memory. `THMGraphNode` carries recall and runtime status into LangGraph state. `deep_agents_tools` returns recall/status tools plus an owner that must be closed. CI executes a real LangGraph graph and tool calls and constructs a real Deep Agents graph using a fake chat model; it does not claim agent outcome.

Correctness runs Linux Python 3.10–3.14, Windows/macOS Python 3.13, the full unit suite, numeric audit, five Evaluation Fabric smoke fixtures, docs/localization/version guards and eight tiktoken versions. Hermes and harness workflows run on every exact PR head and main push. Optional SDK tests use public API fakes; they do not install vendor binaries or large models.

`scripts/verify_merge_gate.py` validates an explicitly fetched snapshot against the exact head, archive, newest push workflow attempts, normal merge method and resolved actionable reviews. The caller must still use GitHub's `expected_head_sha` guard. This offline helper does not replace remote branch protection. Remote administration is separately recorded as unavailable when the integration cannot access it. New archives are immutable; post-merge workflow identities can be recorded in a forward-only documentation descendant, as permitted by VERSIONING.
