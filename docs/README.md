# THM 项目文档总目录

当前新增能力见 [1.2 召回、观察与测量](09-retrieval-and-measurement.md)及[可复现实验协议](../research/recall/README.md)。原索引维护仍使用[主文件指南](06-engine-guide.md)和[1.1 实现状态](07-implementation-status.md)。历史研究、设计和审计分别保留，不把原设计的验收目标算成已部署功能。1.1.1 的跨日重试、配置与跨平台修正见[直接修复补充](../reports/2026-09-06-chat-followup.md)。

| 文档 | 内容与口径 |
| --- | --- |
| [项目入口](../README.md) | 当前 CLI 范围、运行与测试入口 |
| [研究综述](01-研究综述.md) | 认知类比、公开研究、设计原则及其限制 |
| [架构设计](02-架构设计.md) | T0-T3 和原 v1.0 规则，保留已知反例；当前落地情况见实现状态 |
| [验证合同](03-validation-contract.md) | 更广泛的验收目标；未自动晋升为运行能力 |
| [相关工作](04-related-work.md) | 有时间和来源边界的公开系统比较 |
| [研究来源清单](related-work-sources.json) | URL、固定提交、章节和未验证项 |
| [Hermes 上游研究修订](05-hermes-upstream.md) | 接口语义、hit 与写入的区分、投稿边界 |
| [主文件与迁移指南](06-engine-guide.md) | 全部命令、配置优先级、状态隔离、v1预览/应用与恢复限制 |
| [1.1 实现状态](07-implementation-status.md) | 已实现、已测、未集成、未部署逐项区分 |
| [测试与发布](08-testing-and-release.md) | 测试口径、完整文档检查及后续有限任务 |
| [1.2 召回与测量](09-retrieval-and-measurement.md) | 稀疏/语义召回、scan、曲线、provider和明确限制 |
| [1.2 召回扩展复核与性能补修](10-recall-integration-review.md) | 修复范围、真实历史 CI 结果、协议勘误、补丁验证与限制 |
| [LoCoMo 与曲线实验协议](../research/recall/README.md) | 数据来源、分母、tokenizer、时序和原报告适用范围 |
| [原上游研究历史稿](05-hermes-upstream-original-20260906.md) | 原字节保存；其中过强结论已由修订页限定 |
| [原学术复审与勘误](../reports/2026-09-06-学术工具复审.md) | 原报告全文及前置勘误，原始段落哈希持续检查 |
| [原文档勘误执行记录](../reports/2026-09-06-文档勘误验证.json) | 仅对应当时的文档与公式检查 |
| [旧公开脚本问题复现](../reports/2026-09-06-legacy-engine-probes.json) | 13 个诊断；CONFIRMED 代表发现问题 |
| [1.1 修复报告](../reports/2026-09-06-engine-hardening.md) | 前驱修复、测试与剩余限制 |
| [1.1 机器可读结果](../reports/2026-09-06-engine-hardening.json) | 前驱实际命令、版本、源码哈希和非验证项 |
| [1.1 原始单元测试日志](../reports/2026-09-06-engine-tests.txt) | 前驱实际本地测试输出 |
| [1.1 原始公式测试日志](../reports/2026-09-06-numeric-tests.txt) | 旧规范的十项回归输出 |
| [1.1.1 直接修复报告](../reports/2026-09-06-chat-followup.md) | 追加修复、兼容性变化和前驱 CI 失败记录 |
| [1.1.1 机器可读结果](../reports/2026-09-06-chat-followup.json) | 当前源码指纹、87 项测试与历史公式回归 |
| [1.1.1 原始单元测试日志](../reports/2026-09-06-chat-engine-tests.txt) | 当前 Linux 原始输出，不冒充跨平台运行 |
| [1.1.1 原始公式测试日志](../reports/2026-09-06-chat-numeric-tests.txt) | 当前执行的十项历史公式检查 |

可运行材料：[索引主脚本](../scripts/thm.py)、[直接实现测试](../tests/test_engine.py)、[1.1.1新增回归](../tests/test_chat_regressions.py)、[文档检查器](../scripts/check_docs.py)、[检查器测试](../tests/test_document_checks.py)、[原公式回归](../scripts/thm_numeric_audit.py)、[旧缺陷复现器](../scripts/reproduce_legacy_engine_findings.py)、[召回包](../thm/retrieval.py)、[新能力测试](../tests/test_recall_extension.py)。旧复现器必须输入其固定的旧引擎 blob，不能套用在修复后的源码上。

此目录涵盖仓库中的项目文档和本轮可公开交付。其他项目资料、个人记忆和未取得的私有交付 ZIP 不被包装为已上传内容，也不在这里复制。
