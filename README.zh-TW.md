# THM — Tiered Hot Memory

**面向 AI Agent 的本地優先、確定性分層記憶基礎設施。** THM 把「什麼值得保持熱駐留」與「什麼可以按需重新取得」分開，並用可觀測的成本與證據約束這些決策，而不是預設再呼叫一個 LLM 去重寫記憶。

[English](README.md) | [简体中文](README.zh-CN.md) | 繁體中文 | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者：Junfu Shi（SJF，xngg1021）· 授權條款：[MIT](LICENSE)

## 為什麼需要 THM

長時間運行的 Agent 會累積遠多於每輪 prompt 應該攜帶的狀態。兩個最直覺的方案都很昂貴：把所有內容永久塞進上下文，會反覆支付 carry cost；全部丟掉，又會不斷重新搜尋與取得。THM 把這件事視為一個**駐留、檢索與固定預算分配問題**。

核心問題是：

> **在不再呼叫另一個 LLM 的前提下，Agent Memory 到底能走多遠？**

因此 THM 優先使用確定性訊號、本地索引、顯式 provenance、有界 evidence budget 與可重放控制規則。生成式抽取、摘要或記憶重寫都不是核心 dataplane 的前置條件。

## 設計理念

### 1. 原始來源始終具有權威性

原生 memory 檔案、session transcript 與外部來源才是事實來源。SQLite/FTS、本地 embedding、locator 與其他 THM 結構只是**派生索引或投影**。檢索系統不能為了「記住」而悄悄改寫正在檢索的原始內容。

### 2. 駐留不等於相關，檢索也不等於使用

THM 明確區分：

- **tier**：內容駐留在哪裡、透過什麼方式存取；
- **activity**：Agent 是否真正使用了它；
- **validity**：內容是否仍然有效、可信；
- **pinning**：操作者的顯式固定約束；
- **retrieval evidence**：某次任務是否透過檢索路徑把它暴露出來。

提及不等於 hit，retrieval 不證明有用，prefetch 不等於 demand，write 也不是 activity event。

### 3. 冷記憶應保持便宜

熱 prompt 是稀缺資源。THM 用 locator 與有界檢索，讓較冷內容留在 resident context 之外，直到任務確實需要它。幾十 token 的 locator 可能值得常駐，而完整來源不值得。

### 4. 固定預算本身就是 correctness 的一部分

THM 不只統計「gold 是否出現在很大的 candidate pool」，還要求 evidence 真正被打包進固定 token budget。candidate 已找到但沒有進入最終 evidence slice，仍然是實際損失；超大 source、重複內容與 packing waste 都必須被量到。

### 5. 禁止檢索系統自我強化

某條內容不能只因系統自己 prefetched/retrieved 過，就自動變得「更重要」。控制面只能從明確的真實 demand 證據學習，並保持 anti-self-training 邊界。

### 6. 自動控制必須晚於證據

THM 可以先產生 residency、prefetch 與 budget 的 shadow recommendation，但自動 promote/demote 與自動 budget write-back 持續關閉，直到 held-out task evidence 證明品質、成本、延遲與 reacquisition 的淨收益。

### 7. 一個記憶核心，多種 Harness 介面

THM 的 retrieval semantics 屬於統一 core，不為每個宿主複製一套實作。Hermes 有最深的 lifecycle integration；OpenAI Agents 與 LangChain 使用原生 SDK adapter；MCP 提供多個 CLI/harness 可共用的標準協定面。

## T0–T3 四個 Tier

| Tier | 角色 | 典型用途 |
| --- | --- | --- |
| **T0 — Hot** | 已由宿主攜帶的 resident memory | 反覆證明其駐留價值的高價值小上下文 |
| **T1 — Warm** | 按需展開的 locator-oriented memory | topic/file/source locator 與有界 warm reference |
| **T2 — Cold** | 可搜尋的本地歷史與檔案 | 在固定 evidence budget 下做 scoped FTS/dense retrieval |
| **T3 — External** | 可重新取得的外部來源 | 檔案、URL 或需要時重新訪問的外部系統 |

T0–T3 是 **THM 的 memory Tier**，不是另一個獨立專案 Context Economics 的 L0–L6 Layer。

## 目前已實作能力

THM 目前包括：

