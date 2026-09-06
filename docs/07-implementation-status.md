# Implementation status and evidence boundaries

Date: 2026-09-07. Package line: **1.4.0 accepted/stable implementation milestone** at `e6e4dda5835e3cb345207457d5491131c6959b2c`, recovery pointer `archive/v1.4.0-stable`. Historical design remains in [architecture](02-架构设计.md); broader targets remain in the [validation contract](03-validation-contract.md). A design requirement, benchmark result or old private report is not automatically an implementation claim.

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
