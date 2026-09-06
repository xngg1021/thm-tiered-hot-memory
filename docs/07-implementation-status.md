# Implementation status and evidence boundaries

Date: 2026-09-06. Public CLI version: 1.1.0. Historical design remains in [architecture](02-架构设计.md); broader acceptance targets remain in the [validation contract](03-validation-contract.md). A requirement or older private test report is not evidence that this public script implements it.

| Area | Public 1.1 state | Evidence or remaining work |
| --- | --- | --- |
| Six original commands | Implemented with argument validation and explicit errors | Actual engine tests |
| Identity | Stable ID plus complete source fingerprint; no 24-character uniqueness | Cross-store and same-prefix tests |
| Profile state | Resolved memory-directory binding and per-directory state by default | Separate-state and shared-state rejection tests; no OS sandbox claim |
| Index publication | Local OS lock, compare-and-swap, previous-index backup, atomic replacement/readback | Real concurrent child processes and replacement failure tests |
| Feedback | Event-ID deduplication; one counted confirmation per day; evidence reference required | Repeat, conflict, ambiguity and source-change tests |
| Activity | Strict dates/types; relocation/display/retrieval do not increase score | Direct function tests; old numeric tests remain historical |
| Residency | Cost and explicit pin separated; due demotion/archive suggestions | New unpinned high-cost entries can be suggested; legacy protection preserved |
| Migration | Explicit preview/apply with exact-byte backup; unknown fields retained | Synthetic v1 tests; no real user migration in this release |
| Validity | Basic status and optional date-interval filters | Does not infer truth or contradictions |
| T0 content changes | Not performed | Native Hermes memory tool remains the write path |
| Full multi-file T0-T3 paging | Not implemented | No claimed seven-stage recovery suite for this public CLI |
| Task semantic retrieval | Not implemented | `find` is a unique record selector, not a semantic retrieval service |
| Whole model-request budget | Not implemented | Audit JSON is not prompt injection; native integration requires its own observation |
| MemoryProvider integration | Not implemented | Public hook research only |
| Real models, real data and production cron | Not run or changed here | No benchmark superiority or deployment claim |
| Native Windows/macOS | Code paths and CI matrix supplied | Local Linux results do not count as native passes; consult exact-commit CI |

The earlier public engine at 4e9b5d8 was 289 lines and retained v1 defects. Its recorded diagnostic probes are [preserved](../reports/2026-09-06-legacy-engine-probes.json); CONFIRMED in that record means a defect reproduced. The [historical reproduction script](../scripts/reproduce_legacy_engine_findings.py) checks the exact old Git blob and deliberately rejects new source. New regression tests target [the current main file](../scripts/thm.py).

A separately delivered private reference implementation was reported to have 53 tests. Its bytes are not present in this repository and were not used to certify this public CLI. No performance, tier-movement or host-integration result is transferred between the two implementations.

The related-work survey is a dated documentation comparison. Its statements about the repository containing no public engine describe the earlier documentation-only snapshot. Current installable scope is this page and the engine guide. Versioned historical material remains available rather than silently rewritten.
