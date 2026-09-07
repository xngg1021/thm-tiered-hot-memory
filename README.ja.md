# THM — Tiered Hot Memory

**AI Agent 向けの local-first・deterministic な階層型 memory infrastructure。** THM は「何を hot に常駐させるべきか」と「何を必要時に取り戻せばよいか」を分離し、その判断を観測可能な cost と evidence で評価します。別の LLM に memory の再生成を常時依存する設計ではありません。

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | 日本語 | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

## THM が必要な理由

長時間動く Agent は、毎回の prompt に載せるには大きすぎる状態を蓄積します。すべてを常駐させれば carry cost を繰り返し払い、すべて捨てれば search / retrieval / reacquisition を繰り返すことになります。THM はこれを**residency・retrieval・bounded budget allocation** の問題として扱います。

中心となる問いは次です。

> **もう一度 LLM を呼ばずに、Agent Memory はどこまで強くできるか？**

そのため THM は deterministic signal、local index、明示的 provenance、固定 evidence budget、replayable control rule を優先します。Generative extraction、summary、memory rewrite は core dataplane の必須条件ではありません。

## Design philosophy

### 1. Source authority を守る

Native memory file、session transcript、external source が authoritative source です。SQLite/FTS、local embedding、locator などは**derived index / projection** にすぎません。Retrieval のために source を暗黙に書き換えません。

### 2. Residency・relevance・activity を混同しない

THM は次を別々に扱います。

- **tier** — どこに resident し、どう access されるか
- **activity** — Agent が実際に使ったか
- **validity** — まだ正しく有効か
- **pinning** — operator による明示的 constraint
- **retrieval evidence** — ある task で検索経路がその item を提示したか

Mention は hit ではなく、retrieval は usefulness の証明ではありません。Prefetch は demand ではなく、write は activity event ではありません。

### 3. Cold memory は安く保つ

Hot prompt は希少です。THM は locator と bounded retrieval により、cold material を必要になるまで resident context の外に置きます。短い locator は常駐する価値があっても、full source はそうでない場合があります。

### 4. Fixed budget も correctness の一部

大きな candidate pool に gold が存在するだけでは不十分です。最終 evidence slice に固定 token budget 内で実際に pack されたかを測ります。Oversized source、duplicate evidence、packing waste も retrieval loss の一部です。

### 5. Self-reinforcing retrieval を作らない

System が自分で prefetch / retrieve した item を、それだけの理由で将来さらに重要と扱うことを禁止します。Control plane は explicit demand evidence からのみ学習し、anti-self-training boundary を維持します。

### 6. Automation は evidence の後

THM は residency / prefetch / budget の shadow recommendation を出せますが、automatic promote/demote と automatic budget write-back は、held-out task evidence が quality・cost・latency・reacquisition の改善を示すまで無効です。

### 7. One core, multiple harness surfaces

Retrieval semantics は THM core に集約します。Hermes は最も深い lifecycle integration、OpenAI Agents と LangChain は native SDK adapter、MCP は複数 CLI/harness が共有できる protocol surface です。

## T0–T3 memory Tiers

| Tier | 役割 | 典型例 |
| --- | --- | --- |
| **T0 — Hot** | Host がすでに携帯する resident memory | 繰り返し resident value を生む小さな high-value context |
| **T1 — Warm** | 必要時に展開する locator-oriented memory | topic/file/source locator、bounded warm reference |
| **T2 — Cold** | 検索可能な local history/archive | 固定 evidence budget 内の scoped FTS/dense retrieval |
| **T3 — External** | 再取得可能な source location | file、URL、external system |

T0–T3 は **THM の memory Tier** です。別プロジェクト Context Economics の L0–L6 Layer とは独立した taxonomy です。

## 現在実装されているもの

THM は現在、次を実装しています。

- profile/scope isolated local index と fail-closed source/database validation
- SQLite FTS5 sparse retrieval、optional local sentence embedding、deterministic rank fusion
- token-budgeted evidence packing と source traceability
- explicit activity / validity / pin semantics と reproducible decay diagnostics
- harness-neutral read-only recall core
- Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2、selected CLI host 用 pinned compatibility bridge
- resident/hard-miss、planned-retrieval telemetry
- locator-only T1 warm directory と opt-in session-frozen Hermes locator snapshot
- miss cost と resident carry cost に基づく shadow T0 recommendation、bounded exact 0/1 packing
- bounded anti-self-training prefetch と shadow resident-budget feedback
- existing sparse/hybrid candidate だけを re-rank する opt-in zero-generative-LLM entity projection

Stable package line は **1.4.0** です。Zero-LLM entity projection は opt-in research successor として main にありますが、**1.5 stable とはしていません**。過去の version / PR / review / implementation chronology は [CHANGELOG.md](CHANGELOG.md) と [version history](docs/12-version-history.md) に置き、homepage には現在の設計と capability だけを置きます。

## Measured retrieval evidence

THM は retrieval evidence と answer-generation claim を分離します。

Canonical LoCoMo Protocol 2 は 1,532 fully resolved non-adversarial questions と固定 600 `cl100k_base` evidence-token slice を使います。

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

現在の opt-in deterministic entity projection は full-set sparse any-gold を **69.39% → 72.52%**、frozen 1,301-question holdout を **69.56% → 72.33%** に改善し、candidate coverage は変えていません。つまり追加モデルで candidate pool を広げたのではなく、**既存 candidate を 600-token slice により良く配置した** 結果です。

これは final answer accuracy、user satisfaction、universal superiority の指標ではありません。[Protocol 2](reports/2026-09-06-recall-protocol2.md) と [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md) を参照してください。

## Harness integration

| Surface | Integration depth |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native `BaseRetriever` surface |
| **MCP v2** | Typed read-only `thm_recall` / `thm_status` over stdio |
| **OpenClaw** | Legacy MCP bridge を使う pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle、同一 read-only recall core を利用 |

Multi-harness support は universal memory database を意味しません。Lifecycle integration の深さは host ごとに異なり、Hermes が最も深い native integration です。

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

## 守るべき invariants

- read-only retrieval は native memory を mutation しない
- retrieval/display/scan は usage activity を捏造しない
- `planned_retrieval` は miss ではない
- prefetch は demand / hit / renewal / promotion evidence を作らない
- residency benefit に使えるのは explicit `avoidable=true` miss だけ
- T1 `pinned` は automatic promotion を意味しない
- locator projection は locator-only で scope 内に解決される
- ordinary mid-session memory write は frozen Hermes prompt snapshot を暗黙に rebuild しない
- held-out task evidence がない限り automatic tier movement / budget write-back は disabled

## Evidence boundary

THM は deterministic/local retrieval と shadow-control experiment を提供しますが、universal answer-quality improvement、universal optimal decay curve、production-ready automatic T0–T3 movement、安全な automatic delete propagation、retrieval metric からの prompt-cache / user-latency 改善、retrieved evidence の model usage を主張しません。

Unit/invariant evidence、retrieval benchmark、harness lifecycle、real task outcome は別々の evidence class です。

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

THM は research software です。1.4.0 は accepted/stable implementation milestone、後続 retrieval frontier は明示的に unreleased です。Version identity は evidence class の代わりにはなりません。
