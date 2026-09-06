# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

THM is a local-first, four-tier memory toolkit for agent harnesses. It started from Hermes Agent and now keeps retrieval logic independent from harness plumbing: decide what deserves permanent context, load colder evidence under a fixed budget, and measure those decisions without fabricating “usage” signals.

## Four tiers

- **T0 — hot:** native permanent-context memory injected by the host.
- **T1 — warm:** thematic material loaded on demand.
- **T2 — cold:** historical sessions and archives searched under an explicit evidence budget.
- **T3 — external:** source locations and references that can be revisited when needed.

THM separates activity, validity, task relevance and explicit pinning. A mention is not a hit; retrieval is not proof of usefulness; a write is not a use event.

## What is implemented

The hardened 1.1.1 index CLI maintains profile-bound memory metadata, exact event identities, migration previews, pin/unpin semantics and failure-safe writes. The 1.2 retrieval package adds scoped FTS5 retrieval, optional local sentence embeddings, reciprocal-rank fusion, budget-counted context packing, zero-weight mention observations, multiple decay-policy comparisons and reproducible evaluation scripts.

**THM 1.3 adds a harness-neutral read-only recall layer.** It provides a standalone Hermes `MemoryProvider`, an OpenAI Agents SDK `FunctionTool`, a LangChain/LangGraph `BaseRetriever`, and a standard MCP v2 stdio server. The MCP surface is directly usable by MCP-capable harnesses; the repository separately tests OpenClaw's outbound MCP registry. See [Harness adapters](docs/11-harness-adapters.md).

Native source memory is not rewritten by retrieval or scan. Harness adapters open derived THM recall databases read-only unless an explicitly enabled host-specific live-session cache is being refreshed. Derived SQLite databases reject unrelated/native database targets before THM tables are created.

## Measured retrieval evidence

A completed **Protocol 2** LoCoMo run used all 10 conversations and 1,986 questions. The principal denominator contains 1,532 fully resolved, non-adversarial questions. At a fixed 600 `cl100k_base` evidence-token slice, any-gold coverage was **56.79% literal**, **69.39% sparse**, **51.11% MiniLM dense**, and **71.34% hybrid**. All-gold coverage was **46.61% / 56.53% / 40.01% / 57.64%** respectively. These are evidence-retrieval metrics, not answer accuracy and not a competitor leaderboard.

Protocol 2 corrects the LoCoMo category mapping, uses one FTS database per conversation so BM25/IDF statistics cannot leak across conversations, and reports MRR, nDCG and p99. At 600 tokens, sparse p95 retrieval+packing latency was **34.55 ms** and hybrid was **57.88 ms**. Hybrid gained **1.96 percentage points** of any-gold coverage over sparse in this workload; this is a measured tradeoff, not a universal default recommendation. Full evidence: [Protocol 2 report](reports/2026-09-06-recall-protocol2.md) · [machine-readable summary](reports/2026-09-06-recall-protocol2-summary.json).

The sparse budget sweep reached **60.57% / 69.39% / 76.17%** any-gold coverage at 300 / 600 / 1200 evidence tokens, with p95 retrieval+packing latency **20.39 / 34.55 / 61.78 ms**.

## Harness integration surfaces

| Surface | THM 1.3 integration |
| --- | --- |
| Hermes Agent | pip-discovered standalone `MemoryProvider`; setup schema/config, current-query prefetch, optional derived `sync_turn`, session boundary hooks and write≠hit semantics |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool` — one read-only `FunctionTool` |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp` / `python -m thm.mcp_server` exposes only `thm_recall` and `thm_status` |
| OpenClaw | local THM MCP server through OpenClaw's managed MCP registry |
| Claude Code / Codex CLI / Gemini CLI | standard local stdio MCP configuration; runtime-specific compatibility is distinguished from pinned E2E evidence |

The earlier Hermes E2E against `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` remains historical evidence. THM 1.3 CI additionally checks a reviewed current Hermes snapshot and the new multi-harness surfaces; use the exact workflow/commit reports rather than transferring an older result to newer code.

## Install and run

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Optional dependencies are split by function:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP example:

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Hermes lifecycle behavior

Hermes setup can save THM scope/mode/budget and optional live-turn synchronization to a profile-scoped private config. `sync_turns` is **off by default**. When explicitly enabled for a primary agent, THM reconciles user/assistant transcript text into a separate derived per-session T2 scope; system rows and marked compression summaries are not copied. `on_memory_write` remains a refresh signal, never a hit. THM deliberately stays on Hermes' best-effort pre-compress API v1 because the derived live cache is not the canonical transcript owner and therefore cannot truthfully promise fail-closed checkpoint-v2 durability.

## Decay calibration

Synthetic decay sweeps remain diagnostic only. For a real-user calibration, `research/recall/decay_from_index.py` exports a privacy-minimized chronology containing entry IDs, unit costs and explicit `hit` dates while excluding memory text, summaries, keys and confirmation evidence. The private trace can then be replayed through `decay_replay.py`. Without an actual chronological hit trace, THM does not claim a user-specific optimal half-life or curve.

## Evidence boundaries

THM does **not** currently claim real-user end-to-end answer accuracy, a universally optimal decay curve, automatic tier movement, automatic deletion propagation, or a prompt-cache / perceived-latency improvement. `scan` records weak `mention_observed` evidence with zero activity weight. The harness integrations deliberately make no second model call: retrieval coverage, host plumbing, model use of evidence and final answer quality remain separate evidence layers.

Normal correctness CI runs on Linux, macOS and Windows. Heavy LoCoMo/model downloads and harness integration jobs are separate. Documentation: [project index](docs/README.md) · [engine guide](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [Harness adapters](docs/11-harness-adapters.md) · [benchmark protocol](research/recall/README.md).

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).
