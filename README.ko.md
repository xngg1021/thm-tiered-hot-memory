# THM — Tiered Hot Memory

**AI Agent를 위한 local-first, deterministic 계층형 memory infrastructure.** THM은 무엇을 hot 상태로 상주시킬지와 무엇을 필요할 때 다시 가져올지를 분리하고, 그 판단을 관측 가능한 cost와 evidence로 평가합니다. 또 하나의 LLM이 memory를 계속 다시 쓰도록 의존하는 구조가 아닙니다.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | 한국어 | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

작성자: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

## 왜 THM이 필요한가

장기 실행 Agent는 매 요청의 prompt에 항상 포함하기에는 너무 많은 상태를 축적합니다. 전부 상주시켜 두면 반복적인 carry cost를 내야 하고, 전부 버리면 search / retrieval / reacquisition을 반복해야 합니다. THM은 이 문제를 **residency, retrieval, bounded budget allocation** 문제로 다룹니다.

핵심 질문은 다음과 같습니다.

> **다른 LLM 호출 없이 Agent Memory는 어디까지 갈 수 있는가?**

그래서 THM은 deterministic signal, local index, explicit provenance, 고정 evidence budget, replayable control rule을 우선합니다. Generative extraction, summary, memory rewrite는 core dataplane의 필수 전제가 아닙니다.

## Design philosophy

### 1. Source authority를 유지한다

Native memory file, session transcript, external source가 authoritative source입니다. SQLite/FTS, local embedding, locator 등은 **derived index / projection**입니다. Retrieval을 위해 원본 memory를 암묵적으로 다시 쓰지 않습니다.

### 2. Residency, relevance, activity를 섞지 않는다

THM은 다음을 분리합니다.

- **tier** — 어디에 resident하며 어떻게 access되는가
- **activity** — Agent가 실제로 사용했는가
- **validity** — 아직 유효하고 신뢰할 수 있는가
- **pinning** — operator가 명시적으로 고정했는가
- **retrieval evidence** — 특정 task에서 retrieval path가 해당 item을 노출했는가

Mention은 hit이 아니고, retrieval은 usefulness의 증거가 아닙니다. Prefetch는 demand가 아니며, write도 activity event가 아닙니다.

### 3. Cold memory는 싸게 유지한다

Hot prompt는 희소합니다. THM은 locator와 bounded retrieval을 사용해 cold material을 실제로 필요해질 때까지 resident context 밖에 둡니다. 짧은 locator는 상주할 가치가 있어도 full source는 그렇지 않을 수 있습니다.

### 4. Fixed budget도 correctness의 일부다

큰 candidate pool 어딘가에 gold가 있다는 것만으로 충분하지 않습니다. 최종 evidence slice에 실제로 고정 token budget 안에서 pack되었는지를 측정합니다. Oversized source, duplicate evidence, packing waste도 실제 retrieval loss입니다.

### 5. Self-reinforcing retrieval을 만들지 않는다

System이 스스로 prefetch/retrieve한 item이라는 이유만으로 앞으로 더 중요해지게 만들지 않습니다. Control plane은 explicit demand evidence에서만 학습하며 anti-self-training boundary를 유지합니다.

### 6. Automation은 evidence 이후에 온다

THM은 residency, prefetch, budget에 대한 shadow recommendation을 만들 수 있지만 automatic promote/demote와 automatic budget write-back은 held-out task evidence가 quality, cost, latency, reacquisition 개선을 입증하기 전까지 비활성화됩니다.

### 7. 하나의 memory core, 여러 Harness surface

Retrieval semantics는 THM core에 둡니다. Hermes는 가장 깊은 lifecycle integration을 가지며, OpenAI Agents와 LangChain은 native SDK adapter를 사용하고, MCP는 여러 CLI/harness가 공유하는 protocol surface를 제공합니다.

## T0–T3 memory Tiers

| Tier | 역할 | 대표 사용처 |
| --- | --- | --- |
| **T0 — Hot** | Host가 이미 들고 있는 resident memory | 반복적으로 residency 가치를 증명하는 작고 중요한 context |
| **T1 — Warm** | 필요할 때 펼치는 locator-oriented memory | topic/file/source locator와 bounded warm reference |
| **T2 — Cold** | 검색 가능한 local history/archive | 고정 evidence budget 아래 scoped FTS/dense retrieval |
| **T3 — External** | 다시 접근 가능한 source location | file, URL, 외부 시스템 |

