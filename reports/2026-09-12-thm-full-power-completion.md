# THM 1.5 full-power implementation completion

All 28 historical design domains have executable implementation and test mappings. Hardware/environment acceptance remains separate. The [machine-readable ledger](2026-09-12-thm-full-power-completion.json) and [post-merge-only release receipt](2026-09-12-v1.5-closeout.json) bind the accepted merge, archive, review and successful workflows.

## Identity and evidence

- Package: 1.5.0; accepted implementation main/merge: `de26865f36df2205c29a470e51c65d5bf9beca4e`; immutable archive: `archive/v1.5.0-stable@de26865f36df2205c29a470e51c65d5bf9beca4e`.
- PR #21: normally merged; exact feature head `d33fc70677e61d6733fdbc8c0f71bced6168dff4`; tree `e8521b03501a015e9f5fc8b94fa99ddb3b6080ab`; parents `b96b82f027ca128072e3c0b3899331af1155b39e, d33fc70677e61d6733fdbc8c0f71bced6168dff4`.
- PR #20 merged normally: `b96b82f027ca128072e3c0b3899331af1155b39e`; accepted head: `62b616b0820749615a5dd3ab9bd9aa55abdc4d27`.
- PR #20 exact-head runs: 34711488892 / 34711488961 / 34711488928. Main runs: 34712261941 / 34712261953 / 34712261948; all successful.
- Immutable 1.4 archive: `e6e4dda5835e3cb345207457d5491131c6959b2c`. Historical machine evidence: `bb1676007b0f86dec0267585c56136c82157ae54`; never relabeled as new runtime acceptance.

## Historical domain closure

