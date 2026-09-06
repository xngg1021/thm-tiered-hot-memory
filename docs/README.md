# THM 项目文档总目录

默认项目主页为英文 [README](../README.md)，并提供简体中文、繁體中文、日本語、한국어、Español、Français、Deutsch 可切换版本。当前实现与验证入口以本页和 1.3 文档为准；历史研究、设计和旧报告继续保留原始证据边界，不把旧目标自动算成当前能力。

| 文档 / 证据 | 内容与口径 |
| --- | --- |
| [项目入口](../README.md) | 英文默认主页、当前能力、最新实测结果与多语言切换 |
| [研究综述](01-研究综述.md) | 认知类比、公开研究、设计原则及其限制 |
| [架构设计](02-架构设计.md) | T0-T3 和原 v1.0 规则，保留已知反例；当前落地情况见实现状态 |
| [验证合同](03-validation-contract.md) | 更广泛的验收目标；未自动晋升为运行能力 |
| [相关工作](04-related-work.md) | 有时间和来源边界的公开系统比较 |
| [研究来源清单](related-work-sources.json) | URL、固定提交、章节和未验证项 |
| [Hermes 上游研究修订](05-hermes-upstream.md) | 接口语义、hit 与写入的区分、投稿边界 |
| [主文件与迁移指南](06-engine-guide.md) | 命令、配置、状态隔离、迁移与恢复限制 |
| [1.1 实现状态](07-implementation-status.md) | 已实现、已测、未集成、未部署逐项区分 |
| [测试与发布](08-testing-and-release.md) | 测试口径与发布纪律 |
| [1.2 召回、scan、decay 与 Hermes 集成](09-retrieval-and-measurement.md) | 稀疏/语义召回、预算、零权重观察、衰退、真实 Hermes 生命周期 E2E 与真实 hit 标定入口 |
| [1.2 召回扩展复核与性能补修](10-recall-integration-review.md) | 召回、缓存、数据库安全与评测协议修复的施工记录 |
| [1.3 Harness 适配](11-harness-adapters.md) | harness-neutral recall、Hermes 完整 lifecycle、OpenAI Agents、LangChain/LangGraph、MCP v2、OpenClaw 及 Claude/Codex/Gemini MCP 边界 |
| [LoCoMo 与曲线实验协议](../research/recall/README.md) | 数据来源、分母、tokenizer、时序和 protocol 定义 |
| [Protocol 2 完整实测](../reports/2026-09-06-recall-protocol2.md) | 10 段 LoCoMo、1,986 题；600 token 主表、300/600/1200 sparse sweep、MRR/nDCG/p99 与边界 |
| [Protocol 2 机器可读摘要](../reports/2026-09-06-recall-protocol2-summary.json) | workflow、commit、artifact digest、dataset digest、模型身份与精确指标 |
| [历史 Hermes provider 生命周期 E2E](../reports/2026-09-06-hermes-e2e.md) | 固定旧 Hermes upstream 的 entry-point discovery、MemoryManager、prefetch、fencing、session switch 与 write≠hit 验证 |
| [Hermes E2E 机器可读记录](../reports/2026-09-06-hermes-e2e.json) | 历史固定 commit、workflow、artifact digest 和 PASS 项 |
| [原上游研究历史稿](05-hermes-upstream-original-20260906.md) | 原字节保存；其中过强结论已由修订页限定 |
| [原学术复审与勘误](../reports/2026-09-06-学术工具复审.md) | 原报告全文及前置勘误，原始段落哈希持续检查 |
| [原文档勘误执行记录](../reports/2026-09-06-文档勘误验证.json) | 仅对应当时的文档与公式检查 |
| [旧公开脚本问题复现](../reports/2026-09-06-legacy-engine-probes.json) | 13 个诊断；CONFIRMED 代表发现问题 |
| [1.1 修复报告](../reports/2026-09-06-engine-hardening.md) | 前驱修复、测试与剩余限制 |
| [1.1.1 直接修复报告](../reports/2026-09-06-chat-followup.md) | 跨日重试、配置与跨平台修正 |

## 当前可运行材料

- 索引维护：[scripts/thm.py](../scripts/thm.py)
- 召回核心：[thm/retrieval.py](../thm/retrieval.py)
- Harness-neutral adapter：[thm/harness.py](../thm/harness.py)
- Hermes provider：[thm/hermes_plugin.py](../thm/hermes_plugin.py)
- OpenAI Agents adapter：[thm/adapters/openai_agents.py](../thm/adapters/openai_agents.py)
- LangChain/LangGraph adapter：[thm/adapters/langchain.py](../thm/adapters/langchain.py)
- MCP v2 server：[thm/mcp_server.py](../thm/mcp_server.py)
- 多 Harness E2E：[research/harness_e2e.py](../research/harness_e2e.py)
- Hermes E2E：[research/hermes_e2e.py](../research/hermes_e2e.py)
- Protocol 2 benchmark：[research/recall/benchmark.py](../research/recall/benchmark.py)
- 合成 decay sweep：[research/recall/decay_replay.py](../research/recall/decay_replay.py)
- **真实用户本地 decay trace 导出**：[research/recall/decay_from_index.py](../research/recall/decay_from_index.py)。它只导出 entry ID、单位成本和显式 hit 日期，不上传记忆文本；真实 trace 应留在私有本地路径。
- 代表性回归测试：[tests/test_engine.py](../tests/test_engine.py)、[tests/test_review_repairs.py](../tests/test_review_repairs.py)、[tests/test_harness_core.py](../tests/test_harness_core.py)
- 文档检查：[scripts/check_docs.py](../scripts/check_docs.py)
- 历史公式回归：[scripts/thm_numeric_audit.py](../scripts/thm_numeric_audit.py)

Protocol 2 和历史 Hermes E2E 已有远端真实运行证据；1.3 的新 Hermes/multi-harness CI 以其各自精确 workflow/commit 结果为准。用户专属 decay 最优参数仍需要用户本机真实显式 hit 时间序列，不能用仓库里的合成轨迹代替。真实用户记忆、私有索引、其他项目内部资料和未授权私有材料不进入本公开仓库。
