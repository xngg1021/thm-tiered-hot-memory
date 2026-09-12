# Implementation status and evidence boundaries

## Current 1.5 zero-touch implementation

Configured extension sessions, five public Python SDK bindings, 42 physical family lifecycles, owned allocations, sharded indexes, joint selection, explicit actuator transactions, environment/outcome attachment and the independent CE bridge are implemented. All 28 design domains have source and test mappings in the completion ledger. The catalog preserves native/automatic maturity separately from configured L4 lifecycle fixtures.

[Zero-touch runtime](20-zero-touch-runtime.md), [Provider Fabric](21-provider-fabric.md), [optimizer](22-runtime-optimizer.md) and [vector indexes](23-vector-index-providers.md) are implemented with host/SDK-fixture and cross-platform correctness gates. Background local text-model preparation uses independent vector profiles and can retain a warm worker after admission. Unsupported or over-budget preparation defers to the reference. The [matrix](provider-matrix.md) explicitly retains L0/L1/L2 boundaries and no L5 vendor acceptance. The [bb16760 post-fix retest](../reports/2026-09-09-post-fix-retest-bb16760.md) completed the earlier auto-safe/reference-fallback and CPU batch 1/4/8/32 acceptance; ISA dispatch and optional ORT/OpenVINO hardware outcomes remain separate.

## Evaluation Fabric implementation boundary

[Evaluation Fabric](18-evaluation-fabric.md) now supplies typed contracts, five native input projections, V2 and MemoryArena memory interfaces, deterministic fixtures, shared dataplane metrics, physical probe receipts and bounded offline acceptance. Three-layer evidence and all eight README section identities are checked. Full V2/BEAM/MemoryArena campaigns and real hardware performance remain unrun. Package version is 1.5.0; exact release acceptance is recorded in the completion ledger. CI and exact-head review results belong to the successor PR receipt, not to prospective claims in this status document.

Historical 1.4 acceptance baseline (2026-09-07). Package line: **1.4.0 accepted/stable implementation milestone** at `e6e4dda5835e3cb345207457d5491131c6959b2c`, recovery pointer `archive/v1.4.0-stable`. Historical design remains in [architecture](02-架构设计.md); broader targets remain in the [validation contract](03-validation-contract.md). A design requirement, benchmark result or old private report is not automatically an implementation claim.

| Area | Current public state | Evidence / remaining boundary |
| --- | --- | --- |
| T0–T3 model | Retained | Tiers remain residency/access classes; 1.4 does not rename them |
| Index maintenance | Implemented in `scripts/thm.py` | Source identity, profile binding, CAS/atomic publication, explicit feedback and migration tests |
| Retrieval | Sparse/dense/hybrid scoped retrieval implemented | Protocol 2 measures retrieval coverage/ranking/latency, not generated-answer accuracy; 1.4 did not change retrieval-path code |
| Harness integration | Hermes provider plus harness-neutral/adapters implemented | Accepted 1.4 merge passed main Hermes and multi-harness workflows |
| Observation scan | Implemented as zero-weight `mention_observed` | Does not create hits, confirmations, validity extensions or causal-use claims |
| Decay/activity policies | Multiple kernels and activity-only plan implemented | Parameters remain tunable heuristics; no user-specific optimum without private explicit-hit chronology |
| Miss/prefetch telemetry | **1.4 stable shadow implementation** | Raw miss and residency-avoidable miss are separate; planned retrieval is not a miss; prefetch never trains its own demand signal; unknown fields fail |
| T1 warm directory | **1.4 stable shadow implementation** | Strict locator-only projection; topic comes from safe locator stem, never legacy key/summary/source text |
| Hermes T1 prompt snapshot | **1.4 stable opt-in runtime implementation** | Disabled at budget 0; refreshes on session boundary only; selected locators must resolve to files inside current profile `memories/` |
| Value-aware T0 recommendation | **1.4 stable shadow implementation** | Uses avoidable miss penalty vs repeated carry cost; exact 0/1 packing for bounded finite token objective; demand/per-item sample gates suppress weak deltas |
| Speculative prefetch | **1.4 stable shadow implementation** | Current canonical seed + explicit-demand co-occurrence only; bounded locator/tiny-excerpt candidates |
| Adaptive resident budget | **1.4 stable shadow implementation** | One bounded suggestion step driven by avoidable miss, context pressure, prefetch pollution and stale risk; no automatic mutation |
| Automatic promote/demote | Not implemented by design | Existing public tools emit proposals/recommendations only; automation remains evidence-gated |
| Fact truth/conflict resolution | Not inferred | Validity, activity, residency and truth remain separate concerns |
| Whole task-economic optimum | Not established | Requires held-out runtime/task outcomes and measured miss/reacquisition/prefetch costs |
| Private user deployment | Not performed by repository CI | Private memory text, catalogs and telemetry must remain outside public fixtures |

