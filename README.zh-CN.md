# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 许可证：[MIT](LICENSE)

THM 是面向 Hermes Agent 的本地优先四层记忆工具。它聚焦一个有限问题：哪些内容值得永久占用上下文，哪些应按需加载，历史材料如何在固定预算内召回，以及怎样测量这些决策而不伪造“使用”信号。

## 四层结构

- **T0 热层：** 会话开始时注入快照的原生 `MEMORY.md` / `USER.md`。
- **T1 温层：** 按主题组织、按需读取的 Markdown。
- **T2 冷层：** 在明确证据预算内检索的历史会话与档案。
- **T3 外部层：** 需要时重新访问的来源位置与引用。

THM 将活跃度、有效性、当前任务相关性和显式固定分开处理。提及不等于 hit，检索不等于有用，写入也不等于使用事件。

## 已实现

1.1.1 索引 CLI 提供 profile 绑定索引、严格事件身份、迁移预览、pin/unpin 和失败保护写入。1.2 包增加了 FTS5 分范围召回、可选本地句向量、RRF 融合、预算计量的上下文装载、零权重 `mention_observed`、多种衰减策略比较、只读 Hermes provider 适配器以及可复现实验脚本。

召回与 scan 路径不会改写原生记忆文件或 Hermes `state.db`。派生 SQLite 数据库在创建 THM 表之前会拒绝无关或原生数据库目标。

## 已测证据

历史 protocol 1 的 LoCoMo 实验覆盖 10 段对话、1,986 道题。在 600 个 `cl100k_base` 证据 token、1,532 道完整可解析非对抗题的主分母上，任一证据命中率为：**literal 56.85%**、**sparse 69.58%**、**MiniLM dense 51.11%**、**hybrid 70.04%**。这些是证据召回指标，不是回答正确率，也不是竞品排行榜。

Protocol 2 修正类别标签、按对话隔离 FTS5 IDF，并增加 MRR、nDCG 和 p99。完整 protocol 2 由仓库 benchmark workflow 独立执行；历史 protocol 1 数字只保留作旧版本证据。

普通 correctness CI 覆盖 Linux、macOS 和 Windows。LoCoMo 与模型下载属于显式重型实验，不会在普通索引维护中自动执行。

## 安装与运行

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

可选 tokenizer / semantic 依赖：

```bash
python -m pip install -e '.[tokenizer,semantic]'
```

安装后，THM 通过 Hermes 的 `hermes_agent.memory_providers` entry-point 暴露 `thm` provider。固定上游版本的集成 workflow 会验证真实 Hermes checkout 中的发现与 provider 生命周期；使用时应以对应提交的实际 CI 为准。

## 证据边界

THM 当前**不**宣称已经证明真实用户端到端回答正确率、存在普适最优衰减曲线、能够自动换层或自动传播删除，也不宣称已证明 prompt-cache 或用户感知延迟收益。`scan` 只记录零活跃度权重的弱 `mention_observed`。用户专属衰减标定必须使用真实的时间序列使用记录；不会用合成轨迹冒充。

文档：[项目目录](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回 / scan / 衰减](docs/09-retrieval-and-measurement.md) · [集成复核](docs/10-recall-integration-review.md) · [benchmark 协议](research/recall/README.md)

相关项目：[hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills)。