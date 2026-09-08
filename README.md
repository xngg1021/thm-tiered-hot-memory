# THM — Tiered Hot Memory

**Local-first, deterministic memory infrastructure for AI agents.** THM separates what should stay hot from what can be recovered on demand, then measures the cost and evidence behind those decisions instead of asking another model to rewrite memory by default.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

## Why THM exists

Long-running agents accumulate more state than should be injected into every prompt. The naive choices are both expensive: keep everything resident and repeatedly pay for it, or discard context and repeatedly rediscover it. THM treats memory as a residency and retrieval problem.

The central question is:

> **How far can agent memory go without another LLM call?**

THM therefore prefers deterministic signals, local indexes, explicit provenance, bounded evidence budgets and replayable control rules. Generative extraction, summarization or memory rewriting are not prerequisites for the core dataplane.

## Design philosophy

### 1. The source remains authoritative

Native memory files, transcripts and external sources are the authority. SQLite/FTS, local embeddings, locators and other THM structures are **derived indexes or projections**. Retrieval must not silently rewrite the source it is trying to remember.

### 2. Residency is not the same thing as relevance

THM keeps several concepts separate:

- **tier** — where an item resides or how it is accessed;
- **activity** — whether the agent actually used it;
- **validity** — whether the item is still current and trustworthy;
- **pinning** — an explicit operator constraint;
- **retrieval evidence** — whether a search path surfaced it for a task.

A mention is not a hit. Retrieval is not proof of usefulness. Prefetch is not demand. A write is not an activity event.

### 3. Cold memory should stay cheap

The hot prompt is scarce. THM uses locators and bounded retrieval so colder material can stay outside the resident context until a task actually needs it. A short locator may be worth carrying even when the full source is not.

### 4. Fixed budgets are part of correctness

Retrieval quality is measured after evidence is actually packed into a fixed token budget, not only when a gold item happens to appear somewhere in a large candidate set. Oversized or duplicate evidence therefore matters.

### 5. No self-reinforcing retrieval loops

A prefetched or retrieved item must not become “important” merely because the system itself surfaced it. Control-plane learning uses explicit demand evidence and preserves anti-self-training boundaries.

### 6. Automation follows evidence

THM can recommend residency, prefetch and budget changes, but automatic promotion/demotion and automatic budget mutation remain disabled until held-out task evidence justifies them. Shadow recommendations come before production control.

### 7. One memory core, multiple harness surfaces

Retrieval semantics live in THM rather than being reimplemented for every host. Hermes has the deepest lifecycle integration; OpenAI Agents and LangChain expose native SDK adapters; MCP provides the protocol surface used by several CLI/harness integrations.

## The four tiers

| Tier | Role | Typical use |
| --- | --- | --- |
| **T0 — Hot** | Resident memory already carried by the host | Small, high-value context that repeatedly earns its residency |
| **T1 — Warm** | Locator-oriented material loaded on demand | Topic/file/source locators and bounded warm references |
| **T2 — Cold** | Searchable local history and archives | Scoped FTS/dense retrieval under an explicit evidence budget |
| **T3 — External** | Reacquirable source locations | Files, URLs or systems that can be revisited when needed |

T0–T3 are **THM memory Tiers**. They are not the L0–L6 Layers used by the separate Context Economics project.

## What is implemented

THM currently provides:

- profile/scope-isolated local indexing with fail-closed source and database checks;
- sparse SQLite FTS5 retrieval, optional local sentence embeddings and deterministic rank fusion;
- token-budgeted evidence packing and source traceability;
- explicit activity/validity/pin semantics and reproducible decay diagnostics;
- a harness-neutral read-only recall core;
- Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 and a pinned compatibility bridge for selected CLI hosts;
- resident/hard-miss and planned-retrieval telemetry;
- a locator-only T1 warm directory and an opt-in session-frozen Hermes locator snapshot;
- shadow value-aware T0 recommendations with bounded exact 0/1 packing;
- bounded anti-self-training prefetch and shadow resident-budget feedback;
- an opt-in zero-generative-LLM entity projection that re-ranks existing sparse/hybrid candidates without changing the canonical T0–T3 model.

The stable package line remains **1.4.0**. The zero-LLM entity projection is merged as an opt-in research successor and is **not** labeled 1.5 stable. Detailed historical changes belong in [CHANGELOG.md](CHANGELOG.md) and [version history](docs/12-version-history.md), not on this homepage.

## Measured retrieval evidence

THM publishes retrieval evidence separately from answer-generation claims.

Under the canonical LoCoMo Protocol 2 setup — 1,532 fully resolved non-adversarial questions and a fixed 600 `cl100k_base` evidence-token slice — the accepted baseline reports:

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

The current opt-in deterministic entity projection raises full-set sparse any-gold from **69.39% to 72.52%** and the frozen 1,301-question holdout from **69.56% to 72.33%**, with candidate coverage unchanged. That result is important because the gain comes from ranking already available candidates into the 600-token slice rather than expanding the candidate pool with another model.

These numbers measure **packed retrieval evidence**, not final answer accuracy, user satisfaction or universal superiority. See [Protocol 2](reports/2026-09-06-recall-protocol2.md) and the [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md).

## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn synchronization, session boundary hooks and memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native `BaseRetriever` surface |
| **MCP v2** | Typed read-only `thm_recall` and `thm_status` over stdio |
| **OpenClaw** | Pinned compatibility probe through the legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle through the same read-only recall core |

Harness support does not turn THM into a universal memory database. Lifecycle depth differs by host; Hermes remains the deepest native integration.

## Quick start

```bash
python -m pip install -e .
python -m thm --help

python -m thm import-files ./notes \
  --db ./state/recall.sqlite3 \
  --scope demo

python -m thm search \
  --db ./state/recall.sqlite3 \
  --scope demo \
  "Which database port?" \
  --budget 600
```

Optional capabilities are installed separately:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP:

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Invariants that matter

THM is deliberately conservative around state mutation:

- read-only retrieval does not mutate native memory;
- retrieval/display/scan do not fabricate usage activity;
- `planned_retrieval` is not a miss;
- prefetch does not create demand, hit, renewal or promotion evidence;
- only explicitly avoidable misses may contribute residency benefit;
- T1 `pinned` does not imply automatic promotion;
- locator projections remain locator-only and must resolve inside the intended scope;
- ordinary mid-session memory writes do not silently rebuild a frozen Hermes prompt snapshot;
- automatic tier movement and automatic budget write-back remain off without held-out task evidence.

## Evidence boundary

THM currently supports strong deterministic/local retrieval and shadow control experiments, but it does **not** claim:

- universal answer-quality improvement;
- a universally optimal decay curve;
- automatic T0–T3 movement is production-ready;
- automatic deletion propagation is safe;
- prompt-cache savings or user-perceived latency gains follow from retrieval metrics;
- a retrieved evidence item was necessarily used by the host model.

The evidence ladder stays explicit: unit/invariant evidence, retrieval benchmark evidence, harness lifecycle evidence and real task outcomes are different things.

## Documentation

- [Documentation index](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [Version history and recovery](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM is research software with an accepted 1.4.0 stable implementation milestone and an explicitly unreleased retrieval frontier. Version identity never substitutes for evidence class.

## Unreleased runtime successor

The optional zero-LLM hardware/profile/AutoTune runtime, identity-safe vector storage, batching and default-off deterministic retrieval experiments are implemented for local acceptance. Core installation stays model-free; no performance or feature admission is implied. See [runtime architecture](docs/17-zero-llm-heterogeneous-runtime.md) and [local verification package](reports/2026-09-08-local-runtime-verification-plan.md). Stable remains unchanged.
