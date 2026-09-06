# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 许可证：[MIT](LICENSE)

THM 是面向 Hermes Agent 的本地优先四层记忆工具：T0 为会话快照中的原生 `MEMORY.md` / `USER.md`，T1 为按需主题 Markdown，T2 为受预算约束的历史会话检索，T3 为外部来源指针。

它把活跃度、有效性、任务相关性和显式固定分开：提及不等于 hit，检索不等于有用，写入也不等于使用事件。1.2 已实现 FTS5 稀疏召回、可选本地语义向量、RRF 融合、预算装载、零权重 `mention_observed`、多种衰减策略比较和只读 Hermes provider。

已完成的 LoCoMo **Protocol 2** 在 600 `cl100k_base` 证据 token、1,532 道完整可解析非对抗题上，any-gold coverage 为 **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**；all-gold 为 **46.61% / 56.53% / 40.01% / 57.64%**。这不是回答正确率。Protocol 2 已修正类别标签、按对话隔离 IDF，并增加 MRR、nDCG 与 p99。完整结果见 [Protocol 2 报告](reports/2026-09-06-recall-protocol2.md)。

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

安装后，THM 通过 Hermes 的 `hermes_agent.memory_providers` entry-point 暴露 `thm` provider。固定上游 E2E 已验证真实 Hermes discovery、MemoryProvider/MemoryManager 接入、prefetch、memory-context fencing、session switch，以及 `on_memory_write` 不会被计作 hit，也不会改写派生召回库。该 E2E 使用合成证据且零模型调用，不是回答生成 benchmark。详见 [Hermes E2E 报告](reports/2026-09-06-hermes-e2e.md)。

用户专属 decay 标定可用 `research/recall/decay_from_index.py` 从本地 THM v2 索引导出只包含 entry ID、单位成本和显式 hit 日期的私有时间序列；没有真实 hit 历史时，THM 不宣称存在用户专属最优半衰期或曲线。

THM 当前不宣称已证明真实用户端到端回答正确率、普适最优衰减曲线、自动换层/删除传播或用户感知延迟收益。`scan` 的 `mention_observed` 权重仍为零。

文档：[项目目录](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回 / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
