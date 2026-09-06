# 2026-09-06 THM 1.2 implementation and experiment results

## Exact execution identity

Implementation/benchmark commit: `433b1256bbaca8680f3c41d67a1e23e97b36bd7c`.

- Correctness workflow: https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34030697736
- Retrieval and synthetic-decay workflow: https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34030697732
- Artifact ID: `9988651011`, `thm-retrieval-metrics`, retention 30 days.
- Archive SHA-256: `08e90068b1120941c72092d51c089c3740d14c034a8b500f0580b4d380cbc783`.
- Permanent compact metrics and raw-file digests: [JSON summary](2026-09-06-recall-summary.json).

The downloaded archive digest was independently checked. It contains lexical.json, semantic.json, decay.json and dependencies.txt. Results were read from these files, not inferred from a green workflow. The source-database guard follow-up does not change ranking/packing logic; its own correctness result must still be checked separately. It was not retroactively substituted into this benchmark's source fingerprint.

## What was implemented

Actual callable code now includes FTS5 literal and improved sparse search, optional local sentence vectors, reciprocal-rank fusion, scope filtering, whole-source budget packing, explicit local source import, read-only schema-checked Hermes import, a zero-weight scan sidecar, alternative residency curves, chronological policy replay, a Hermes provider contract adapter and optional local generation measurement. The original index engine remains the single index-maintenance implementation.

The provider was tested using a contract double, not a live installed Hermes lifecycle. It prefetches on the current query and never mirrors a write as a usage hit. Sources and native memory files were not modified. No private project code or private histories were inputs.

## Main recall result

Dataset: pinned official LoCoMo, 10 conversations, 5,882 source turns and 1,986 questions. Categories 1-4 contain 1,540 questions; four have no gold and four have unresolved/malformed references. The principal denominator is therefore 1,532. Category 5's 446 adversarial questions are shown separately in the raw artifact and are not treated as normal answerable questions. Headers, speakers, dates and separators count against `cl100k_base`.

| Route / budget | Any-gold question rate | All-gold question rate | Mean used tokens | Retrieval+packing mean / p95 ms |
| --- | ---: | ---: | ---: | ---: |
| Literal / 300 | 48.83% | 40.34% | 284.61 | 14.25 / 15.47 |
| Literal / 600 | 56.85% | 47.06% | 583.84 | 23.52 / 24.67 |
| Literal / 1200 | 64.10% | 52.61% | 1183.04 | 40.76 / 42.08 |
| Improved sparse / 300 | 60.70% | 49.15% | 284.51 | 17.85 / 23.85 |
| Improved sparse / 600 | 69.58% | 56.33% | 584.78 | 29.89 / 40.27 |
| Improved sparse / 1200 | 76.50% | 62.47% | 1182.81 | 52.68 / 71.26 |
| MiniLM dense / 600 | 51.11% | 40.01% | 584.31 | 35.00 / 35.67 |
| Hybrid / 600 | 70.04% | 56.46% | 585.74 | 47.89 / 61.63 |

At 600 tokens, sparse adds 12.73 percentage points over this run's literal baseline. On the eight disclosed held-out conversations the any-gold rates are 57.19%, 69.64%, 50.88% and 69.95% respectively. No parameter was chosen from QA outcomes by the runner.

Hybrid adds only seven net successes over sparse: 90 hybrid-only successes versus 83 sparse-only successes, with 983 both successful and 376 both unsuccessful. No statistical significance is claimed. Hybrid's pre-budget candidate any-gold coverage is 97.06%, versus 91.58% sparse; the remaining gap is largely after candidate generation and must not be called final recall. The chosen dense encoder alone is worse on this protocol.

## Speed and curve interpretation

The latency numbers include query processing, candidate retrieval, full result materialization and context packing. They exclude model loading, source indexing, corpus encoding and answer generation. Sparse index creation across all conversations took about 0.75 seconds; corpus encoding took about 38.69 seconds. Hybrid ran after dense and often reused query vectors, so dense/hybrid query-encoding latency is not a cache-matched comparison.

No end-to-end speedup over the user's 0.38 ms SQL probe is claimed. The local SQL result and this complete retrieval pipeline have different timed boundaries. Provider prefetch may avoid an extra agent tool-decision turn, but this has not been measured in a real agent session.

Synthetic replay used 1,440 chronological uses and selected among 22 configurations on the first half. `bounded_power@3d` scored 56.39% residency hits on the second half; the legacy curve scored 55.42%, LRU 50.14%, LFU 51.81%. This is a synthetic trace, not empirical knowledge aging or answer accuracy. No user's decay parameters were changed. A 30-day bounded-power default did not win this workload.

## Corrections to the earlier user-reported inference

The earlier local 425/1966=21.6% result remains user-reported: its script and results were absent from the remote snapshot. It cannot be used as a matched before/after baseline here. Raw question words are not an oracle query, and one FTS configuration does not establish a structural lexical ceiling. The new lexical-only result supplies a counterexample under its disclosed protocol.

A 600-token evidence hit rate and a full-context model answer score measure different things. Neither 72.9% nor a weighted composite of tier assumptions establishes THM answer accuracy here. Character-count/4 is not a tokenizer-specific measurement. The observed local near-zero I/O time cannot identify the entire response-latency decomposition without timing the other phases.

## Tests, limitations and next measurements

The initial implementation has 47 new regression tests, bringing the complete suite to 134. GitHub Linux, Windows and macOS runs each passed 133 with one optional NumPy test skipped; the neural benchmark ran separately with actual dependencies. The follow-up adds three foreign-database preservation tests. A separate local extension-only run executed all 50 extension tests with NumPy installed; this is not a substitute for running the entire repository suite on the follow-up commit.

Limits remain: multi-scope FTS statistics share a database, the simple CJK tokenizer is not a multilingual embedding evaluation, import refresh is explicit, arbitrary paraphrase remains imperfect, whole oversized source turns can be omitted, reliable abstention is not demonstrated, and native-host/real-user answer quality is unmeasured. Future reranking or chunk changes require fresh evidence; none are counted as already implemented.

The fixed 1.1.1 index CLI was left unchanged. The follow-up guards foreign SQLite files, wraps the source read in one snapshot, packages the existing scripts rather than duplicating their engine, and makes heavyweight benchmark downloads opt-in. These changes do not claim to finish all broader validation-contract requirements.
