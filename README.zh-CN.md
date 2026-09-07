# THM — Tiered Hot Memory

**面向 AI Agent 的本地优先、确定性分层记忆基础设施。** THM 把“什么应该保持热驻留”和“什么可以按需重新取得”分开，并用可观测的成本与证据来约束这些决策，而不是默认再调用一个 LLM 去重写记忆。

[English](README.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者：Junfu Shi（SJF，xngg1021）· 许可证：[MIT](LICENSE)

## 为什么需要 THM

长期运行的 Agent 会积累远多于每轮 prompt 应该携带的状态。两个最朴素的方案都很昂贵：把所有内容永久塞进上下文，会反复支付携带成本；全部丢掉，又会不断重新搜索和获取。THM 把这件事视为一个**驻留、检索和固定预算分配问题**。

核心问题是：

> **在不再调用另一个 LLM 的前提下，Agent Memory 到底能走多远？**

因此 THM 优先使用确定性信号、本地索引、显式 provenance、有界 evidence budget 和可重放的控制规则。生成式抽取、总结或记忆重写都不是核心 dataplane 的前置条件。

## 设计理念

### 1. 原始来源始终具有权威性

原生 memory 文件、会话 transcript 和外部来源才是事实来源。SQLite/FTS、本地 embedding、locator 与其他 THM 结构只是**派生索引或投影**。检索系统不能为了“记住”而悄悄改写它正在检索的原始内容。

### 2. 驻留不等于相关，检索也不等于使用

THM 明确区分：

- **tier**：内容驻留在哪里、通过什么方式访问；
- **activity**：Agent 是否真正使用了它；
- **validity**：内容是否仍然有效、可信；
- **pinning**：操作者的显式固定约束；
- **retrieval evidence**：某次任务是否通过检索路径把它暴露出来。

提及不等于 hit，retrieval 不证明有用，prefetch 不等于 demand，write 也不是 activity event。

### 3. 冷记忆应该保持便宜

热 prompt 是稀缺资源。THM 用 locator 与有界检索，让较冷内容留在 resident context 之外，直到任务确实需要它。一个几十 token 的 locator 可能值得常驻，而完整来源并不值得。

### 4. 固定预算本身就是 correctness 的一部分

THM 不只统计“gold 有没有出现在很大的候选池里”，还要求证据真正被打包进固定 token budget。candidate 已找到但没有进入最终 evidence slice，仍然算实际损失；超大 source、重复内容和 packing 浪费都必须被看见。

### 5. 禁止检索系统自我强化

某条内容不能因为系统自己 prefetched/retrieved 过，就自动变得“更重要”。控制面只从明确的真实 demand 证据学习，并保持 anti-self-training 边界。

### 6. 自动控制必须晚于证据

THM 可以先给出 residency、prefetch 和 budget 的 shadow recommendation，但自动 promote/demote 与自动 budget write-back 继续关闭，直到 held-out task evidence 能证明质量、成本、延迟和 reacquisition 的净收益。

### 7. 一个记忆核心，多种 Harness 接口

THM 的检索语义属于统一 core，不为每个宿主复制一套实现。Hermes 有最深的生命周期集成；OpenAI Agents 与 LangChain 使用原生 SDK adapter；MCP 提供多个 CLI/harness 可复用的标准协议面。

## T0–T3 四个 Tier

| Tier | 角色 | 典型用途 |
| --- | --- | --- |
| **T0 — Hot** | 已由宿主携带的 resident memory | 反复证明其驻留价值的高价值小上下文 |
| **T1 — Warm** | 按需展开的 locator-oriented memory | topic/file/source locator 与有界 warm reference |
| **T2 — Cold** | 可搜索的本地历史与档案 | 在固定 evidence budget 下做 scoped FTS/dense retrieval |
| **T3 — External** | 可重新访问的外部来源 | 文件、URL 或需要时重新取得的外部系统 |

T0–T3 是 **THM 的 memory Tier**，不是另一个独立项目 Context Economics 的 L0–L6 Layer。

## 当前已经实现的能力

THM 目前包括：

- profile/scope 隔离的本地索引，以及 fail-closed source/database 检查；
- SQLite FTS5 sparse retrieval、可选本地 sentence embedding 与确定性 rank fusion；
- token-budgeted evidence packing 与完整 source traceability；
- 显式 activity / validity / pin 语义与可复现 decay diagnostics；
- harness-neutral 的只读 recall core；
- Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2，以及面向特定 CLI host 的 pinned compatibility bridge；
- resident/hard-miss 与 planned-retrieval telemetry；
- locator-only T1 warm directory 与默认关闭、session-frozen 的 Hermes locator snapshot；
- 基于 miss cost 与 resident carry cost 的 shadow T0 recommendation，并使用有界 exact 0/1 packing；
- bounded anti-self-training prefetch 与 shadow resident-budget feedback；
- 可选的 zero-generative-LLM entity projection：只重排已有 sparse/hybrid candidate，不改变 canonical T0–T3 模型。

稳定 package line 仍为 **1.4.0**。zero-LLM entity projection 已合入 main 作为 opt-in research successor，但**没有被登记为 1.5 stable**。所有历史版本、PR、review 与施工过程统一放在 [CHANGELOG.md](CHANGELOG.md) 和 [版本历史](docs/12-version-history.md)，不再堆到首页。

## 已测量的检索证据

THM 始终把 retrieval evidence 与 answer-generation claim 分开。

Canonical LoCoMo Protocol 2 使用 1,532 道证据完全解析的非对抗问题，并固定 600 个 `cl100k_base` evidence tokens。accepted baseline 为：

| 检索模式 | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

当前 opt-in deterministic entity projection 将全量 sparse any-gold 从 **69.39% 提高到 72.52%**，冻结的 1,301 道 holdout 从 **69.56% 提高到 72.33%**，candidate coverage 保持不变。这个结果说明收益来自把 **已经存在的候选** 更好地排进 600-token slice，而不是再调用模型扩大 candidate pool。

这些数字只衡量**最终打包进去的检索证据**，不等于最终回答正确率、用户满意度或普适优越性。详见 [Protocol 2](reports/2026-09-06-recall-protocol2.md) 和 [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md)。

## Harness 集成

| Surface | 集成深度 |
| --- | --- |
| **Hermes Agent** | 原生 `MemoryProvider`；setup/config、prefetch、可选 live-turn sync、session boundary hooks、memory-write refresh semantics |
| **OpenAI Agents SDK** | 原生只读 `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | 原生 `BaseRetriever` surface |
| **MCP v2** | 通过 stdio 提供有类型的 `thm_recall` 与 `thm_status` |
| **OpenClaw** | 通过 legacy MCP bridge 做 pinned compatibility probe |
| **Claude Code / Codex CLI / Gemini CLI** | 真实固定版本 CLI discovery/call lifecycle，共用同一只读 recall core |

多 Harness 支持不意味着 THM 是“万能 memory database”。不同宿主的 lifecycle depth 不同，Hermes 仍是最深的 native integration。

## 快速开始

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

按需安装可选依赖：

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

## 必须保持的系统不变量

THM 对状态变化刻意保持保守：

- 只读 retrieval 不改写 native memory；
- retrieval/display/scan 不伪造 usage activity；
- `planned_retrieval` 不是 miss；
- prefetch 不产生 demand、hit、renewal 或 promotion evidence；
- 只有显式标记为 avoidable 的 miss 才能计入 residency benefit；
- T1 `pinned` 不自动意味着 promotion；
- locator projection 必须保持 locator-only，并在正确 scope 内解析；
- 普通 mid-session memory write 不会悄悄重建 Hermes 已冻结的 prompt snapshot；
- 没有 held-out task evidence 时，自动 tier movement 和自动 budget write-back 保持关闭。

## 证据边界

THM 当前已经支持较强的 deterministic/local retrieval 与 shadow control experiment，但不宣称：

- 普适提升最终回答质量；
- 存在对所有用户最优的 decay curve；
- 自动 T0–T3 movement 已经 production-ready；
- 自动 delete propagation 已经安全；
- retrieval metric 的提升必然带来 prompt-cache 或用户感知延迟收益；
- 被检索出来的 evidence 一定被宿主模型真正使用。

unit/invariant、retrieval benchmark、harness lifecycle 和 real task outcome 是四类不同证据，不能互相冒充。

## 文档

- [文档目录](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [版本历史与恢复](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM 仍是研究软件：1.4.0 是 accepted/stable implementation milestone，之后的 retrieval frontier 明确保持 unreleased。版本号永远不能替代 evidence class。