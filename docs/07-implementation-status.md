# Implementation status and evidence boundaries

Date: 2026-09-07. Package line: **1.4.0 development**. Historical design remains in [architecture](02-架构设计.md); broader targets remain in the [validation contract](03-validation-contract.md). A design requirement, benchmark result or old private report is not automatically an implementation claim.

| Area | Current public state | Evidence / remaining boundary |
| --- | --- | --- |
| T0–T3 model | Retained | Tiers remain residency/access classes; 1.4 does not rename them |
| Index maintenance | Implemented in `scripts/thm.py` | Source identity, profile binding, CAS/atomic publication, explicit feedback and migration tests |
| Retrieval | Sparse/dense/hybrid scoped retrieval implemented | Protocol 2 measures retrieval coverage/ranking/latency, not generated-answer accuracy |
| Harness integration | Hermes provider plus harness-neutral/adapters implemented | Exact runtime/workflow evidence remains revision-specific |
| Observation scan | Implemented as zero-weight `mention_observed` | Does not create hits, confirmations, validity extensions or causal-use claims |
| Decay/activity policies | Multiple kernels and activity-only plan implemented | Parameters remain tunable heuristics; no user-specific optimum without private explicit-hit chronology |
| Miss/prefetch telemetry | **1.4 shadow implementation** | Raw miss and residency-avoidable miss are separate; planned retrieval is not a miss; prefetch never trains its own demand signal |
| T1 warm directory | **1.4 shadow implementation** | Strict locator-only projection; topic comes from safe locator stem, never legacy key/summary/source text |
| Value-aware T0 recommendation | **1.4 shadow implementation** | Uses avoidable miss penalty vs repeated carry cost; exact 0/1 packing for that finite token objective; incomplete telemetry suppresses actionable deltas |
| Speculative prefetch | **1.4 shadow implementation** | Current canonical seed + explicit-demand co-occurrence only; bounded locator/tiny-excerpt candidates |
| Adaptive resident budget | **1.4 shadow implementation** | One bounded suggestion step driven by avoidable miss, context pressure, prefetch pollution and stale risk; no automatic mutation |
| Automatic promote/demote | Not implemented | Existing public tools emit proposals/recommendations only |
| Fact truth/conflict resolution | Not inferred | Validity, activity, residency and truth remain separate concerns |
| Whole task-economic optimum | Not established | Requires held-out runtime/task outcomes and measured miss/reacquisition/prefetch costs |
| Private user deployment | Not performed by repository CI | Private memory text, catalogs and telemetry must remain outside public fixtures |

## 1.4 control-plane invariants

The new public API is documented in [14-residency-control-plane.md](14-residency-control-plane.md). Its central invariant is:

> **measurement and recommendation are permitted; hidden automatic tier mutation is not.**

Additional invariants now enforced in code and tests:

- only explicit `avoidable=true` misses contribute resident-capacity benefit; raw unavoidable misses remain diagnostics;
- a pinned nonresident item is not automatically promoted;
- current T0 with unknown counterfactual miss cost is protected/reviewed under incomplete evidence rather than silently scored as zero;
- budget selection is exact for the finite supplied token objective rather than value-density greedy;
- prefetch seeds must resolve to current canonical items;
- successful prefetches do not become future demand training examples;
- stale/unknown catalog identities fail explicitly;
- warm directory output is derived from safe locators and cannot leak legacy source-prefix keys;
- CLI regression tests byte-compare canonical index and native memory files before/after every 1.4 shadow command.

The optional residency catalog is a non-authoritative local overlay. It may add resident-cost estimates, counterfactual miss-cost estimates, safe locators and scope labels; it cannot override canonical tier, status, validity, pin state, events or source identity.

## Evidence ladder

Use the weakest accurate label:

1. **unit/contract test** — function and invariant behavior;
2. **synthetic replay** — policy behavior on constructed traces;
3. **trace replay** — real historical events with simulated placement;
4. **runtime A/B** — actual host/provider execution under controlled alternatives;
5. **task outcome** — same tasks with quality/success plus cost/latency/reacquisition.

Only levels 4–5 support a production claim that an adaptive residency policy is better for the tested workload. Protocol 2 retrieval results and Hermes lifecycle E2E remain valuable but answer different questions.

## Historical boundaries

The legacy public engine, 1.1 hardening, 1.2 retrieval work and 1.3 harness integration remain recoverable through [the version history map](12-version-history.md). The new 1.4 development line does not rewrite those commits, reports or archive refs.