## 1.4 acceptance evidence

Feature PR #5 was merged normally from feature head `a1bd23d6abfa1181327d9ec23887cf3903be3ea0` into accepted merge commit `e6e4dda5835e3cb345207457d5491131c6959b2c`. The accepted merge then produced:

- THM correctness run `34059895478`: **success**;
- THM Hermes integration run `34059895474`: **success**;
- THM harness integrations run `34059895461`: **success**;
- THM retrieval benchmark run `34059936492`: **skipped by path gate**, because 1.4 did not change retrieval-path files; this is not a new retrieval result.

See [the human closeout](../reports/2026-09-07-v1.4-closeout.md) and [machine-readable closeout](../reports/2026-09-07-v1.4-closeout.json).

## 1.4 control-plane invariants

The shadow control API is documented in [14-residency-control-plane.md](14-residency-control-plane.md); the opt-in Hermes surface is documented separately in [15-hermes-warm-directory.md](15-hermes-warm-directory.md). The central invariant is:

> **measurement and recommendation are permitted; hidden automatic tier mutation is not.**

Additional invariants enforced in code and tests:

- only explicit `avoidable=true` misses contribute resident-capacity benefit; raw unavoidable misses remain diagnostics;
- global all-task count and explicit-demand-task count are separate, so prefetch-only/planned-retrieval-only tasks cannot dilute residency need rates;
- `min_item_demands` is enforced as a real item-level evidence gate; low-support current T0 stays protected/reviewed rather than becoming false zero-value;
- telemetry and catalog structure fail on unknown fields/identities instead of accepting likely typos or stale metadata;
- a pinned nonresident item is not automatically promoted;
- current T0 with unknown counterfactual miss cost is protected/reviewed under incomplete evidence rather than silently scored as zero;
- budget selection is exact for the finite supplied token objective rather than value-density greedy, with explicit public limits of 100,000 budget units and 1,024 entries;
- prefetch seeds must resolve to current canonical items;
- successful prefetches do not become future demand training examples;
- warm directory text is derived from safe locators and cannot leak legacy source-prefix keys;
- the Hermes opt-in directory verifies every selected target exists, remains inside the current profile memory root after symlink resolution, and is a file;
- native memory writes do not refresh the frozen directory block inside the current session; a later session boundary rebuilds it;
- CLI/provider regression tests byte-compare canonical index and native memory files before/after 1.4 read-only operations.

The optional residency catalog is a non-authoritative local overlay. It may add resident-cost estimates, counterfactual miss-cost estimates, safe locators and scope labels; it cannot override canonical tier, status, validity, pin state, events or source identity.

## Evidence ladder

Use the weakest accurate label:

1. **unit/contract test** — function and invariant behavior;
2. **synthetic replay** — policy behavior on constructed traces;
3. **trace replay** — real historical events with simulated placement;
4. **runtime A/B** — actual host/provider execution under controlled alternatives;
5. **task outcome** — same tasks with quality/success plus cost/latency/reacquisition.

1.4 reached implementation/integration stability at the accepted merge SHA. Only levels 4–5 can establish that an adaptive residency policy is better for a tested workload. Protocol 2 retrieval results and Hermes lifecycle E2E remain valuable but answer different questions. The Hermes T1 directory provider tests establish integration/read-only/frozen-snapshot behavior; they do not establish task-quality benefit.

