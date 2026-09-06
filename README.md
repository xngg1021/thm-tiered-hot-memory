# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

THM is a local-first, four-tier memory toolkit for Hermes Agent. It focuses on a narrow problem: deciding what deserves permanent context, what should be loaded on demand, how historical material is recalled under a fixed budget, and how those decisions can be measured without fabricating “usage” signals.

## Four tiers

- **T0 — hot:** native `MEMORY.md` / `USER.md` content that is injected into the session snapshot.
- **T1 — warm:** thematic Markdown material loaded on demand.
- **T2 — cold:** historical sessions and archives searched under an explicit evidence budget.
- **T3 — external:** source locations and references that can be revisited when needed.

THM separates activity, validity, task relevance and explicit pinning. A mention is not a hit; a retrieval is not proof of usefulness; a write is not a use event.

## What is implemented

The hardened 1.1.1 index CLI maintains profile-bound memory metadata, exact event identities, migration previews, pin/unpin semantics and failure-safe writes. The 1.2 package adds scoped FTS5 retrieval, optional local sentence embeddings, reciprocal-rank fusion, budget-counted context packing, zero-weight mention observations, multiple decay-policy comparisons, a read-only Hermes provider adapter and reproducible evaluation scripts.

Native memory files and Hermes `state.db` are never rewritten by the retrieval or scan paths. Derived SQLite databases reject unrelated/native database targets before creating THM tables.

## Measured evidence

The historical protocol-1 LoCoMo run used 10 conversations and 1,986 questions. For the principal 1,532 fully resolvable non-adversarial questions at a 600-token `cl100k_base` evidence budget, any-gold coverage was **56.85% literal**, **69.58% sparse**, **51.11% MiniLM dense**, and **70.04% hybrid**. These are evidence-retrieval metrics, not answer accuracy and not a competitor leaderboard.

Protocol 2 fixes the category labels, isolates FTS5 IDF statistics per conversation, and adds MRR, nDCG and p99. A full protocol-2 run is executed by the repository benchmark workflow and its exact-commit result is published separately; protocol-1 numbers are retained only as historical evidence.

Normal correctness CI runs on Linux, macOS and Windows. Heavy LoCoMo/model downloads are opt-in and never occur during normal index maintenance.

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

The package exposes the `thm` provider through Hermes' `hermes_agent.memory_providers` entry-point group. The pinned-upstream integration workflow verifies discovery and provider lifecycle against a real Hermes checkout; read the exact commit/run before treating that integration as current.

## Evidence boundaries

THM does **not** currently claim real-user end-to-end answer accuracy, a universally optimal decay curve, automatic tier movement, automatic deletion propagation, or a prompt-cache / perceived-latency improvement. `scan` records weak `mention_observed` evidence with zero activity weight. User-specific decay calibration requires an actual chronological use trace; synthetic traces are never substituted for that evidence.

Documentation: [project index](docs/README.md) · [engine guide](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [integration review](docs/10-recall-integration-review.md) · [benchmark protocol](research/recall/README.md)

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).