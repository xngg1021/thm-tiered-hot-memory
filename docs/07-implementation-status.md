# Implementation status and evidence boundaries

Date: 2026-09-07. Package line: **1.4.0 development**. Historical design remains in [architecture](02-架构设计.md); broader targets remain in the [validation contract](03-validation-contract.md). A design requirement, benchmark result or old private report is not automatically an implementation claim.

| Area | Current public state | Evidence / remaining boundary |
| --- | --- | --- |
| T0–T3 model | Retained | Tiers are residency/access classes; they are not renamed by 1.4 |
| Index maintenance | Implemented in `scripts/thm.py` | Source identity, profile binding, CAS/atomic publication, explicit feedback and migration tests |
| Retrieval | Sparse/dense/hybrid scoped retrieval implemented | Protocol 2 measures retrieval coverage/ranking/latency, not generated-answer accuracy |
| Harness integration | Hermes provider plus harness-neutral/adapters implemented | Exact runtime/workflow evidence remains revision-specific |
| Observation scan | Implemented as zero-weight `mention_observed` | Does not create hits, confirmations, validity extensions or causal-use claims |
| Decay/activity policies | Multiple kernels and activity-only plan implemented | Parameters remain tunable heuristics; no user-specific optimum without private explicit-hit chronology |
| Miss/prefetch telemetry | **1.4 shadow implementation** | Explicit events and penalties; aggregation never promotes telemetry to activity |
| T1 warm directory | **1.4 shadow implementation** | Locator-only deterministic projection; does not write warm files or substitute summaries for evidence |
| Value-aware T0 recommendation | **1.4 shadow implementation** | Token-denominated comparison; incomplete telemetry suppresses actionable deltas |
| Speculative prefetch | **1.4 shadow implementation** | Co-demand heuristic trained only on explicit demand events; prior prefetches cannot train it |
| Adaptive resident budget | **1.4 shadow implementation** | One bounded suggestion step; no automatic Hermes/T0 budget mutation |
| Automatic promote/demote | Not implemented | Existing public tools still emit proposals/recommendations only |
| Fact truth/conflict resolution | Not inferred | Validity, activity, residency and truth remain separate concerns |
| Whole task-economic optimum | Not established | Requires held-out runtime/task outcomes and measured miss/reacquisition/prefetch costs |
| Private user deployment | Not performed by repository CI | Private memory text, catalogs and telemetry must remain outside public fixtures |

## 1.4 control-plane boundary

The new public API is documented in [14-residency-control-plane.md](14-residency-control-plane.md). Its central invariant is:

> **measurement and recommendation are permitted; hidden automatic tier mutation is not.**

Current T0 rows with unknown counterfactual miss cost are protected under incomplete telemetry. A stale-resident failure triggers review before residency ranking. `planned_retrieval` is not a miss. Successful prefetches are intentionally excluded from the demand training set, preventing a self-reinforcing “prefetch → observed → prefetch more” loop.

The optional residency catalog is a non-authoritative local overlay. It can add resident-cost estimates, miss-cost estimates, safe locators and scope labels; it cannot override canonical tier, status, validity, pin state, events or source identity.

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