T0–T3는 **THM memory Tier**입니다. 별도 프로젝트인 Context Economics의 L0–L6 Layer와는 독립된 taxonomy입니다.

## 현재 구현된 기능

THM은 현재 다음을 제공합니다.

- profile/scope isolated local index와 fail-closed source/database validation
- SQLite FTS5 sparse retrieval, optional local sentence embedding, deterministic rank fusion
- token-budgeted evidence packing과 source traceability
- explicit activity / validity / pin semantics와 reproducible decay diagnostics
- harness-neutral read-only recall core
- Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2, selected CLI host용 pinned compatibility bridge
- resident/hard-miss 및 planned-retrieval telemetry
- locator-only T1 warm directory와 opt-in session-frozen Hermes locator snapshot
- miss cost와 resident carry cost를 사용하는 shadow T0 recommendation 및 bounded exact 0/1 packing
- bounded anti-self-training prefetch와 shadow resident-budget feedback
- 기존 sparse/hybrid candidate만 re-rank하는 opt-in zero-generative-LLM entity projection

Stable package line은 **1.4.0**입니다. Zero-LLM entity projection은 opt-in research successor로 main에 병합되어 있지만 **1.5 stable로 선언되지 않았습니다**. 과거 version/PR/review/implementation chronology는 [CHANGELOG.md](CHANGELOG.md)와 [version history](docs/12-version-history.md)에 두고 homepage에는 현재 설계와 capability만 둡니다.

## Measured retrieval evidence

THM은 retrieval evidence와 answer-generation claim을 분리합니다.

Canonical LoCoMo Protocol 2는 1,532 fully resolved non-adversarial questions와 고정 600 `cl100k_base` evidence-token slice를 사용합니다.

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

현재 opt-in deterministic entity projection은 full-set sparse any-gold를 **69.39% → 72.52%**, frozen 1,301-question holdout을 **69.56% → 72.33%**로 높이며 candidate coverage는 바꾸지 않습니다. 즉 추가 모델로 candidate pool을 키운 것이 아니라 **이미 존재하는 candidate를 600-token slice 안에 더 잘 배치한 결과**입니다.

이 수치는 final answer accuracy, user satisfaction, universal superiority가 아니라 **packed retrieval evidence**를 측정합니다. [Protocol 2](reports/2026-09-06-recall-protocol2.md)와 [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md)를 참고하십시오.

## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native `BaseRetriever` surface |
| **MCP v2** | stdio 기반 typed read-only `thm_recall` / `thm_status` |
| **OpenClaw** | legacy MCP bridge를 통한 pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | pinned real-CLI discovery/call lifecycle, 동일 read-only recall core 사용 |

Multi-harness support가 universal memory database를 의미하지는 않습니다. Lifecycle integration의 깊이는 host마다 다르고 Hermes가 가장 깊은 native integration입니다.

## Quick start

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Optional dependencies:

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

## 반드시 지켜야 할 invariants

- read-only retrieval은 native memory를 mutate하지 않는다
- retrieval/display/scan은 usage activity를 만들어내지 않는다
- `planned_retrieval`은 miss가 아니다
- prefetch는 demand / hit / renewal / promotion evidence를 만들지 않는다
- residency benefit에는 explicit `avoidable=true` miss만 사용한다
- T1 `pinned`은 automatic promotion을 뜻하지 않는다
- locator projection은 locator-only이며 올바른 scope 내부에 resolve되어야 한다
- ordinary mid-session memory write는 frozen Hermes prompt snapshot을 암묵적으로 rebuild하지 않는다
- held-out task evidence가 없으면 automatic tier movement와 budget write-back은 disabled 상태를 유지한다

## Evidence boundary

THM은 deterministic/local retrieval과 shadow-control experiment를 제공하지만 universal answer-quality improvement, universal optimal decay curve, production-ready automatic T0–T3 movement, 안전한 automatic delete propagation, retrieval metric에서 자동으로 추론한 prompt-cache/user-latency 개선, retrieved evidence의 실제 model usage를 주장하지 않습니다.

Unit/invariant evidence, retrieval benchmark, harness lifecycle, real task outcome은 서로 다른 evidence class입니다.

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

THM은 research software입니다. 1.4.0은 accepted/stable implementation milestone이고 후속 retrieval frontier는 명시적으로 unreleased입니다. Version identity는 evidence class를 대신하지 않습니다.