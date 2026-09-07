# Reviewed zero-LLM frontier production evidence

This supersedes the current-source claim of the [pre-review result report](2026-09-07-zero-llm-frontier-results.md). Earlier numeric results and source fingerprints are preserved as historical run provenance; metadata wrappers identify the superseding current evidence.

## Review repairs

The first final review identified one P1 (unbounded repeated identifier regex work) and two P2 findings (compound-prefix collisions and stale production source fingerprints). The policy now admits at most 16 identifiers, limits identifier/name/body lengths, precompiles at most two patterns, and fails soft to base order for over-complex identifier queries. Longest known full names take precedence over shorter names. The follow-up P2 repair captures complete multi-component versions and applies the same exact boundaries during query extraction, rejecting truncated release, build, ticket, path, and URL prefixes. Unquoted URL extraction also removes terminal prose punctuation and unmatched closing wrappers in linear work, preserving balanced path parentheses and explicit backtick literals. Exact boundaries reject Ann/Ann-Marie and path/path.old prefix collisions while allowing terminal sentence punctuation.

The 1200-identifier / 1000-candidate reproduction returns unchanged order in 0.024 ms locally. This measures only the guarded projection, not complete search latency. Regression tests assert the work/compile bounds rather than imposing a flaky wall-time threshold. The complete local suite has 260 passing tests.

## Fresh canonical run

Unicode URL prose punctuation and common paired wrappers were subsequently added with regression coverage; explicit backtick literals and balanced Unicode path wrappers are preserved. Both the fresh manifest and compressed trace were regenerated after the fixes; every recorded source SHA-256 was checked against the actual source files. No tuning was performed.

| Policy | Any-gold | All-gold | MRR | nDCG | p50 ms | p95 ms | p99 ms | Mean tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 69.3864% | 56.5274% | 0.497354 | 0.507241 | 23.04 | 31.86 | 39.30 | 583.93 |
| entity | 72.5196% | 59.4648% | 0.537435 | 0.543583 | 23.45 | 32.86 | 43.63 | 584.12 |

The dataset, 1532 main-question denominator, 1301-question holdout, candidate coverage (92.4282%), and fixed 600 cl100k_base budget are unchanged. Holdout improvement remains +2.7671 pp (55 wins / 19 losses), cluster-bootstrap interval [+1.7946, +3.8247] pp. All preregistered metric gates still pass. No new generative calls, judge calls, embeddings, native-memory writes, or tier changes.

The [full-candidate rank equivalence proof](2026-09-07-zero-llm-frontier-rank-equivalence.json) compares every question against the pre-holdout frozen projection. Identical complete candidate ordering implies the unchanged whole-turn packer produces the same evidence at every positive budget; the original six-budget curve therefore remains applicable without replacing its measured timing values. No timing result from this instrumented equivalence check is used as a benchmark.

## Latency investigation after the URL repair

The first URL-repair run failed the unchanged 1.25 holdout p95 ratio gate. Before inspecting further results, two sequential repeats were scheduled, without source changes or parameter tuning. Both repeats and the failed run are preserved; the second scheduled repeat is retained as a separate historical investigation artifact. Recall, selected candidate order, and token results remain identical. None of the 1986 dataset questions contains an HTTP(S) URL, so the newly added URL branch was not exercised by these benchmark queries. Opposite timing movements across repeats indicate substantial timing variability; its cause is not established and no speedup or universal latency guarantee is claimed. Exact-head CI must independently pass the original gate before merge.

| Run | Held-out baseline p95 ms | Held-out entity p95 ms | Ratio | All gates pass |
| --- | ---: | ---: | ---: | --- |
| Initial | 36.22 | 63.06 | 1.741 | False |
| Repeat 1 | 69.33 | 45.53 | 0.657 | True |
| Repeat 2 (pre-Unicode fix) | 45.08 | 44.98 | 0.998 | True |

[Initial failed manifest](2026-09-07-zero-llm-frontier-latency-investigation-initial.json) and [repeat 1 manifest](2026-09-07-zero-llm-frontier-latency-investigation-repeat1.json) each have an adjacent `.json.gz` with their full raw records. The [repeat 2 manifest](2026-09-07-zero-llm-frontier-latency-investigation-repeat2.json) also has an adjacent raw `.json.gz`. All three investigation runs precede the Unicode punctuation fix and retain their original source fingerprints; the current reviewed production files are regenerated after that fix. These measurements support retaining an opt-in experiment, not declaring a stable 1.5 latency milestone.

Current files: [reviewed production manifest](2026-09-07-zero-llm-frontier-reviewed-production-summary.json) and `2026-09-07-zero-llm-frontier-reviewed-production-traces.json.gz`. The older `production-summary.json` and `production-traces.json.gz` are explicitly pre-review runs, not current-source fingerprints. CI and re-review on the new commit remain required before merge; no 1.5 stable registration is declared.
