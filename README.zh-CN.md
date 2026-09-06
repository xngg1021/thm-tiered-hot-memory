# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 许可证：[MIT](LICENSE) · 当前稳定版：**1.3.0**

THM 是面向 agent harness 的本地优先四层记忆工具：T0 为宿主永久上下文，T1 为按需主题资料，T2 为固定证据预算内检索的历史，T3 为可重新访问的外部来源。提及不等于 hit，检索不等于有用，写入也不等于使用事件。

## 1.3 已实现

1.1.1 提供加固索引 CLI；1.2 加入 scoped FTS5、可选本地向量、RRF、预算装载、衰减比较与可复现实验；**1.3 加入 harness-neutral 只读召回层**：Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2 stdio，以及 OpenClaw 2026.9.x 的独立 legacy MCP 桥。Claude Code、Codex CLI 和 Gemini CLI 均由固定版本真实 CLI 配置及同一服务命令 lifecycle E2E 验证。

原生来源记忆不会被 recall 或 scan 改写；派生 SQLite 在建表前拒绝无关或原生数据库目标；harness 集成不额外调用模型。

## 测量结果

LoCoMo Protocol 2 覆盖 10 段对话、1,986 道题，主口径为 1,532 道完整解析非对抗题。600 个 `cl100k_base` 证据 token 下，any-gold coverage 为 **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**，all-gold 为 **46.61% / 56.53% / 40.01% / 57.64%**。这是证据召回指标，不是回答正确率。详见 [Protocol 2](reports/2026-09-06-recall-protocol2.md)。

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

可选依赖：`.[tokenizer,semantic]`、`.[openai]`、`.[langchain]`、`.[mcp]`、`.[harnesses]`。OpenClaw 使用 `thm-mcp-legacy`。

1.3.0 accepted/stable 只由指向已通过 correctness、Hermes 与 harness 全矩阵的精确 Git SHA 的正式版本引用确认。THM 当前不宣称真实用户端到端回答正确率、普适最优衰减曲线、自动换层或删除传播、prompt-cache 收益或用户感知延迟改善。

文档：[项目目录](docs/README.md) · [Harness 适配](docs/11-harness-adapters.md) · [版本历史](docs/12-version-history.md) · [更新日志](CHANGELOG.md)
