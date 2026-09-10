# Zero-touch heterogeneous provider fabric — engineering closeout

This Unreleased implementation is published in [PR #20](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20). The runtime/provider implementation and the subsequent Chat corrective pass are engineering-validated; release closure still requires a valid exact-head Codex review of the final PR head, a normal expected-head merge, and successful post-merge `main` CI. A review-service failure is not review approval.

## Identity and scope

| Identity | Value |
| --- | --- |
| Base main | `2d5c2adcf994edd8b7bb3c0546983ba9531af392` |
| Validated corrective implementation head | `6b309c42d28bbeafc40a23bbc0bfab89702aad0f` |
| Historical post-fix hardware head | `bb1676007b0f86dec0267585c56136c82157ae54` |
| Unchanged stable archive | `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c` |
| Package version | `1.4.0`; no promotion |

The implementation adds lazy provider contracts and catalog discovery, public hardware/driver observations, checksummed profiles and immutable compiled artifacts, safe bootstrap, passive telemetry, bounded online queues, material-gain/Pareto admission, session pinning, preemptible isolated exploration, resident indexes/transfers, local-model preparation in retained workers with private index replicas, and harness/MCP/Hermes lifecycle integration. Physical plans bind the actual placement and regenerate on fallback.

The catalog has 71 entries: 51 L4, one L2, 12 L1 and seven L0. **There are no L5 hardware-accepted entries.** L4 is implemented lifecycle/fixture evidence, not a claim that every vendor SDK or accelerator ran here. The [provider matrix](../docs/provider-matrix.md) and [source registry](../docs/provider-sources.json) retain per-provider API, platform, license and executable-boundary provenance.

## Chat takeover corrective pass

After the original Work execution stopped making progress, the successor was reviewed and forward-fixed on the same branch. The corrective pass did not change THM memory authority or retrieval-policy semantics. It closed these implementation/evidence issues:

- retained Windows warm workers renew the Job Object CPU ceiling **cumulatively**, matching `JOB_OBJECT_LIMIT_JOB_TIME` semantics;
- a paired replay over one observed query is explicitly **observed-request-only evidence**, not a provider-wide equivalence certificate for a different embedding implementation;
- `reference`, `auto-safe` and `auto-throughput` do not activate an alternate model from observed-request-only evidence; only explicit `approximate-performance` may do so after a session boundary;
- an active alternate-model session pin cannot be replaced merely because a different workload/settings key appears mid-session;
- one model-serving failure produces one quarantine increment rather than duplicate failure accounting;
- alternate-model receipts distinguish authority embedding identity from the private runtime profile and expose their limited evidence scope;
- resident vector handles bind the concrete vector snapshot revision, so same-generation vector republication cannot reuse stale embeddings;
- HNSW persisted observations bind `hnswlib` package identity, while native accelerators with unknown driver identity remain process-local;
- shadow preemption is sticky across the thread-start/child-publication race;
- successful model-worker responses are rechecked against the complete resource budget before publication;
- Linux shadow accounting aggregates the worker process group rather than only the leader PID;
- the previously proposed provider-supplied top-k+1 cutoff witness was rejected by review as insufficient. Strict admitted ranking now uses an **independent complete reference verification**. No bounded-cutoff performance claim remains.

## Ledger A: retrieval engineering

| Observation | Evidence and boundary |
| --- | --- |
| Speaker SQL reuse | Two same-generation searches issue one `SELECT DISTINCT speaker`; replacing the scope causes the next search to issue the second query. |
| Neighbor retrieval | Batched CTE lookup preserves the original per-row ordering/content. This is query-pattern/parity evidence, not a wall-time claim. |
| Row cache | Copy-on-read prevents returned-row mutations from changing cached source rows; generation identity invalidates reuse. |
| Tokenizer calls/cache hits | The public `encode_ordinary` path uses an exact whole-prefix bounded cache. The second identical prefix performs zero additional encoder calls. No private tiktoken BPE/regex API remains. |
| Tokenizer releases | CI covers tiktoken 0.7.0 through 0.14.0 inclusive using in-memory vocabularies and no vocabulary/model download. |
| Admitted online ranking | Strict resident-provider results are checked against an independent complete host reference before acceptance. A provider that omits the true top row fails the guard. |
| Ranking optimization boundary | The rejected top-k+1 cutoff certificate is not used as proof. Any future bounded certificate requires a provider-independent coverage bound and separate evidence. |
| Packing/source semantics | Exact final counting, stable order, selected/ranked/source identities and generation-bound retrieval remain checked. |

These are deterministic engineering observations. They are **not** native-device latency, throughput, power, end-to-end dataset quality or agent-outcome evidence. In particular, the strict ranking guard currently prioritizes correctness over accelerated steady-state speed.

## Ledger B: fabric correctness and integration

The current corrective implementation suite contains **561 tests**. Core-only ignition has zero native-provider, network and generation calls. Numeric auditing passes ten historical specification checks. Document/version-history checks and bounded evaluation smoke pass; evaluation smoke performs zero generation/judge calls and does not claim full-dataset acceptance.

The corrective regressions additionally verify vector-snapshot invalidation, HNSW dependency freshness, sticky preemption, post-response resource checks, Linux process-group accounting, independent ranking verification and cross-platform test portability.

| Tested head | Workflow | Result |
| --- | --- | --- |
| `6b309c4` | [Correctness 34435176859](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34435176859) | Success: Ubuntu, Windows, macOS and all tokenizer rows |
| `ca4d5f1` | [Harness 34401841275](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34401841275) | Success on implementation source |
| `ca4d5f1` | [Hermes 34401841296](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34401841296) | Success on implementation source |

The final closeout/documentation commit that follows `6b309c4` must pass its own exact-head correctness gate. The implementation-source integration results retain their own exact identity rather than being relabeled as later runs.

## Ledger C: real-hardware performance

**New-fabric real-hardware performance remains unaccepted.** No new machine benchmark, full-dataset campaign, model/vendor-SDK installation, positive ISA dispatch validation, ANE placement validation or generative/judge evaluation was performed for this closeout. SDK fixtures cannot establish native acceleration, quality improvement, resource savings or agent outcomes.

The earlier [post-fix bb16760 retest](2026-09-09-post-fix-retest-bb16760.md) remains historical evidence. It is not a benchmark of this new fabric. [Issue #13](https://github.com/xngg1021/thm-tiered-hot-memory/issues/13) remains the real-machine evidence ledger for still-open dispatch/backend/low-precision questions. No repeated user benchmark is required for this merge.

## Review and release gates

All six actionable Codex threads found during the takeover review have been answered with forward fixes and regressions and are resolved. The earlier service failures that never produced a valid review are not counted as approval.

Required final sequence:

1. the final closeout/documentation head passes correctness/documentation checks;
2. a **valid exact-head Codex review** completes with no actionable unresolved P1/P2 findings;
3. PR #20 is merged by normal merge with an expected-head guard;
4. post-merge `main` CI is green;
5. any post-merge closure record retains the exact merge/main identities.

Activity, hit, confirmation, validity, tier and memory-authority semantics remain unchanged. Stable/package promotion and new hardware/full-dataset acceptance remain outside this closeout.
