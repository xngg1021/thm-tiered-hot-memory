# THM 项目文档总目录

默认项目主页为英文 [README](../README.md)，并提供多语言版本。当前实现与验证入口以本页、实现状态和对应版本文档为准；历史研究、设计和报告保留原始证据边界，不把旧目标自动算成当前能力。

| 文档 / 证据 | 内容与口径 |
| --- | --- |
| [项目入口](../README.md) | 当前能力、实测结果与多语言切换 |
| [研究综述](01-研究综述.md) | 认知类比、公开研究、设计原则及限制 |
| [架构设计](02-架构设计.md) | THM **T0–T3** residency/access tiers 与历史设计规则 |
| [验证合同](03-validation-contract.md) | 更广泛验收目标；未自动晋升为运行能力 |
| [相关工作](04-related-work.md) | 有时间和来源边界的公开系统比较 |
| [Hermes 上游研究](05-hermes-upstream.md) | 接口语义、hit/写入边界、投稿范围 |
| [索引引擎指南](06-engine-guide.md) | 主文件、配置、迁移与恢复限制 |
| [当前实现状态](07-implementation-status.md) | 1.4 development 的已实现/已测/未自动化边界 |
| [测试与发布](08-testing-and-release.md) | 测试口径与发布纪律 |
| [1.2 召回与测量](09-retrieval-and-measurement.md) | 召回、预算、零权重观察、衰退与 Hermes provider E2E |
| [1.2 召回复核](10-recall-integration-review.md) | 召回、缓存、数据库与评测协议补修记录 |
| [1.3 Harness 适配](11-harness-adapters.md) | harness-neutral recall 与多 harness 边界 |
| [版本历史](12-version-history.md) | 精确 commit/archive 恢复地图与版本纪律 |
| [硬件类比审计](13-hardware-inspired-adaptive-residency.md) | miss、locator、prefetch、budget-control 的可迁移部分与禁区 |
| [1.4 Shadow Residency Control](14-residency-control-plane.md) | telemetry、T1 locator directory、value-aware T0 recommendation、co-demand prefetch、budget feedback |
| [1.4 Hermes T1 Directory](15-hermes-warm-directory.md) | opt-in、session-frozen、目标存在性校验的 locator-only prompt projection |
| [机器可读版本谱系](../versions/history.json) | 精确历史 SHA、archive refs 与 development boundaries |
| [LoCoMo / decay 实验协议](../research/recall/README.md) | 数据、分母、tokenizer、时序与 protocol 定义 |
| [Protocol 2 实测](../reports/2026-09-06-recall-protocol2.md) | LoCoMo retrieval 指标及边界 |
| [Hermes provider E2E](../reports/2026-09-06-hermes-e2e.md) | 固定 upstream 的真实 provider lifecycle 验证 |

## 当前可运行材料

- 索引维护：`scripts/thm.py`
- 召回核心：`thm/retrieval.py`
- Harness-neutral adapter：`thm/harness.py`
- Hermes base provider：`thm/hermes_plugin.py`
- **1.4 Hermes provider entrypoint：`thm/hermes_v14_plugin.py`**
- MCP v2 server：`thm/mcp_server.py`
- decay/activity policy：`thm/policy.py`
- **1.4 residency facade：`thm/residency.py`**
- **telemetry：`thm/residency_telemetry.py`**
- **T1 locator directory：`thm/residency_directory.py`**
- **shadow residency/prefetch/budget control：`thm/residency_control.py`**
- 兼容 telemetry research CLI：`research/residency/miss_telemetry.py`
- Protocol 2 benchmark：`research/recall/benchmark.py`
- 本地 decay trace 导出：`research/recall/decay_from_index.py`
- 版本历史检查：`scripts/check_version_history.py`
- 文档检查：`scripts/check_docs.py`
- 代表性测试：`tests/test_engine.py`、`tests/test_review_repairs.py`、`tests/test_harness_core.py`、`tests/test_residency_control.py`、`tests/test_residency_cli.py`、`tests/test_hermes_warm_directory.py`

## 当前证据边界

Protocol 2 和历史 Hermes E2E 已有远端运行证据。1.4 shadow control 以 unit/contract test 和 recommendation report 形式验收；Hermes T1 locator snapshot 另有 provider lifecycle/integration tests，但仍不等于真实任务收益 A/B。1.4 **没有**自动改变 T0–T3，也没有在缺少真实任务结果时宣称最优 residency/prefetch/budget policy。

真实用户 memory、私有 catalog、telemetry、显式 hit chronology 和其他未授权材料不进入公开仓库。用户专属 optimum 需要用户自己的留出任务与运行数据，不能用仓库里的 synthetic trace 代替。