## Historical boundaries

The legacy public engine, 1.1 hardening, 1.2 retrieval work and 1.3 harness integration remain recoverable through [the version history map](12-version-history.md). The stable 1.4 code/content milestone is frozen at `archive/v1.4.0-stable`; later closeout documentation does not move that pointer or rewrite prior history.

## Unreleased retrieval successor

The opt-in Python entity projection and its Protocol 2 evidence are documented in [the zero-LLM frontier](16-zero-llm-retrieval-frontier.md). It does not enable a harness option, change residency/activity/validity semantics, or move the 1.4 stable pointer.

## Unreleased runtime integration

The canonical SearchIndex now exposes typed default-off RetrievalFeatures and bounded search_many; existing search/entity and residency behavior remain compatible. Optional runtime setup, profile/vector identity, isolated calibration and the final local experiment contract are described in [runtime architecture](17-zero-llm-heterogeneous-runtime.md). Z6 CPU/CUDA/auto-throughput evidence now exists at b1f8119; post-corrective hardware acceptance remains pending; this is a performance evidence boundary, not a correctness merge blocker.

## 2026-09-09 repository reconciliation

PR #15 merged normally at `70180dd4a319c62cc839ee1b7f39b5573b3a1f66`; PR #16 merged normally at `3512aa02015d6eb10e390e1fe7f06309fd84b6c6` after absorbing that main. Scope cleanup, transitive reference semantics, vector snapshot publication, conservative OS locality and exclusive physical-root ownership are integrated. Seven actionable review findings were forward-fixed, the exact final source received clean Codex review, 424 tests passed, and post-merge correctness on all three OSes plus Hermes/harness integrations passed. No Open/Draft/unmerged PR remains.

At that 2026-09-09 reconciliation, bounded acceptance and physical storage were **Unreleased**; package version 1.4.0 and its stable archive did not move. Their implementation surface is now included in the 1.5 acceptance above. The [closeout receipt](../reports/2026-09-09-open-pr-reconciliation-closeout.md) records exact lineage, review/CI evidence, the final documentation publication and remaining measurements; the [physical storage contract](physical-storage-fabric.md) is the current short acceptance entrypoint.


## Post-local corrective evidence

See the [current corrective contract and short retest](19-post-local-corrective.md). Z6 CPU/CUDA/auto-throughput and local NTFS/NVMe are machine-observed at b1f8119. Aggregate parity, strict parity, calibrated policy and post-fix acceptance remain separate claims. Auto-safe now allows a measured reference fallback; lack of acceleration does not itself fail correctness. No version/stable promotion or full-dataset acceptance is implied.

## 1.5 implementation and evidence contract

[1.5 implementation surface](24-full-power-implementation.md) defines the executable configured provider/storage lifecycle, allocation and joint-planning APIs, explicit actuator, five benchmark/environment/outcome interfaces, independent CE bridge, and LangGraph/Deep Agents lifecycle. Automatic memory mutation remains false and rejected features remain default-off. Hardware, full-research and real task evidence are separately recorded in the [completion ledger](../reports/2026-09-12-thm-full-power-completion.md).

## 1.5 accepted closeout

THM 1.5.0 is implementation/integration stable at `de26865f36df2205c29a470e51c65d5bf9beca4e`, normally merged by PR #21 from `d33fc70677e61d6733fdbc8c0f71bced6168dff4`. The immutable `archive/v1.5.0-stable` pins that accepted implementation main. Exact-head and post-merge correctness, Hermes and harness workflows passed; 669 local unit tests ran with zero failures/errors and 3 expected skips. The 28 domains are implemented with zero external implementation gaps; remaining hardware, target-machine, full-research, private-workload and real-environment work is evidence-only. [Final acceptance receipt](../reports/2026-09-12-v1.5-closeout.json). Remote branch-protection administration remains an integration 403 governance limitation.
