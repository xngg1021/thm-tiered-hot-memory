# THM — Tiered Hot Memory

**面向 AI Agent 的本地优先、确定性分层记忆基础设施。** THM 把“什么应该保持热驻留”和“什么可以按需重新取得”分开，并用可观测的成本与证据来约束这些决策，而不是默认再调用一个 LLM 去重写记忆。

[English](README.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md)

作者：Junfu Shi（SJF，xngg1021）· 许可证：[MIT](LICENSE)

<!-- section:architecture -->
## 三平面架构

THM 将逻辑记忆、计算执行和物理存储分开。Evaluation Fabric 在三个平面上统一测量，不引入新的记忆算法。原始来源身份和 scope 在各种表示之间始终保持权威。

架构与证据契约

稳定 package 与 archive 保持 1.4.0。Runtime、Physical Storage Fabric 与 Evaluation Fabric 继续标为 Unreleased。既有测量保留原始 protocol、source SHA 和适用范围，未执行的 benchmark 与硬件不计入 accepted evidence。

<!-- section:philosophy -->
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

<!-- section:logical -->
## 逻辑记忆平面

带 scope 的 SearchIndex 检索、预算内证据打包和影子驻留控制共用一个记忆核心。T0–T3 表示逻辑驻留与访问方式。活动、有效性、固定约束和检索分别记录；自动提升和预算回写继续关闭。

<!-- section:tiers -->
## T0–T3 四个 Tier

| Tier | 角色 | 典型用途 |
| --- | --- | --- |
| **T0 — Hot** | 已由宿主携带的 resident memory | 反复证明其驻留价值的高价值小上下文 |
| **T1 — Warm** | 按需展开的 locator-oriented memory | topic/file/source locator 与有界 warm reference |
| **T2 — Cold** | 可搜索的本地历史与档案 | 在固定 evidence budget 下做 scoped FTS/dense retrieval |
| **T3 — External** | 可重新访问的外部来源 | 文件、URL 或需要时重新取得的外部系统 |

T0–T3 是 **THM 的 memory Tier**，不是另一个独立项目 Context Economics 的 L0–L6 Layer。

<!-- section:compute -->
## 计算执行平面

RuntimeProfile 绑定编码器与 backend、精度、设备、scorer、批大小和线程设置。可选调度器与有界 AutoTune 选择明确的运行配置。CPU/CUDA 等 backend 描述需要独立 runtime 证据；fixture 通过不能证明实际 dispatch 或加速。

[Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## 物理存储平面

StorageProfile 描述实测访问成本，placement 将数据表示绑定到目标，PhysicalTelemetry 记录实际 extent I/O。已经实现经过验证的本地文件系统 buffered/mmap 路径；CXL、DAX、SPDK、GDS 和远程传输条目仍是扩展描述，硬件性能未经验收。

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric 评估体系

Adapter 将原生输入统一为 Task、仅评分器可见的 GroundTruth、Result 和 SHA 绑定的 Receipt。LoCoMo Protocol 2 与 LongMemEval-S 共用 dataplane 指标，同时保留文档级和会话级证据差异。LongMemEval-V2 接入公开 trajectory states 与 insert/query；BEAM 接入原生 batches/turns 和 probing questions；MemoryArena 接入原生子任务以及跨会话 add/wrap_user_prompt。

Fixture 只验证接口与确定性检索。V2 当前采用纯文本配置，拒绝图像查询。缺少 gold locator 时召回率为 null。解析 MemoryArena 任务不等于执行环境。答案与 rubric 不进入检索文档。

| 证据层 | 回执契约 |
| --- | --- |
| memory-dataplane | any/all-gold、宏平均/微平均召回率、父定位覆盖、预算、延迟 |
| systems-runtime | 计算配置、StorageProfile、placement、I/O 遥测 |
| LLM-agent-outcome | 生成与评分调用、答案准确率、环境成功率；默认 not-run |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

<!-- section:evidence -->
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

<!-- section:harness -->
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

<!-- section:quickstart -->
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

<!-- section:acceptance -->
## 有界本地验收

在仓库根目录使用 Python 3.10 或更新版本执行。无需下载模型或数据集，也不需要 provider key。进程树限时 3300 秒，为 60 分钟以内的退出清理留出余量。超时或失败会写入未完成回执并返回非零退出码，不会记为通过。

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

完整 campaign 必须独立使用 --mode full-research --full-research --benchmark NAME --dataset FILE 显式启用，输入为外部准备的原生数据，agent、环境和 judge 需另行配置。此命令仅测量检索，不会启动真实 agent，也不会自动授予 benchmark 验收。

<!-- section:invariants -->
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

<!-- section:boundary -->
## 证据边界

THM 当前已经支持较强的 deterministic/local retrieval 与 shadow control experiment，但不宣称：

- 普适提升最终回答质量；
- 存在对所有用户最优的 decay curve；
- 自动 T0–T3 movement 已经 production-ready；
- 自动 delete propagation 已经安全；
- retrieval metric 的提升必然带来 prompt-cache 或用户感知延迟收益；
- 被检索出来的 evidence 一定被宿主模型真正使用。

unit/invariant、retrieval benchmark、harness lifecycle 和 real task outcome 是四类不同证据，不能互相冒充。

<!-- section:documentation -->
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
