# Zero-touch heterogeneous provider fabric — engineering closeout

This Unreleased implementation is published in [PR #20](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20). The implementation source is now engineering-validated; release closure still requires a valid exact-head Codex review of the final documentation head, a normal expected-head merge, and successful post-merge `main` CI. A review-service failure is not review approval.

## Identity and scope

| Identity | Value |
| --- | --- |
| Base main | `2d5c2adcf994edd8b7bb3c0546983ba9531af392` |
| Validated implementation head | `ca4d5f14d088ab9be0e53b01595143182b2072eb` |
| Implementation tree | `ff7126959c337af4719f1ab9e4696589c36de1d9` |
| Historical post-fix hardware head | `bb1676007b0f86dec0267585c56136c82157ae54` |
| Unchanged stable archive | `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c` |
| Package version | `1.4.0`; no promotion |

The implementation adds lazy provider contracts and catalog discovery, public hardware/driver observations, checksummed profiles and immutable compiled artifacts, safe bootstrap, passive telemetry, bounded online queues, material-gain/Pareto admission, session pinning, preemptible isolated exploration, resident indexes/transfers, local-model preparation in retained workers with private index replicas, and harness/MCP/Hermes lifecycle integration. Physical plans bind the actual placement and regenerate on fallback.

The catalog has 71 entries: 51 L4, one L2, 12 L1 and seven L0. **There are no L5 hardware-accepted entries.** L4 is implemented lifecycle/fixture evidence, not a claim that every vendor SDK or accelerator ran here. The [provider matrix](../docs/provider-matrix.md) and [source registry](../docs/provider-sources.json) retain per-provider API, platform, license and executable-boundary provenance.

## Chat takeover corrective pass

After the original Work execution stopped making progress, the successor was reviewed and forward-fixed on the same branch. The corrective pass did not change THM memory authority or retrieval-policy semantics. It closed these implementation/evidence issues:

- retained Windows warm workers now renew the Job Object CPU ceiling **cumulatively**, matching `JOB_OBJECT_LIMIT_JOB_TIME` semantics instead of treating it as a fresh per-request allowance;
- a paired replay over one observed query is explicitly **observed-request-only evidence**, not a provider-wide equivalence certificate for a different embedding implementation;
- `reference`, `auto-safe` and `auto-throughput` therefore do not activate an alternate model from that evidence; only explicit `approximate-performance` can do so, after a session boundary and with the limited evidence scope in the receipt;
- an active alternate-model session pin cannot be closed/replaced merely because a different workload/settings key appears mid-session;
- one model-serving failure produces one quarantine increment rather than duplicate failure accounting;
- alternate-model receipts distinguish the authority embedding profile from the actual private profile and identify the evidence scope instead of labeling it as globally strict;
- the final docs gate exposed a missing EOF newline in `service.py`; the generated wheel copy inherited it, so the source hygiene defect was corrected without changing runtime logic.

## Ledger A: retrieval engineering

| Observation | Evidence and boundary |
| --- | --- |
| Speaker SQL reuse | Two same-generation searches issue one `SELECT DISTINCT speaker`; replacing the scope causes the next search to issue the second query. |
| Neighbor retrieval | Batched CTE lookup preserves the original per-row ordering/content. This is query-pattern/parity evidence, not a wall-time claim. |
| Row cache | Copy-on-read prevents returned-row mutations from changing cached source rows; generation identity invalidates reuse. |
| Tokenizer calls/cache hits | The public `encode_ordinary` path uses an exact whole-prefix bounded cache. The second identical prefix performs zero additional encoder calls. No private tiktoken BPE/regex API remains. |
| Tokenizer releases | CI covers tiktoken 0.7.0 through 0.14.0 inclusive using in-memory vocabularies and no vocabulary/model download. |
| Admitted online ranking | At k=5 on a 500-row fixture, separated candidates use bounded selected/cutoff witness scoring rather than an unconditional 500-row reference rescan. |
| Ambiguous cutoff | A tied boundary falls back to the stable complete reference path. Unknown accumulation also fails closed. |
| Packing/source semantics | Exact final counting, stable order, selected/ranked/source identities and generation-bound retrieval remain checked. |

These are deterministic engineering observations. They are **not** native-device latency, throughput, power, end-to-end dataset quality or agent-outcome evidence.

## Ledger B: fabric correctness and integration

The current implementation suite contains **556 tests**. Core-only ignition has zero native-provider, network and generation calls. Numeric auditing passes ten historical specification checks. Document/version-history checks and bounded evaluation smoke pass; evaluation smoke performs zero generation/judge calls and does not claim full-dataset acceptance.

The new model-fabric regressions additionally verify that observed-request evidence does not promote an alternate model in `auto-safe` or `auto-throughput`, explicit approximate activation waits for a session boundary, an active model pin survives a different settings key, fallback reports the reference path, failure quarantine increments once, private index/model artifacts do not mutate the authority profile, and worker cleanup removes the private workspace.

| Tested head | Workflow | Result |
| --- | --- | --- |
| `ca4d5f1` | [Correctness / push 34401841245](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34401841245) | Success: Ubuntu, Windows, macOS and all eight tokenizer rows |
| `ca4d5f1` | [Harness 34401841275](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34401841275) | Success |
| `ca4d5f1` | [Hermes 34401841296](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34401841296) | Success |

The closeout files that follow `ca4d5f1` are evidence/documentation-only. Their exact head must still pass the documentation/correctness gates before merge; the implementation-source integration results retain their own exact identity rather than being relabeled as later runs.

## Ledger C: real-hardware performance

**New-fabric real-hardware performance remains unaccepted.** No new machine benchmark, full-dataset campaign, model/vendor-SDK installation, positive ISA dispatch validation, ANE placement validation or generative/judge evaluation was performed for this closeout. SDK fixtures cannot establish native acceleration, quality improvement, resource savings or agent outcomes.

The earlier [post-fix bb16760 retest](2026-09-09-post-fix-retest-bb16760.md) remains historical evidence. It is not a benchmark of this new fabric. [Issue #13](https://github.com/xngg1021/thm-tiered-hot-memory/issues/13) remains the real-machine evidence ledger for the still-open dispatch/backend/low-precision questions. No repeated user benchmark is required for this merge.

## Review and release gates

The targeted review requested public tokenizer compatibility with actual cache hits, bounded admitted steady-state ranking verification, and strict separation of retrieval engineering, fabric correctness and real-hardware performance. Those requirements are now represented in code/tests and in the three ledgers above.

Earlier Codex requests repeatedly failed before code review with `Provided git ref ... does not exist`. Empty review threads do not establish approval when the service failed. This closeout therefore records the review gate as pending rather than waiving it.

Required final sequence:

1. the final documentation head passes correctness/documentation checks;
2. a **valid exact-head Codex review** completes with no actionable unresolved P1/P2 findings;
3. PR #20 is merged by normal merge with an expected-head guard;
4. post-merge `main` CI is green;
5. any post-merge closure record retains the exact merge/main identities.

Activity, hit, confirmation, validity, tier and memory-authority semantics remain unchanged. Stable/package promotion and new hardware/full-dataset acceptance remain outside this closeout.
