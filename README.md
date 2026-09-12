# THM — Tiered Hot Memory

**Local-first, deterministic memory infrastructure for AI agents.** THM separates what should stay hot from what can be recovered on demand, then measures the cost and evidence behind those decisions instead of asking another model to rewrite memory by default.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

<!-- section:architecture -->
## Three-plane architecture

THM separates logical memory, compute execution and physical storage. Version 1.5.0 brings these planes, Evaluation Fabric, explicit residency actuation and the independent Context Economics bridge into one implementation surface. Source identity and scope remain authoritative. Historical 1.4.0 evidence retains its original protocol and SHA; implementation stability does not grant hardware or task acceptance.

<!-- section:philosophy -->
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

<!-- section:logical -->
## Logical memory plane

Scoped SearchIndex retrieval, budgeted evidence packing and shadow residency control share one memory core. T0–T3 describe logical residency/access. Activity, validity, pinning and retrieval remain distinct; automatic promotion and budget write-back stay off.

The explicit actuator supports dry-run, replay, exact-plan approval, transactional placement updates, rollback and audit. Automatic mutation remains false by default; source validity, pinning, demand, capacity and evidence gates apply.

<!-- section:tiers -->
## The four tiers

| Tier | Role | Typical use |
| --- | --- | --- |
| **T0 — Hot** | Resident memory already carried by the host | Small, high-value context that repeatedly earns its residency |
| **T1 — Warm** | Locator-oriented material loaded on demand | Topic/file/source locators and bounded warm references |
| **T2 — Cold** | Searchable local history and archives | Scoped FTS/dense retrieval under an explicit evidence budget |
| **T3 — External** | Reacquirable source locations | Files, URLs or systems that can be revisited when needed |

T0–T3 are **THM memory Tiers**. They are not the L0–L6 Layers used by the separate Context Economics project.

<!-- section:compute -->
## Compute execution plane

The zero-touch runtime starts with a safe available path, observes real requests and explores installed providers within background resource limits. Provider Fabric separates inference, resident vector indexes and transfer across CPU, GPU and NPU runtimes. Semantic parity, material gain, freshness and session boundaries control adoption; users do not need to run a benchmark. Profiles and receipts record actual execution and fallback. Optional SDKs/models are never downloaded automatically, and implementation maturity does not imply hardware acceptance.

[Zero-touch runtime](docs/20-zero-touch-runtime.md) · [Provider Fabric](docs/21-provider-fabric.md) · [Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## Physical storage plane

StorageProfile describes measured access costs; placement binds a representation to a target. PhysicalTelemetry records extent I/O. Buffered/mmap files, transactional configured transports, S3, allocation ownership and joint placement have executable paths and fixtures. CXL, DAX, SPDK, GDS and remote families share bounded lifecycle contracts; native transport execution and hardware performance require separate evidence.

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Adapters normalize native inputs into Task, evaluator-only GroundTruth, Result and SHA-bound Receipt contracts. LoCoMo Protocol 2 and LongMemEval-S share dataplane metrics while retaining document-level versus session-level evidence. LongMemEval-V2 supports public trajectory states and insert/query; BEAM supports native batches/turns and probing questions; MemoryArena supports native subtasks and add/wrap_user_prompt across sessions.

Fixtures validate interfaces and deterministic retrieval only. V2 is a text-only operating point and rejects image queries. Missing gold locators yield null recall. MemoryArena task parsing is not environment execution. Answers and rubrics never enter retrieval documents.

| Evidence layer | Receipt contract |
| --- | --- |
| memory-dataplane | any/all-gold, macro/micro recall, parent coverage, budget, latency |
| systems-runtime | compute profile, StorageProfile, placement, I/O telemetry |
| LLM-agent-outcome | generation/judge calls, answer accuracy, environment success; not-run by default |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

EnvironmentRunner supplies a bounded environment lifecycle and OfficialScorerBridge keeps evaluator-only answers separate. Outcome attachment binds executed task IDs and trace SHA, supports partial coverage, missing scores, macro/micro results and observed latency/cost. THM exports unit- and denominator-bound evidence to Context Economics and accepts explicit budget/envelope advice without merging THM T0–T3 with CE L0–L6.

<!-- section:evidence -->
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

<!-- section:harness -->
## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn synchronization, session boundary hooks and memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native BaseRetriever, executable LangGraph node, Deep Agents recall/status tools and graph construction |
| **MCP v2** | Typed read-only `thm_recall` and `thm_status` over stdio |
| **OpenClaw** | Pinned compatibility probe through the legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle through the same read-only recall core |

Harness support does not turn THM into a universal memory database. Lifecycle depth differs by host; Hermes remains the deepest native integration.

<!-- section:quickstart -->
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

<!-- section:acceptance -->
## Bounded local acceptance

Run from the repository root with Python 3.10 or newer. No model download, provider key or dataset download is needed. The process-tree deadline is 3300 seconds, leaving room below 60 minutes for cleanup. A timeout/failure writes an incomplete receipt and returns nonzero; it never becomes passed evidence.

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

Full campaigns are independent opt-ins using --mode full-research --full-research --benchmark NAME --dataset FILE. They require externally prepared native inputs and any separately configured agent/environment/judge. This command only measures retrieval; it does not launch a live agent or grant benchmark acceptance.

<!-- section:invariants -->
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

<!-- section:boundary -->
## Evidence boundary

THM currently supports strong deterministic/local retrieval and shadow control experiments, but it does **not** claim:

- universal answer-quality improvement;
- a universally optimal decay curve;
- automatic T0–T3 movement is production-ready;
- automatic deletion propagation is safe;
- prompt-cache savings or user-perceived latency gains follow from retrieval metrics;
- a retrieved evidence item was necessarily used by the host model.

The evidence ladder stays explicit: unit/invariant evidence, retrieval benchmark evidence, harness lifecycle evidence and real task outcomes are different things.

<!-- section:documentation -->
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

THM 1.5.0 is an implementation milestone with separate integration, hardware, benchmark and task evidence. Rejected retrieval experiments remain reproducible and default-off.
