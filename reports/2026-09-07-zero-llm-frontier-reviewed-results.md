# Reviewed zero-LLM frontier production evidence

This supersedes the current-source claim of the [pre-review result report](2026-09-07-zero-llm-frontier-results.md). Earlier numeric results and source fingerprints are preserved as historical run provenance; metadata wrappers identify the superseding current evidence.

## Review repairs

The first final review identified one P1 (unbounded repeated identifier regex work) and two P2 findings (compound-prefix collisions and stale production source fingerprints). The policy now admits at most 16 identifiers, limits identifier/name/body lengths, precompiles at most two patterns, and fails soft to base order for over-complex identifier queries. Longest known full names take precedence over shorter names. The follow-up P2 repair captures complete multi-component versions and applies the same exact boundaries during query extraction, rejecting truncated release, build, ticket, path, and URL prefixes. Exact boundaries reject Ann/Ann-Marie and path/path.old prefix collisions while allowing terminal sentence punctuation.

The 1200-identifier / 1000-candidate reproduction returns unchanged order in 0.024 ms locally. This measures only the guarded projection, not complete search latency. Regression tests assert the work/compile bounds rather than imposing a flaky wall-time threshold. The complete local suite has 258 passing tests.

## Fresh canonical run

Both the fresh manifest and compressed trace were regenerated after the fixes; every recorded source SHA-256 was checked against the actual source files. No tuning was performed.

| Policy | Any-gold | All-gold | MRR | nDCG | p50 ms | p95 ms | p99 ms | Mean tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 69.3864% | 56.5274% | 0.497354 | 0.507241 | 36.98 | 82.62 | 104.20 | 583.93 |
| entity | 72.5196% | 59.4648% | 0.537435 | 0.543583 | 37.09 | 76.42 | 100.35 | 584.12 |

The dataset, 1532 main-question denominator, 1301-question holdout, candidate coverage (92.4282%), and fixed 600 cl100k_base budget are unchanged. Holdout improvement remains +2.7671 pp (55 wins / 19 losses), cluster-bootstrap interval [+1.7946, +3.8247] pp. All preregistered metric gates still pass. No new generative calls, judge calls, embeddings, native-memory writes, or tier changes.

The [full-candidate rank equivalence proof](2026-09-07-zero-llm-frontier-rank-equivalence.json) compares every question against the pre-holdout frozen projection. Identical complete candidate ordering implies the unchanged whole-turn packer produces the same evidence at every positive budget; the original six-budget curve therefore remains applicable without replacing its measured timing values. No timing result from this instrumented equivalence check is used as a benchmark.

Current files: [reviewed production manifest](2026-09-07-zero-llm-frontier-reviewed-production-summary.json) and `2026-09-07-zero-llm-frontier-reviewed-production-traces.json.gz`. The older `production-summary.json` and `production-traces.json.gz` are explicitly pre-review runs, not current-source fingerprints. CI and re-review on the new commit remain required before merge; no 1.5 stable registration is declared.