| Domain | Status | Implementation and validation |
| --- | --- | --- |
| logical T0–T3 | implemented | Source-bound logical residency/access classes, explicit host lifecycle. [scripts/thm.py](../scripts/thm.py); [thm/harness.py](../thm/harness.py); [tests/test_engine.py](../tests/test_engine.py) |
| metadata/authority | implemented | Derived indexes preserve native source, scope, generation, hashes and atomic replacement. [thm/sources.py](../thm/sources.py); [thm/retrieval.py](../thm/retrieval.py); [tests/test_derived_database_guard.py](../tests/test_derived_database_guard.py) |
| activity/validity | implemented | Explicit events, validity/pin/stale guards; retrieval does not fabricate activity. [scripts/thm.py](../scripts/thm.py); [thm/_residency_common.py](../thm/_residency_common.py); [tests/test_engine.py](../tests/test_engine.py); [tests/test_residency_guardrails.py](../tests/test_residency_guardrails.py) |
| retrieval | implemented | Scoped literal/sparse/dense/hybrid retrieval and budgeted complete/partial evidence. [thm/retrieval.py](../thm/retrieval.py); [tests/test_recall_extension.py](../tests/test_recall_extension.py); [tests/test_ranking_guard.py](../tests/test_ranking_guard.py) |
| feature channels | implemented | Typed default-off entity/alias/temporal/query/segment/association channels, standalone A/B and Track B. [thm/features.py](../thm/features.py); [thm/evaluation/runner.py](../thm/evaluation/runner.py); [tests/test_frontier_projections.py](../tests/test_frontier_projections.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| residency | implemented | Demand-aware shadow decisions and bounded value/carry objective. [thm/residency.py](../thm/residency.py); [thm/residency_control.py](../thm/residency_control.py); [tests/test_residency_control.py](../tests/test_residency_control.py) |
| prefetch | implemented | Locator-only demand-independent prefetch and pollution accounting. [thm/residency_telemetry.py](../thm/residency_telemetry.py); [thm/residency_directory.py](../thm/residency_directory.py); [tests/test_miss_telemetry.py](../tests/test_miss_telemetry.py); [tests/test_hermes_warm_directory.py](../tests/test_hermes_warm_directory.py) |
| adaptive budget | implemented | Bounded shadow budget objective and explicit new-session recommendation import. [thm/residency_control.py](../thm/residency_control.py); [thm/economics_bridge.py](../thm/economics_bridge.py); [tests/test_residency_control.py](../tests/test_residency_control.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| actuator | implemented | Dry-run, replay, exact approval, evidence-gated automatic placement replica, transaction/recovery/rollback audit; default false. [thm/actuator.py](../thm/actuator.py); [tests/test_full_power_lifecycles.py](../tests/test_full_power_lifecycles.py) |
| source/index lifecycle | implemented | Generation/profile/capacity CAS, handle ownership and fresh fallback. [thm/retrieval.py](../thm/retrieval.py); [thm/runtime/fabric/indexes.py](../thm/runtime/fabric/indexes.py); [tests/test_physical_isolation.py](../tests/test_physical_isolation.py); [tests/test_model_fabric.py](../tests/test_model_fabric.py) |
| multi-harness | implemented | Eleven canonical-core host/protocol surfaces; real installed SDK lifecycle CI, no model outcome. [thm/adapters/langgraph.py](../thm/adapters/langgraph.py); [research/harness_e2e.py](../research/harness_e2e.py); [tests/test_harness_core.py](../tests/test_harness_core.py); [tests/test_mcp_legacy.py](../tests/test_mcp_legacy.py) |
| compute runtime | implemented | Safe bootstrap, passive telemetry, bounded exploration, guarded session adoption and reference fallback. [thm/runtime/fabric/service.py](../thm/runtime/fabric/service.py); [tests/test_runtime_successor.py](../tests/test_runtime_successor.py); [tests/test_pr20_review_regressions.py](../tests/test_pr20_review_regressions.py) |
| provider fabric | implemented | 71 catalog identities; 19 configured extension L4 contracts independently fixture-executed. [thm/runtime/fabric/catalog.py](../thm/runtime/fabric/catalog.py); [thm/runtime/fabric/extensions.py](../thm/runtime/fabric/extensions.py); [tests/test_provider_adapters.py](../tests/test_provider_adapters.py); [tests/test_optional_sdk_bindings.py](../tests/test_optional_sdk_bindings.py) |
| model preparation | implemented | Local immutable artifact/compile/load identity, no automatic model/SDK download. [thm/runtime/fabric/inference.py](../thm/runtime/fabric/inference.py); [thm/runtime/fabric/sdk_extensions.py](../thm/runtime/fabric/sdk_extensions.py); [tests/test_model_fabric.py](../tests/test_model_fabric.py); [tests/test_optional_sdk_bindings.py](../tests/test_optional_sdk_bindings.py) |
| vector index | implemented | Resident exact/native/approximate indexes, sharded ownership, deterministic merge, explicit quality admission. [thm/runtime/fabric/indexes.py](../thm/runtime/fabric/indexes.py); [thm/runtime/fabric/multidevice.py](../thm/runtime/fabric/multidevice.py); [tests/test_provider_fabric.py](../tests/test_provider_fabric.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| transfer | implemented | Owned bytes, synchronization, extent/generation identity and specialized bindings. [thm/runtime/fabric/transfer.py](../thm/runtime/fabric/transfer.py); [thm/physical/allocation.py](../thm/physical/allocation.py); [tests/test_provider_adapters.py](../tests/test_provider_adapters.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| scheduler | implemented | Deadline queues, foreground/background separation, sticky preemption, process-tree and warm-worker accounting. [thm/runtime/fabric/optimizer.py](../thm/runtime/fabric/optimizer.py); [thm/runtime/fabric/explorer.py](../thm/runtime/fabric/explorer.py); [tests/test_resource_budget.py](../tests/test_resource_budget.py); [tests/test_pr20_review_regressions.py](../tests/test_pr20_review_regressions.py) |
| physical storage | implemented | 42 configured family lifecycles plus portable buffered/mmap, mounted files and S3; native transport distinct. [thm/physical/backends.py](../thm/physical/backends.py); [thm/physical/adapters.py](../thm/physical/adapters.py); [tests/test_full_power_lifecycles.py](../tests/test_full_power_lifecycles.py); [tests/test_optional_sdk_bindings.py](../tests/test_optional_sdk_bindings.py) |
| migration | implemented | Immutable verified publication, atomic manifest switch, corruption/recovery and no source mutation. [thm/physical/migration.py](../thm/physical/migration.py); [thm/physical/segments.py](../thm/physical/segments.py); [tests/test_physical_migration.py](../tests/test_physical_migration.py); [tests/test_physical_segments.py](../tests/test_physical_segments.py) |
| topology | implemented | Public block/NUMA/PMem/DAX/CXL topology and optional NVML partition observation; unknown stays unknown. [thm/physical/probe.py](../thm/physical/probe.py); [thm/runtime/fabric/telemetry.py](../thm/runtime/fabric/telemetry.py); [tests/test_physical_probe.py](../tests/test_physical_probe.py); [tests/test_provider_adapters.py](../tests/test_provider_adapters.py) |
| joint placement | implemented | Orthogonal identities, hard constraints, amortized costs, named orderings and fail-closed fallback. [thm/physical/joint.py](../thm/physical/joint.py); [thm/runtime/fabric/optimizer.py](../thm/runtime/fabric/optimizer.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py); [tests/test_physical_execution.py](../tests/test_physical_execution.py) |
| evaluation | implemented | Three evidence layers, source/implementation hash, bounded fixture and explicit full-research paths. [thm/evaluation/contracts.py](../thm/evaluation/contracts.py); [thm/evaluation/runner.py](../thm/evaluation/runner.py); [tests/test_evaluation_fabric.py](../tests/test_evaluation_fabric.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| benchmark adapters | implemented | Five native parsers/source projections, evidence units, evaluator-only gold and persisted memory interfaces. [thm/evaluation/adapters.py](../thm/evaluation/adapters.py); [thm/evaluation/memory.py](../thm/evaluation/memory.py); [tests/test_evaluation_fabric.py](../tests/test_evaluation_fabric.py) |
| agent outcome | implemented | Environment/scorer boundary, exact IDs/traces, partial/missing scores, macro/micro and observed cost/latency. [thm/evaluation/environment.py](../thm/evaluation/environment.py); [thm/evaluation/outcomes.py](../thm/evaluation/outcomes.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| CE bridge | implemented | Standalone bidirectional source/commit/unit/denominator-bound protocol; no CE dependency or taxonomy merge. [thm/economics_bridge.py](../thm/economics_bridge.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| privacy/provenance | implemented | Private runtime/device/placement identities hashed; source and trace integrity, explicit evidence classes. [thm/runtime/fabric/contracts.py](../thm/runtime/fabric/contracts.py); [thm/evaluation/identity.py](../thm/evaluation/identity.py); [thm/runtime/fabric/extensions.py](../thm/runtime/fabric/extensions.py); [tests/test_provider_fabric.py](../tests/test_provider_fabric.py); [tests/test_full_power_protocols.py](../tests/test_full_power_protocols.py) |
| version/release | implemented | 1.5 coherent package surface; immutable archives, exact-head normal merge and descendant closeout. [VERSION](../VERSION); [VERSIONING.md](../VERSIONING.md); [scripts/check_version_history.py](../scripts/check_version_history.py); [scripts/verify_merge_gate.py](../scripts/verify_merge_gate.py); [tests/test_merge_gate.py](../tests/test_merge_gate.py) |
| governance | implemented | Unconditional exact-head/main checks, offline guarded merge and archive verification; remote administration separately unavailable. [.github/workflows/qa.yml](../.github/workflows/qa.yml); [.github/workflows/hermes-e2e.yml](../.github/workflows/hermes-e2e.yml); [.github/workflows/harness-e2e.yml](../.github/workflows/harness-e2e.yml); [scripts/verify_merge_gate.py](../scripts/verify_merge_gate.py); [tests/test_merge_gate.py](../tests/test_merge_gate.py) |

## Census

- 71 providers: native/automatic maturity L4=51, L2=1, L1=12, L0=7; new L5=0. All 19 extension entries additionally have configured L4 lifecycle fixtures. Five concrete optional Python SDK bindings and sharded multi-device execution are implemented.
- 42 physical backend families run the configured transport protocol fixture; portable buffered/mmap, mounted filesystem and S3 client transports have concrete execution paths. Eight allocation kinds have owned lifetime contracts. Specialized/native DMA and deployed services retain their own evidence state.
- Five benchmark adapters: LoCoMo, LongMemEval-S, LongMemEval-V2, BEAM and MemoryArena. All have fixtures, bounded/full-research interfaces and external scorer/environment boundaries. No new full campaign or real model outcome is claimed.
- Eleven harness surfaces: Hermes, OpenAI Agents SDK, LangChain, LangGraph, Deep Agents, MCP v2, legacy MCP, OpenClaw, Claude Code, Codex CLI, Gemini CLI. LangGraph graph execution, Deep Agents tools and graph construction are exercised without model calls.
- Counts: 28 implemented domains; 4 intentionally rejected policy choices; 20 evidence-only items; 1 external governance limitation; 0 external implementation gaps.

## Intentional exclusions

- **default promotion of historical negative retrieval experiments**: Negative held-out results do not justify default adoption; executable feature/research paths remain default-off.
- **retrieval/prefetch as activity or truth**: Would self-train demand and violate source/activity/validity authority.
- **automatic unaccepted memory mutation**: No held-out task acceptance authorizes default policy mutation; explicit actuator is implemented and disabled by default.
- **universal weighted hardware score or tier/CE taxonomy merge**: Incomparable objectives and independent taxonomies require hard constraints and named orderings.

## Evidence-only remaining work

- `hardware-unvalidated`: ISA dispatch and clocks.
- `hardware-unvalidated`: ORT and OpenVINO on target machines.
- `hardware-unvalidated`: NVIDIA native execution/performance and MIG isolation.
- `hardware-unvalidated`: AMD native execution/performance.
- `hardware-unvalidated`: Intel XPU/NPU native execution/performance.
- `hardware-unvalidated`: Apple Silicon/ANE operator placement.
- `hardware-unvalidated`: Qualcomm/Windows HTP/NPU execution.
- `hardware-unvalidated`: Ascend native execution/performance.
- `hardware-unvalidated`: MUSA native execution/performance.
- `hardware-unvalidated`: Cambricon native execution/performance.
- `hardware-unvalidated`: MetaX native execution/performance.
- `environment-unvalidated`: PJRT/Neuron/TTNN/Vulkan/OpenCL deployed execution.
- `hardware-unvalidated`: FP16/BF16/INT8 quality and performance acceptance.
- `hardware-unvalidated`: PMem/DAX/CXL allocations and performance.
- `hardware-unvalidated`: SPDK/cuFile/GDS/direct-I/O native path and zero-copy counters.
- `environment-unvalidated`: NVMe-oF/FC/Ceph/Lustre/BeeGFS/DAOS/S3/HSM deployed transport performance.
- `full-research-not-run`: Full LoCoMo/LME-S/LME-V2/BEAM/MemoryArena campaign for the new surface.
- `environment-unvalidated`: Real generative model/judge/agent environment outcomes.
- `environment-unvalidated`: Private memory corpus task outcome and automatic-actuator policy acceptance.
- `environment-unvalidated`: Private Context Economics workload optimum.

## External-only limitation

GitHub integration returns 403 Resource not accessible by integration for branch protection; no supported protection mutation capability. Remote enforcement could not be verified through the administration endpoint. Repo-local gates and expected-head guarded merge were verified.

## Validation and release discipline

Linux Python 3.10–3.14, Windows/macOS 3.13; eight tokenizer versions; full unit suite, numeric audit, five benchmark fixtures, 30 independent feature A/B cases, two Track B modes, source/metadata/actuator/physical/provider regressions, docs/localization/version guards, Hermes and harness E2E. Generation/judge calls remain zero. Tests assert cleanup, corruption rejection, stale generation, source authority, pin/capacity, partial-outcome binding, cold-cost fallback and no fixture-to-hardware promotion.

The offline merge helper binds expected head, newest workflow attempt, historical archive and review state. GitHub merge still receives expected_head_sha and normal merge method. Post-merge run identities are recorded in a forward-only documentation descendant; no published history is rewritten.

The [implementation guide](../docs/24-full-power-implementation.md) explains configured contracts, concrete SDK paths and the boundary between a host-consumable placement replica and authoritative source memory.

## Exact-head review repairs

Four actionable findings were repaired with regressions: path-based preparation now bounds complete bundle size/traversal before hashing and loading; snapshot save and restore share a UTF-8 byte limit; empty outcome attachment cannot create measured evidence; and the advertised harness extra includes LangGraph/Deep Agents, exercised through a constraints-only CI install. The complete local suite now has 600 tests (two platform/dependency skips).

A second completed review added three lifecycle repairs: atomic snapshot publication and retry after failed fsync; session-owned verified artifact copies that survive source replacement; and process-tree deadlines covering environment reset, policy, step and close. Corresponding failure/race/timeout regressions bring the local suite to 603 tests (two platform/dependency skips).

The final closeout regression extends the same fixes to actual opened descriptors and storage callback process deadlines. Snapshot short writes, write exceptions, publication failures and failed retry paths leave no authoritative partial file. Artifact FIFO/symlink/regular substitutions fail before reads; frozen sibling bundles retain the consumed-byte receipt identity. Storage stage/commit/size/read/abort/close are interruptible, timeout cleanup is bounded, and uncertain remote publication is recorded without successful-write credit. Environment exceptions and exhausted launch/result deadlines cannot publish success. The combined full local suite ran 669 tests with zero failures/errors and three platform/dependency skips; numeric audit passed 10/10, all five Evaluation Fabric smoke fixtures passed, and docs/completion/version/merge/whitespace guards passed.

Remote corrective commit `02d62165e0403e36e322fdfd466e7d2f882ac952` was reconciled forward with the independent closeout regression work. Its descriptor, SDK and transport test cases remain, with the single consolidated implementation checking directory/file descriptors, freezing sibling content, owning all callback processes, and recording bounded cleanup and timeout transaction status.

The concurrent macOS cleanup correction `d00b237b0fbcae28a6f2b233c02006ea52729c4e` is also preserved: an exited group may report EPERM on Darwin, while a permission failure for a live owned worker still propagates. Its regression is retained against the consolidated process boundary.

The Windows enumeration repair from `2bd6e5186a74c576a598ea264363ee7ef5b73118` is preserved with its regression. File identities come from os.stat; on POSIX that stat is relative to the pinned directory descriptor.

Exact-head macOS CI exposed the remaining exit/reap window: poll may briefly report a live leader after its process group becomes unsignalable. A bounded 200 ms wait now confirms actual exit before accepting EPERM. The regression covers exited, still-live and concurrently exiting workers.

Final group-cleanup review repair requires an ESRCH result from a process-group liveness check before suppressing EPERM after leader exit. A live or permission-denied descendant remains a cleanup error. The shared environment/storage cleanup preserves that rule. Exhausted environment deadlines now fail before Windows Job Object creation. Linux accounting rechecks group membership after a leader exits between proc sampling and poll, while real surviving helpers still fail.

Lost mounted/S3 commit acknowledgements remain indeterminate with zero successful-write credit, even when abort completes. Regression verifies the published object remains recoverable. Linux accounting filters unrelated groups before opening their protected records.

Mounted commits now bound pending/existing reads on checked descriptors and publish a separate private validated inode. Regressions cover growth, symlink/FIFO swaps, source changes during linking, oversized existing objects and cleanup. DiskANN construction uses the documented memory-only API, generates zero disk artifacts, preserves zero-based external result IDs and releases failed partial builds.

Protected mounted publication now retains Linux kernel leases or Windows write/delete share denial through descriptor-based publication. A real same-credential writer causes the Linux worker to stop without publishing or receiving write credit. Missing protection fails closed; stock macOS Python lacks the required file-leases entitlement, so its rejection path is explicitly tested. Mounted commit is bounded to one second, including factory-created transports. Shard capacity is admitted before advanced indexing can allocate the shard.

The last review repairs preflight float32 shard size before normalization, bind supplied CE observations to this exact source receipt, retain the mounted root identity through descriptor-relative operations, and isolate exhaustive old-shard retirement errors from successful generation publication. Failed retirement handles remain available for cleanup retry; further rebuilds cannot silently accumulate leaked generations. Concurrent source-binding and shard-admission commits remain in the forward history.

Linux 3.14 CI exposed disappearing procfs I/O permissions during worker exit. Intermediate bounded-wait and membership-snapshot repairs were superseded after review showed that a helper could join after enumeration. The final path never treats waitpid or a subsequent dead-state observation as complete lifetime group accounting: any denied member read raises `ProcessGroupAccountingUnavailable`. Advisory probes explicitly defer with zero generation calls and no availability/acceptance credit. Regressions cover late helper creation, all leader states, no exit wait, and complete probe cleanup. The real probe contract permits either verified availability or this precise fail-closed deferral; generic worker errors remain test failures.

The Windows corruption regression now closes its quarantined mounted worker before deleting the temporary root, matching the retained handle lifetime contract.

Environment and storage callbacks now receive kernel descendant containment before deserialization: Linux group/session/namespace escape is denied by an inherited seccomp filter, Darwin workers cannot fork under Seatbelt, and Windows keeps no-breakaway Job ownership. Missing containment rejects execution. Regressions prove detached helper creation cannot publish success, Linux descendants inherit the restrictions through exec, and ordinary Linux child/thread execution remains possible. Receipts disclose the mechanism. The Windows mounted-timeout regression checks worker/parent handle release and permits at most one second for a transient sharing violation before failing directory deletion.

Oversized transport callback responses now preserve all bounded envelope metadata when replacing the result with `ValueError`. Regression exercises stage, commit, abort and close, proving the intended error reaches the caller with the original containment/evidence metadata.

Transport responses are limited to exact built-in scalar/byte types before serialization. A custom response object cannot transfer executable pickle reconstruction into the parent; the regression proves its reduce hook is never called and no successful write is credited.

A full regression’s PID-based liveness assertion exposed a local executor/procfs namespace mismatch: it read a host telemetry process instead of the helper. The helper now records its own procfs PID/start time, and cleanup refuses to certify an extant group from mismatched procfs evidence. Cleanup now waits up to five seconds for Linux group members or Windows Job processes to terminate; persistent descendants cause an explicit failure. Tests cover both observed exit and bounded rejection, alongside the real helper timeout test.

Linux cleanup also probes the kernel process group before and after its procfs scan. Permission denial propagates; an existing group with no visible members remains unproven. Visible zombies certify termination only with complete procfs visibility; hidepid or ambiguous stacked mounts require actual group disappearance. Regressions cover denied/absent groups, invisible members, visible zombies and hidden/stacked procfs mounts.

The model and shadow provider entrypoints enforce the same inherited descendant containment as environment/storage workers. Darwin model preparation stays inside the already-owned outer worker to respect its no-fork policy. Linux accounting rejects a mismatched procfs PID namespace before enumeration; timeout regressions bind helper-owned procfs PID and start time. The reconciled candidate passed 657 local tests, zero failures/errors, three expected skips.

The final Darwin thread-policy review corrected the interpretation of `LocalEncoder(isolated=True)`: it declares the existing worker boundary and permits explicit thread control, without spawning a worker. Both model-worker calls retain this declaration on every OS. Regressions first reproduced rejection on the prior head, then exercised actual local Torch baseline and ORT/OpenVINO candidate construction, explicit thread options and a forbidden-subprocess guard. The corrected full suite passed 659 tests, zero failures/errors, three expected skips.

The CE CLI now uses the shared checked-descriptor reader instead of pathname stat/read. FIFO, symlink and oversized regular replacements are rejected before parsing; post-check growth stops after at most 8,000,001 bytes without creating output. Valid advice retains its checksum and default-false mutation boundary. Focused regressions reproduced the prior bypass and pass after repair; the full local suite passed 662 tests, zero failures/errors, three expected skips.

The standalone merge-admission CLI uses the same checked-descriptor reader under its original 8 MiB bound. Regressions cover FIFO/symlink/oversized replacement, bounded growth without admission, guaranteed descriptor closure on failure, and direct `python -S` execution from another directory. The full local suite passed 665 tests, zero failures/errors, three expected skips.

Merge admission now requires a freshly and independently observed `--expected-base` and rejects snapshot/base mismatch. The caller rechecks head/main immediately before GitHub normal merge and verifies the actual ordered merge parents against the checksum-bound admission receipt before release/archive acceptance. The API has no atomic expected-base guard; any observed base movement requires renewed evidence and admission. Regressions reject changed bases, wrong merge parents and tampered receipts.

Allocation close attempts every eviction before reporting cleanup failures. Successfully released allocations are removed once; failed callbacks retain evicted, non-acquirable ownership for explicit retry, and in-flight leases retain data until their normal release boundary. The independently prepared allocation commit `ec7373ea3d9e7f06bd0864c016f8bd7e095863b8` is preserved in the parent chain. Combined full validation passed 669 tests, zero failures/errors, three expected skips; numeric 10/10, five smoke fixtures and release guards passed.

## Final exact-head and main gates

| Stage | Workflow | Run | Conclusion |
| --- | --- | --- | --- |
| PR head | THM Hermes integration | [34726090606](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726090606) | success |
| PR head | THM harness integrations | [34726090612](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726090612) | success |
| PR head | THM correctness | [34726090623](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726090623) | success |
| Accepted main | THM harness integrations | [34726430677](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726430677) | success |
| Accepted main | THM Hermes integration | [34726430678](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726430678) | success |
| Accepted main | THM correctness | [34726430673](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34726430673) | success |

Review status: reviewed. Actionable findings remaining: 0. The exact admission receipt is embedded in the JSON ledger. The archive pins accepted implementation bytes; this post-merge report is a forward-only documentation descendant.

## Final release identities

| Identity | Value |
| --- | --- |
| Base main | `b96b82f027ca128072e3c0b3899331af1155b39e` |
| PR initial head | `bb6808467fcd076e264dbbdfe4aebd4984f0b73a` |
| PR handoff head | `36b353ca51827a3a5b2f0c4c38972ab288e0c290` |
| PR final head | `d33fc70677e61d6733fdbc8c0f71bced6168dff4` |
| Accepted merge/main | `de26865f36df2205c29a470e51c65d5bf9beca4e` |
| Accepted tree | `e8521b03501a015e9f5fc8b94fa99ddb3b6080ab` |
| Normal merge parents | `b96b82f027ca128072e3c0b3899331af1155b39e, d33fc70677e61d6733fdbc8c0f71bced6168dff4` |
| Stable archive | `de26865f36df2205c29a470e51c65d5bf9beca4e` |
| Package | `1.5.0` |

Exact review: {"clean_review_comment_id": 5649485866, "clean_review_url": "https://github.com/xngg1021/thm-tiered-hot-memory/pull/21#issuecomment-5649485866", "completed_at": "2026-09-12T23:48:00Z", "head_sha": "d33fc70677e61d6733fdbc8c0f71bced6168dff4", "request_comment_id": 5649457403, "resolved_threads": 30, "result": "Didn't find any major issues", "reviewer": "chatgpt-codex-connector[bot]", "status": "reviewed", "summary_comment_id": 5648110047, "unresolved_actionable": 0}

The complete parent chain is in the JSON ledger. The documentation descendant is identified by Git history and the final PR conversation receipt.
