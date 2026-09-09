# THM retrieval, observation, decay and measurement — 1.2 foundation, current in 1.4

## Unified dataplane metrics

[Evaluation Fabric](18-evaluation-fabric.md) projects LoCoMo Protocol 2 and LongMemEval-S into shared any/all-gold, macro/micro recall, parent coverage, budget and latency metrics. Evidence units and protocol identities remain explicit; native results remain available. Unresolved/no-gold/diagnostic tasks do not earn main recall credit. New default fixtures use utf8_bytes, not cl100k_base; their values are not comparable with the historical 600-token benchmark. No answer/rubric enters the source index.

<!-- current-v1.4-status:start -->
> **Current release status — THM 1.4.0 accepted/stable implementation milestone.** Stable code/content milestone: `e6e4dda5835e3cb345207457d5491131c6959b2c`; immutable recovery pointer: `archive/v1.4.0-stable`. This document retains its original research/design/1.2/1.3 scope as historical foundation rather than rewriting old evidence as a new result. Current implementation state is tracked in [07-implementation-status.md](07-implementation-status.md), the 1.4 shadow control plane in [14-residency-control-plane.md](14-residency-control-plane.md), the opt-in Hermes T1 surface in [15-hermes-warm-directory.md](15-hermes-warm-directory.md), and the exact acceptance record in [the 1.4 closeout](../reports/2026-09-07-v1.4-closeout.md).
<!-- current-v1.4-status:end -->

This is a THM-only extension. The tested 1.1.1 index-maintenance CLI remains in `scripts/thm.py`; the `thm` package adds retrieval and measurement without creating a second index-maintenance engine.

## Commands

```bash
python -m thm --help
python -m thm import-files ./example-notes --db ./test-state/recall.sqlite3 --scope demo
python -m thm import-hermes ./test-profile/state.db --db ./test-state/recall.sqlite3 --scope demo
python -m thm search --db ./test-state/recall.sqlite3 --scope demo 'Which database port?' --budget 600
python -m thm curves
python -m thm index --mem-dir ./test-profile/memories audit
```

File and Hermes imports refresh their own source kind without removing the other kind. All imports write a separate derived SQLite index, never native memory files or the source `state.db`. The Hermes source reader is read-only, schema-checked and profile-scoped; partial imports are refused.

## Recall modes and budget

`literal` is an unstemmed lexical baseline. `sparse` uses FTS5 Porter stemming, stopword filtering for candidate generation, speaker-aware terms, light adjacent-turn context and reciprocal-rank fusion. Chinese text has a simple character-bigram channel. `dense` and `hybrid` require an explicitly selected on-disk sentence-transformer; the library itself does not download a model.

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m thm embed --db ./test-state/recall.sqlite3 --scope demo --model-path ./models/encoder --model-id local-encoder-revision
python -m thm search --db ./test-state/recall.sqlite3 --scope demo 'database port' --mode hybrid --counter cl100k_base --budget 600 --model-path ./models/encoder --model-id local-encoder-revision
```

The default `utf8_bytes` counter measures bytes, not model tokens. `cl100k_base` is an explicit reference-tokenizer option. Speaker/date/header/separator text counts against the same evidence budget. Whole source turns are packed; an oversized candidate is skipped without terminating the remaining search. A candidate ID is not evidence unless its text is actually packed.

Timings separate lexical retrieval, query encoding, retrieval and packing. They exclude source ingestion, model loading and answer generation and therefore are not user-perceived latency measurements.

## Scan without feedback fabrication

`scan` emits `mention_observed` records with weight zero. It never calls `hit` or `confirm`, extends validity or writes `index.json`.

```bash
python -m thm scan --state-db ./test-profile/state.db --scope demo --anchors ./anchors.json --now 2026-09-06T12:00:00+00:00 --save-observations ./test-state/observations.sqlite3
```

Observations retain message/session identity, time, source-text fingerprint and rule version. A match is not proof of use; no match is not proof of uselessness. Copied branches, code/quotes and recognizable review echoes are excluded conservatively. Observation storage may itself contain sensitive metadata and should remain local unless deliberately published.

## Decay and residency

Available alternatives include the historical power curve, half-life-calibrated power and exponential curves, a two-timescale mixture, bounded-window/day-capped power, LRU and LFU. Mention, display, retrieval and relocation carry zero activity weight. Validity and explicit pinning precede activity score. No selected curve is auto-installed.

Synthetic comparison remains available:

```bash
python research/recall/decay_replay.py --sweep --output ./test-state/decay-synthetic.json
```

For a real-user calibration, export only the explicit hit chronology from a local THM v2 index and keep the generated trace outside the public repository:

```bash
python research/recall/decay_from_index.py \
  --index /path/to/memories/.thm/index.json \
  --mem-dir /path/to/memories \
  --counter utf8_bytes \
  --output /private/path/thm-decay-trace.json