- profile/scope 隔離的本地索引，以及 fail-closed source/database 檢查；
- SQLite FTS5 sparse retrieval、可選本地 sentence embedding 與確定性 rank fusion；
- token-budgeted evidence packing 與完整 source traceability；
- 顯式 activity / validity / pin 語義與可重現 decay diagnostics；
- harness-neutral 的唯讀 recall core；
- Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2，以及面向特定 CLI host 的 pinned compatibility bridge；
- resident/hard-miss 與 planned-retrieval telemetry；
- locator-only T1 warm directory 與預設關閉、session-frozen 的 Hermes locator snapshot；
- 基於 miss cost 與 resident carry cost 的 shadow T0 recommendation，並使用有界 exact 0/1 packing；
- bounded anti-self-training prefetch 與 shadow resident-budget feedback；
- 可選的 zero-generative-LLM entity projection：只重排既有 sparse/hybrid candidate，不改變 canonical T0–T3 模型。

穩定 package line 仍為 **1.4.0**。zero-LLM entity projection 已合入 main 作為 opt-in research successor，但**沒有登記為 1.5 stable**。歷史版本、PR、Review 與施工 chronology 統一放在 [CHANGELOG.md](CHANGELOG.md) 與 [版本歷史](docs/12-version-history.md)，不再堆在首頁。

## 已量測的檢索證據

THM 始終把 retrieval evidence 與 answer-generation claim 分開。

Canonical LoCoMo Protocol 2 使用 1,532 道證據完全解析的非對抗問題，固定 600 個 `cl100k_base` evidence tokens。accepted baseline：

| 檢索模式 | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

目前 opt-in deterministic entity projection 將全量 sparse any-gold 從 **69.39% 提高到 72.52%**，凍結的 1,301 道 holdout 從 **69.56% 提高到 72.33%**，candidate coverage 不變。這表示收益來自把**已存在的 candidate** 更好地排進 600-token slice，而不是再呼叫模型擴大 candidate pool。

這些數字只衡量**最終打包進去的檢索證據**，不等於最終回答正確率、使用者滿意度或普適優越性。詳見 [Protocol 2](reports/2026-09-06-recall-protocol2.md) 與 [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md)。

## Harness 整合

| Surface | 整合深度 |
| --- | --- |
| **Hermes Agent** | 原生 `MemoryProvider`；setup/config、prefetch、可選 live-turn sync、session boundary hooks、memory-write refresh semantics |
| **OpenAI Agents SDK** | 原生唯讀 `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | 原生 `BaseRetriever` surface |
| **MCP v2** | 透過 stdio 提供有型別的 `thm_recall` 與 `thm_status` |
| **OpenClaw** | 透過 legacy MCP bridge 做 pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | 真實固定版本 CLI discovery/call lifecycle，共用同一唯讀 recall core |

多 Harness 支援不表示 THM 是「萬能 memory database」。不同宿主的 lifecycle depth 不同，Hermes 仍是最深的 native integration。

## 快速開始

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

按需安裝可選依賴：

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP：

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## 必須保持的系統不變量

THM 對狀態改變刻意保持保守：

- 唯讀 retrieval 不改寫 native memory；
- retrieval/display/scan 不偽造 usage activity；
- `planned_retrieval` 不是 miss；
- prefetch 不產生 demand、hit、renewal 或 promotion evidence；
- 只有明確標記為 avoidable 的 miss 才可計入 residency benefit；
- T1 `pinned` 不自動代表 promotion；
- locator projection 必須保持 locator-only，並在正確 scope 內解析；
- 一般 mid-session memory write 不會悄悄重建 Hermes 已凍結的 prompt snapshot；
- 沒有 held-out task evidence 時，自動 tier movement 與自動 budget write-back 保持關閉。

## 證據邊界

THM 目前已支援較強的 deterministic/local retrieval 與 shadow control experiment，但不宣稱：

- 普適提升最終回答品質；
- 存在對所有使用者最優的 decay curve；
- 自動 T0–T3 movement 已 production-ready；
- 自動 delete propagation 已安全；
- retrieval metric 提升必然帶來 prompt-cache 或使用者感知延遲收益；
- 被檢索出的 evidence 一定被宿主模型真正使用。

unit/invariant、retrieval benchmark、harness lifecycle 與 real task outcome 是不同類型的證據，不能互相冒充。

## 文件

- [文件目錄](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [版本歷史與恢復](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM 仍是研究軟體：1.4.0 是 accepted/stable implementation milestone，之後的 retrieval frontier 明確保持 unreleased。版本號永遠不能替代 evidence class。