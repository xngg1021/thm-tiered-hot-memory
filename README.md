# THM — Tiered Hot Memory

Author: Junfu Shi (SJF, xngg1021). License: [MIT](LICENSE).

THM is a local-first four-tier memory toolkit for Hermes. The hardened `scripts/thm.py` 1.1.1 maintains a profile-bound index and proposes residency changes. The 1.2 package adds scoped lexical/local-semantic retrieval, budget-counted source packing, zero-weight mention observations, explicit decay-policy comparison and an optional Hermes provider adapter. Native memory files are not rewritten by these tools. Personal memories and deployed instances are not distributed.

## Current evidence

The [retrieval experiment](reports/2026-09-06-recall-results.md) and [machine-readable summary](reports/2026-09-06-recall-summary.json) report the completed GitHub Actions run at `433b1256`: 10 LoCoMo conversations, 1,986 questions, with 1,532 fully resolvable non-adversarial questions in the principal retrieval denominator. Under the same 600 `cl100k_base` token slice, question-level any-gold coverage was 56.85% for literal, 69.58% for improved sparse, 51.11% for the chosen dense encoder, and 70.04% for hybrid. These are evidence retrieval metrics, not answer accuracy or a competitor leaderboard. The user's earlier 21.6% experiment used an unavailable script and is not a matched baseline.

The benchmark invokes no generative model or judge. Dense encoding does use an explicitly downloaded local model. Sparse remains the default: this experiment does not establish that dense retrieval or hybrid's small gain is worth its extra cost for every workload.

The [integration review](docs/10-recall-integration-review.md) documents follow-up fixes, local regressions and evaluation-protocol corrections. The category names for 1/4 were reversed in the original runner, and protocol 2 isolates per-conversation IDF statistics. Historical results above remain protocol 1; a new full protocol 2 run is pending.

## Four tiers

T0 is the small native MEMORY.md / USER.md snapshot; T1 is on-demand thematic material; T2 is historical sessions and archives; T3 contains external source locations. A native memory-file write does not itself refresh an existing frozen system snapshot. T3's name does not guarantee immutable external content. See [architecture history](docs/02-架构设计.md).

The original activity formula is a heuristic, not a truth or relevance score. The 1.1.1 engine does not reward relocation and does not automatically pin new high-cost entries. Explicit migration preserves old protection. New alternative curves are available for comparison, not silently installed into a real profile.

## Run

Core commands require Python 3.10+ and the standard library. A reference tokenizer and neural encoder are optional dependencies.

```bash
python scripts/thm.py --help
python -m thm --help
python -m thm import-files ./example-notes --db ./test-state/recall.sqlite3 --scope demo
python -m thm search --db ./test-state/recall.sqlite3 --scope demo 'Which database port?' --budget 600
python -m thm curves
python -m unittest discover -s tests -v
python scripts/thm_numeric_audit.py
python scripts/check_docs.py
```

The default new context-budget counter is explicitly `utf8_bytes`, not model tokens. Select `--counter cl100k_base` after installing the optional tokenizer for the published reference protocol. Provider users must allocate a suitable evidence slice from the host's real request budget.

The index CLI writes only its own state under `<resolved-memory-directory>/.thm`. Retrieval and scan write separate derived databases. A foreign database is refused before creating derived tables, so accidentally targeting a native `state.db` does not install a THM schema into it. These are cooperating-process safety checks, not protection against a hostile filesystem owner.

Guides: [index commands and migration](docs/06-engine-guide.md), [new retrieval/scan/policy/provider interface](docs/09-retrieval-and-measurement.md), [reproducible benchmark](research/recall/README.md), [all project documents](docs/README.md).

## Evidence boundaries

The implementation commit's three-platform correctness run discovered 134 tests: 133 passed and one optional-NumPy test was skipped on each platform. The separate benchmark actually loaded and executed the neural encoder. Follow-up source-database guards add three more tests; read their exact-commit CI rather than transferring the earlier count. Original numeric tests preserve old counterexamples and do not certify new behavior.

Not yet established: real-user end-to-end answer accuracy, native Hermes installation lifecycle, user-specific optimal decay, prompt-cache savings or user-perceived response-time improvement. No automatic tier movement or multi-file memory migration is performed. Source imports are explicit snapshots and must be refreshed. The scan measures mentions, not actual usefulness. A clean benchmark run does not certify those omitted capabilities.

The substantial benchmark is opt-in through workflow dispatch or a commit message containing `[benchmark]`; normal three-platform correctness CI remains automatic. No model downloads happen during ordinary index maintenance.

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills). Its presence is not validation of THM.