python research/recall/decay_replay.py \
  --input /private/path/thm-decay-trace.json \
  --sweep \
  --output /private/path/thm-decay-calibration.json
```

The exporter writes entry IDs, unit costs and explicit hit dates only; it excludes memory text, summaries, keys and confirmation evidence. `mention_observed`, display, retrieval, confirm and movement events are not converted into uses. Without an actual private chronology, THM makes no user-specific optimum claim.

## Hermes integration

Installing the package registers THM through Hermes' `hermes_agent.memory_providers` entry-point group:

```bash
python -m pip install -e .
export THM_RECALL_SCOPE=demo
```

The selected scope must already exist in `<hermes_home>/memories/.thm/recall.sqlite3`. THM occupies Hermes' single external-provider slot; it does not auto-export conversations or rewrite native memory files.

A pinned-upstream integration run has exercised the **real** Hermes discovery and provider lifecycle rather than only a contract double. Run `34042345020` used THM commit `2d55f944ec066bdb26444db633d2a686fd22ec2d` and Hermes `77915e344cb0cd8e20661d4a7b393f987a2eef32`. It verified pip entry-point discovery, `MemoryProvider` type admission, `MemoryManager` admission, current-query prefetch, Hermes memory-context fencing, recall status, session switching, and that `on_memory_write` clears recall status without becoming a hit or changing the derived recall database. See [the permanent report](../reports/2026-09-06-hermes-e2e.md).

That is a provider-lifecycle E2E with synthetic evidence and zero model calls; it is not an answer-generation E2E or a real-user quality measurement.

## Benchmark protocol

The historical protocol-1 numbers remain immutable evidence. Protocol 2 corrects LoCoMo category names, creates one FTS database per conversation so IDF statistics cannot leak across conversations, and adds MRR, nDCG and p99. The heavy workflow asserts `protocol == 2`, the pinned dataset digest and `idf_scope == one_database_per_conversation` before accepting an artifact.

Protocol 2 completed successfully in workflow run `34042410130` at THM commit `702ad5c7973f7376e575734948847204cf5a4b0c`. On the principal 1,532 fully resolved non-adversarial questions at a 600 `cl100k_base` evidence-token slice, any-gold coverage was **56.79% literal**, **69.39% sparse**, **51.11% dense**, and **71.34% hybrid**. Sparse p95 retrieval+packing latency was **34.55 ms**; hybrid was **57.88 ms**. See the [full Protocol 2 report](../reports/2026-09-06-recall-protocol2.md) and [machine-readable summary](../reports/2026-09-06-recall-protocol2-summary.json). These remain retrieval metrics, not generated-answer accuracy.

## Generation evaluation

`thm.answer_eval.local_answer` can optionally call an explicit loopback-IP chat-completions endpoint. Remote hosts, proxies and redirects are refused. `exact_f1` provides transparent lexical metrics; it is not a semantic judge.

## Public technical sources

- SQLite FTS5 query syntax, Porter tokenizer and BM25: https://www.sqlite.org/fts5.html
- SQLite read-only URI semantics: https://sqlite.org/uri.html
- Cormack, Clarke and Buettcher, SIGIR 2009, reciprocal rank fusion: https://doi.org/10.1145/1571941.1572114
- Sentence Transformers local loading options: https://sbert.net/docs/package_reference/sentence_transformer/model.html
- Hermes integration is pinned to `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` for the recorded E2E run.

No private Family HF code, private histories or cross-project runtime internals are inputs to this extension.

## Unreleased retrieval successor

The opt-in Python entity projection and its Protocol 2 evidence are documented in [the zero-LLM frontier](16-zero-llm-retrieval-frontier.md). It does not enable a harness option, change residency/activity/validity semantics, or move the 1.4 stable pointer.


## Post-local corrective evidence

See the [current corrective contract and short retest](19-post-local-corrective.md). Z6 CPU/CUDA/auto-throughput and local NTFS/NVMe are machine-observed at b1f8119. Aggregate parity, strict parity, calibrated policy and post-fix acceptance remain separate claims. Auto-safe now allows a measured reference fallback; lack of acceleration does not itself fail correctness. No version/stable promotion or full-dataset acceptance is implied.
