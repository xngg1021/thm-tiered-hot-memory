# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

THM is a local-first, four-tier memory toolkit for Hermes Agent. It focuses on a narrow problem: deciding what deserves permanent context, what should be loaded on demand, how historical material is recalled under a fixed budget, and how those decisions can be measured without fabricating “usage” signals.

## Four tiers

- **T0 — hot:** native `MEMORY.md` / `USER.md` content injected into the session snapshot.
- **T1 — warm:** thematic Markdown material loaded on demand.
- **T2 — cold:** historical sessions and archives searched under an explicit evidence budget.
- **T3 — external:** source locations and references that can be revisited when needed.

THM separates activity, validity, task relevance and explicit pinning. A mention is not a hit; a retrieval is not proof of usefulness; a write is not a use event.

## What is implemented

The hardened 1.1.1 index CLI maintains profile-bound memory metadata, exact event identities, migration previews, pin/unpin semantics and failure-safe writes. The 1.2 package adds scoped FTS5 retrieval, optional local sentence embeddings, reciprocal-rank fusion, budget-counted context packing, zero-weight mention observations, multiple decay-policy comparisons, a read-only Hermes provider adapter and reproducible evaluation scripts.

Native memory files and Hermes `state.db` are never rewritten by retrieval or scan. Derived SQLite databases reject unrelated/native database targets before THM tables are created.

## Measured evidence

A completed **Protocol 2** LoCoMo run used all 10 conversations and 1,986 questions. The principal denominator contains 1,532 fully resolved, non-adversarial questions. At a fixed 600 `cl100k_base` evidence-token slice, any-gold coverage was **56.79% literal**, **69.39% sparse**, **51.11% MiniLM dense**, and **71.34% hybrid**. All-gold coverage was **46.61% / 56.53% / 40.01% / 57.64%** respectively. These are evidence-retrieval metrics, not answer accuracy and not a competitor leaderboard.

Protocol 2 corrects the LoCoMo category mapping, uses one FTS database per conversation so BM25/IDF statistics cannot leak across conversations, and reports MRR, nDCG and p99. At 600 tokens, sparse p95 retrieval+packing latency was **34.55 ms** and hybrid was **57.88 ms**. Hybrid gained **1.96 percentage points** of any-gold coverage over sparse in this workload; this is a measured tradeoff, not a universal default recommendation. Full evidence: [Protocol 2 report](reports/2026-09-06-recall-protocol2.md) · [machine-readable summary](reports/2026-09-06-recall-protocol2-summary.json).

The sparse budget sweep reached **60.57% / 69.39% / 76.17%** any-gold coverage at 300 / 600 / 1200 evidence tokens, with p95 retrieval+packing latency **20.39 / 34.55 / 61.78 ms**. Heavy LoCoMo/model downloads remain opt-in and never occur during ordinary index maintenance.

## Hermes integration

The package exposes `thm` through Hermes' `hermes_agent.memory_providers` entry-point group. A pinned-upstream E2E run against `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` verified real Hermes plugin discovery, `MemoryProvider` admission, `MemoryManager` admission, current-query prefetch, memory-context fencing, recall status, session switching, and that `on_memory_write` is **not** a hit and does not modify the derived recall database. The run used synthetic evidence and zero model calls, so it is a provider-lifecycle E2E rather than an answer-generation benchmark. See [Hermes E2E report](reports/2026-09-06-hermes-e2e.md).

## Install and run

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Optional tokenizer / semantic dependencies:

```bash
python -m pip install -e '.[tokenizer,semantic]'
```

## Decay calibration

Synthetic decay sweeps remain diagnostic only. For a real-user calibration, `research/recall/decay_from_index.py` exports a privacy-minimized chronology containing entry IDs, unit costs and explicit `hit` dates while excluding memory text, summaries, keys and confirmation evidence. The private trace can then be replayed through `decay_replay.py`. Without an actual chronological hit trace, THM does not claim a user-specific optimal half-life or curve.

## Evidence boundaries

THM does **not** currently claim real-user end-to-end answer accuracy, a universally optimal decay curve, automatic tier movement, automatic deletion propagation, or a prompt-cache / perceived-latency improvement. `scan` records weak `mention_observed` evidence with zero activity weight. Retrieval coverage, provider lifecycle, user-specific decay and generated-answer quality remain separate evidence layers.

Normal correctness CI runs on Linux, macOS and Windows. Documentation: [project index](docs/README.md) · [engine guide](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [integration review](docs/10-recall-integration-review.md) · [benchmark protocol](research/recall/README.md).

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).
