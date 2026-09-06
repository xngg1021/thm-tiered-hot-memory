# THM — Tiered Hot Memory

[English](README.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi（SJF，xngg1021）· 许可证：[MIT](LICENSE)

THM 是面向 agent harness 的本地优先四层记忆工具。它从 Hermes Agent 起步，现已将检索逻辑与 harness 接线分离：判断哪些内容值得进入永久上下文，在固定预算内加载较冷的证据，并在不伪造“使用”信号的前提下测量这些决策。

## 四个层级

- **T0——热层：**由宿主注入的原生永久上下文记忆。
- **T1——温层：**按需加载的主题材料。
- **T2——冷层：**在明确证据预算内检索的历史会话和档案。
- **T3——外部层：**需要时可重新访问的来源位置和引用。

THM 将活跃度、有效性、任务相关性与显式固定分开。提及不等于 hit，检索不证明有用，写入也不等于使用事件。

## 已实现内容

加固后的 1.1.1 索引 CLI 维护 profile 绑定的记忆元数据、精确事件身份、迁移预览、pin/unpin 语义和故障安全写入。1.2 检索包加入按 scope 隔离的 FTS5、可选本地句向量、倒数排名融合、计入预算的上下文装载、零权重 mention observation、多种衰减策略比较及可复现实验脚本。

**THM 1.3 加入 harness-neutral 只读召回层。**它提供独立 Hermes `MemoryProvider`、OpenAI Agents SDK `FunctionTool`、LangChain/LangGraph `BaseRetriever` 和标准 MCP v2 stdio 服务。OpenClaw 2026.9.x、Claude Code、Codex CLI 与 Gemini CLI 通过独立的只读 MCP 兼容桥验证，因此不会为了旧一代客户端削弱 MCP v2 主服务契约。参见 [Harness 适配](docs/11-harness-adapters.md)。

检索或 scan 不会改写原生来源记忆。Harness 适配器以只读方式打开派生 THM 召回数据库，除非显式启用了宿主专属 live-session cache 刷新。派生 SQLite 数据库会在创建 THM 表之前拒绝无关或原生数据库目标。

## 召回测量证据

完整 **Protocol 2** LoCoMo 实验覆盖全部 10 段对话和 1,986 道题。主分母包含 1,532 道证据完全解析的非对抗问题。在固定 600 个 `cl100k_base` 证据 token 下，any-gold coverage 为 **literal 56.79%、sparse 69.39%、MiniLM dense 51.11%、hybrid 71.34%**；all-gold coverage 分别为 **46.61% / 56.53% / 40.01% / 57.64%**。这些是证据检索指标，不是回答正确率，也不是竞品排行榜。

Protocol 2 修正了 LoCoMo 类别映射，每段对话使用独立 FTS 数据库，避免 BM25/IDF 统计跨对话泄漏，并报告 MRR、nDCG 和 p99。在 600 token 下，sparse 的 p95 检索加装载延迟为 **34.55 ms**，hybrid 为 **57.88 ms**。本工作负载中 hybrid 的 any-gold 比 sparse 高 **1.96 个百分点**，这是实测权衡，不是普适默认建议。完整证据：[Protocol 2 报告](reports/2026-09-06-recall-protocol2.md) · [机器可读摘要](reports/2026-09-06-recall-protocol2-summary.json)。

Sparse 预算扫描在 300 / 600 / 1200 证据 token 下的 any-gold coverage 为 **60.57% / 69.39% / 76.17%**，p95 检索加装载延迟为 **20.39 / 34.55 / 61.78 ms**。

## Harness 集成界面

| 界面 | THM 1.3 集成 |
| --- | --- |
| Hermes Agent | 通过 pip 发现的独立 `MemoryProvider`；覆盖 setup schema/config、当前查询预取、可选派生 `sync_turn`、session boundary hooks 与 write≠hit |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool`——单个只读 `FunctionTool` |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp` / `python -m thm.mcp_server`，公开有类型的 `thm_recall` 与 `thm_status` 结构化输出 |
| OpenClaw 2026.9.x | `thm-mcp-legacy` / `python -m thm.mcp_legacy_server`；真实 OpenClaw MCP probe，使用同一只读召回核心 |
| Claude Code / Codex CLI / Gemini CLI | 固定版本真实 CLI 配置，通过只读兼容桥完成精确命令的 tool discovery/call lifecycle；零模型调用 |

早期针对 `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` 的 Hermes E2E 仍作为历史证据。THM 1.3 CI 还检查经审阅的当前 Hermes 快照和新增多 harness 界面；应查看精确 commit 对应的 workflow/report，不能把旧结果转移到新代码。

## 安装与运行

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

可选依赖按用途拆分：

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP 示例：

```bash
# MCP v2 主服务
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600

# 固定 OpenClaw/CLI 客户端代际使用的兼容桥
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Hermes 生命周期行为

Hermes setup 可将 THM scope/mode/budget 及可选 live-turn synchronization 保存到 profile 隔离的私有配置中。`sync_turns` 默认关闭。为 primary agent 显式启用后，THM 会把 user/assistant transcript 文本协调进单独的派生 per-session T2 scope；system rows 和标记的压缩摘要不会复制。`on_memory_write` 仍只是刷新信号，绝不是 hit。THM 有意停留在 Hermes best-effort pre-compress API v1，因为派生 live cache 不是 canonical transcript owner，无法诚实承诺 fail-closed checkpoint-v2 durability。

## 衰减标定

合成 decay sweep 只用于诊断。真实用户标定可用 `research/recall/decay_from_index.py` 导出隐私最小化时间序列，其中仅含 entry ID、单位成本和显式 `hit` 日期，不包含记忆文本、摘要、key 或 confirmation evidence；随后可用 `decay_replay.py` 私下回放。没有真实按时间排序的 hit trace 时，THM 不宣称存在用户专属最优半衰期或曲线。

## 证据边界

THM 当前不宣称真实用户端到端回答正确率、普适最优衰减曲线、自动换层、自动删除传播或 prompt-cache／用户感知延迟改善。`scan` 记录的是活动权重为零的弱 `mention_observed` 证据。Harness 集成刻意不进行第二次模型调用：召回覆盖、宿主接线、模型是否使用证据以及最终回答质量是四个独立证据层。

常规 correctness CI 在 Linux、macOS 和 Windows 上运行。重型 LoCoMo／模型下载与 harness 集成任务相互独立。文档：[项目目录](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回／scan／decay](docs/09-retrieval-and-measurement.md) · [Harness 适配](docs/11-harness-adapters.md) · [版本历史](docs/12-version-history.md) · [更新日志](CHANGELOG.md) · [benchmark protocol](research/recall/README.md)。

相关项目：[hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills)。

Version identity: **1.3.0 accepted/stable**.
