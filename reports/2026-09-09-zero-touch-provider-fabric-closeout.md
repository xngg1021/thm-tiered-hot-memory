# Zero-touch heterogeneous provider fabric — engineering closeout

This Unreleased implementation is published in [PR #20](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20). Engineering validation is complete at the implementation head below. Release closure still requires a valid exact-head Codex review, an expected-head normal merge and successful main CI. A review service failure is not review approval.

## Identity and scope

| Identity | Value |
| --- | --- |
| Base main | `2d5c2adcf994edd8b7bb3c0546983ba9531af392` |
| Implementation head | `64fdcc42a673d7d07513d58bca00facbe69afdf7` |
| Implementation tree | `1119c97ad0c16c73835d9d0346da50fb79121384` |
| Historical post-fix hardware head | `bb1676007b0f86dec0267585c56136c82157ae54` |
| Unchanged stable archive | `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c` |
| Package version | `1.4.0`; no promotion |

The implementation adds lazy provider contracts and catalog discovery; public hardware/driver observations; checksummed profiles and immutable compiled artifacts; safe bootstrap; passive telemetry and bounded online queues; material-gain/Pareto admission; session pinning; preemptible isolated exploration; resident indexes/transfers; local-model preparation in retained workers with private index replicas; and harness/MCP/Hermes lifecycle integration. Physical plans bind the actual placement and regenerate on fallback.

The catalog has 71 entries: 51 L4, one L2, 12 L1 and seven L0. **There are no L5 hardware-accepted entries.** L4 is implemented lifecycle/fixture evidence, not a claim that every vendor SDK or accelerator ran here. The [provider matrix](../docs/provider-matrix.md) and [source registry](../docs/provider-sources.json) retain per-provider public API, platform, license and executable-boundary provenance. The architecture is documented in [runtime](../docs/20-zero-touch-runtime.md), [fabric](../docs/21-provider-fabric.md), [optimizer](../docs/22-runtime-optimizer.md) and [vector providers](../docs/23-vector-index-providers.md).

## Ledger A: retrieval engineering

| Observation | Evidence and boundary |
| --- | --- |
| Speaker SQL reuse | `test_speaker_cache_and_generation_invalidation`: two same-generation searches issue one `SELECT DISTINCT speaker`; replacing the scope causes the next search to issue the second query. |
| Neighbor retrieval | Batched CTE lookup preserves the original per-row ordering and content in `test_neighbor_prefetch_has_exact_original_order`. This is parity evidence; no wall-time speedup is claimed. |
| Row cache | Copy-on-read prevents returned row mutations from changing cached source rows. Generation identity invalidates reuse. |
| Tokenizer calls/cache hits | `test_tokenizer_compat.py` checks every prefix of fixed ASCII, whitespace, Chinese and emoji samples against the public encoder. The second identical prefix performs zero additional encoder calls. It also checks non-additive BPE boundaries, 64-entry eviction and encoder replacement. |
| Supported tokenizer releases | Actual CI jobs pass for tiktoken 0.7.0, 0.8.0, 0.9.0, 0.10.0, 0.11.0, 0.12.0, 0.13.0 and 0.14.0 with in-memory vocabularies; no vocabulary/model download. |
| Admitted online ranking | A two-query online cohort at k=5 scores `[6, 6]` host rows on a 500-row source matrix. The test exercises RuntimeService admission and its actual batcher. It does not rescan all 500 rows for either separated ranking. |
| Ambiguous cutoff | A tied k=1 fixture scores `[2, 500]`: bounded selected/cutoff check followed by the stable full reference fallback. Unknown accumulation uses the full reference path. |
| Packing/source semantics | Exact final counting, stable order, selected/ranked/source identities and generation-bound retrieval remain independently checked. Provider guard cost is included in shadow timing before performance admission. |

These are SQL/call-count/cache/semantic measurements on deterministic fixtures. They are not native hardware latency, throughput, power or memory-quality results. The fragile private regex/BPE piece path was removed; the retained optimization uses exact whole-prefix public-call caching.

## Ledger B: fabric correctness and integration

The local full suite passes **553 tests**. Core-only ignition reports zero native provider, network and generation calls. Numeric auditing passes its ten historical specification checks; document and version-history checks pass; bounded offline evaluation smoke passes with zero generation/judge calls and `full_dataset_acceptance=false`.

Coverage includes safe first requests, missing optional dependencies, store schema/corruption/TTL/driver freshness, all critical profile-key components, real placement identity, material/noise/resource gates, Pareto unknowns, queue growth/deadlines/recycling, session non-promotion, generation/fallback planning, resident ownership and in-flight eviction, allocation cleanup, child resource limits/preemption, quarantine, private model profiles and retained-worker lifecycle. Public SDK fixtures check callable contracts and failure receipts. Real macOS CI validates the bounded worker path after switching its accounting to public `libproc`; MCP end-to-end checks validate the added runtime status schema.

| Tested head | Workflow | Result |
| --- | --- | --- |
| `64fdcc4` | [Correctness / PR 34378979939](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34378979939) | Success: Linux, Windows, macOS and eight tokenizer versions |
| `64fdcc4` | [Correctness / push 34378975911](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34378975911) | Success |
| `7c5a77a` | [Harness 34378460874](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34378460874) | Success |
| `7c5a77a` | [Hermes 34378460854](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34378460854) | Success |

The last implementation-source change is `7c5a77a`. Its successor `64fdcc4` changes only provider source documentation and the eighth tokenizer CI row; integration path filters do not schedule new harness/Hermes runs for those three files. The earlier integration runs retain their own exact identity, rather than being relabeled as runs at a later SHA. PR/main checks after this report are tracked in the PR's checks and merge records.

## Ledger C: real-hardware performance

**New-fabric real-hardware performance remains unaccepted.** No new machine benchmark, full dataset campaign, model/vendor SDK installation, ISA dispatch validation, ANE placement validation or generative/judge evaluation was performed for this closeout. Energy counters are device observations in stated units; an unknown resource is not zero and board energy is not query-attributed energy. SDK fixtures cannot establish native acceleration, quality, resource savings or agent outcomes.

The earlier [post-fix bb16760 retest](2026-09-09-post-fix-retest-bb16760.md) and its seven raw receipts remain historical evidence. That run admitted an auto-safe torch FP32 CPU candidate, exercised reference fallback and recorded CPU batches 1/4/8/32. It is not a benchmark of this new fabric. [Issue #13](https://github.com/xngg1021/thm-tiered-hot-memory/issues/13) now marks the completed retest and batch sweep as completed; ISA-positive dispatch, successful ORT/OpenVINO paths and low-precision quality evidence remain separate open items. No repeated user benchmark is requested.

## Review and remaining release gates

The [targeted review](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20#pullrequestreview-5156589002) requested public tokenizer compatibility with actual cache hits, bounded admitted steady-state ranking verification, and these three separate ledgers. The forward implementation commits address all three.

The first two exact-head Codex requests failed before code review with `Provided git ref ... does not exist`: [7c5a77a service failure](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20#issuecomment-5605440475) and [64fdcc4 service failure](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20#issuecomment-5605572566). Git remote listing and a fetched commit object independently confirm `64fdcc4` exists. The ready-for-review transition was applied after exact-head correctness passed; its review attempt also failed at 16:55:46 UTC in the [service summary](https://github.com/xngg1021/thm-tiered-hot-memory/pull/20#issuecomment-5605434182). An empty inline-thread list does not establish a clean review when the service failed.

Until a valid exact-head review completes, the expected-head normal merge and post-merge main verification remain pending. No gate is waived and no merge/main SHA is invented. The [machine-readable record](2026-09-09-zero-touch-provider-fabric-closeout.json) distinguishes completed engineering evidence from release closure. Subsequent gate outcomes must retain their exact head and workflow identities.

Activity, hit, confirmation, validity, tier and memory-authority semantics remain unchanged. Stable/package promotion and new hardware/full-dataset acceptance are outside this implementation closeout.
