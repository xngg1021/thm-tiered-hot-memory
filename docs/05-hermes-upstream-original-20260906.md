# Hermes 上游研究：官方内存架构、同类 issue 与合并路径

读取日期：2026-09-06。证据来源：本地克隆的 NousResearch/hermes-agent（commit 9a84bee265daad14340a80d7585928cd8ea1f9eb，与[来源清单](related-work-sources.json)的 hermes pin 一致）、gh CLI 对官方仓库 issue 的检索快照（183 条合并去重）、官方文档站。issue 状态、优先级与维护者决策会随时间漂移，本文是快照，不是对维护者意图的推断。本文未运行官方代码、未复现任何 benchmark。

## 一、官方内存架构与 THM 层级对应

证据层级 D（官方文档）与 S（源码抽查，同一 pin）。逐层对应关系：

| THM 层 | 官方对应物 | 说明与证据 |
| --- | --- | --- |
| T0 热层 | memory 工具 + MEMORY.md / USER.md | 字符硬上限、会话开始注入 frozen snapshot、满时工具报错逼 agent 当场合并。官方文档明确 no auto-compact。文件 tools/memory_tool.py、tools/memory_tool_store.py；文档 user-guide/features/memory.md |
| T1 温层 | skills 机制 | 按主题拆分的 markdown 文件、按需加载，结构与温层文件等价。上游提交 562ee8ab76 明确把任务学到的知识导向 skills，memory 只留每会话必用的例外 |
| T2 冷层 | session_search 工具 | 查 state.db 的 FTS5 全文检索，无 LLM 调用 |
| T3 外部层 | 无指针层 | 官方以 8 个外部 memory provider 插件替代（honcho、openviking、mem0、hindsight、holographic、retaindb、byterover、supermemory），目录 plugins/memory/，同时只激活一个 |

官方额外拥有而 THM 没有的：每轮后台 self-improvement review（把重复纠正与工作流教训自动写回 memory 或 skill，带 write_approval 审核闸门）、/journey 学习时间线（可视化记忆与技能、手动剪枝）、会话压缩 compression.threshold。

官方明确没有的：使用反馈计数（memory_tool.py 中无 recall 或 hit 统计）、层级晋升降级、排程巩固（合并只在内存满时报错触发）。

同域先例（I）：holographic provider 自带 trust 评分、temporal_decay_half_life 配置与 fact_feedback 反馈工具。说明评分与衰减在官方 provider 层早有先例，内置 memory 层没有。

## 二、MemoryProvider ABC 钩子与 THM 层映射

证据 S，文件 agent/memory_provider.py（同一 pin）。独立插件实现 MemoryProvider 抽象基类后，THM 各层可一对一映射：

| THM 机制 | 官方钩子 | 说明 |
| --- | --- | --- |
| T1 温层注入 | prefetch | 每次 API 调用前执行，返回的召回文本注入上下文；queue_prefetch 在每轮后预取 |
| T0 写入挂钩 | on_memory_write | 内置记忆每次写入时镜像调用，可顺带记 hit |
| T2 会话落盘 | sync_turn / on_session_end | 每轮或会话结束持久化；sync_turn 必须非阻塞 |
| T2 压缩前归档 | on_pre_compress | v2 checkpoint 契约，压缩改写前落盘证据，可配 fail-closed 阻止未归档的丢失性改写 |
| 协议技能与命令 | register_skill / cli.py | 激活该 provider 时才加载的只读技能，以及 hermes <provider> 子命令 |

硬性契约：存储路径必须用 initialize 传入的 hermes_home（profile 隔离），is_available 不得联网，prefetch 必须快。

## 三、其他 harness 与框架

证据 D、M、P，概述级，未安装未复现。三个零件各自的成熟实现：

| 对象 | 相关能力与时间 |
| --- | --- |
| Claude Code | CLAUDE.md 三级层级；auto-memory 2026-02（v2.1.59）自动写回；Memory 2.0 Auto Dream 在会话间自动合并与剪枝；compaction 与 tool clearing |
| Codex | AGENTS.md 静态三级；Memories 后台把旧会话摘要写入 ~/.codex/memories/，agent 自管、用户不可手改 |
| Gemini CLI | save_memory 工具向 ~/.gemini/GEMINI.md 追加事实；/memory show/add/refresh |
| OpenCode | 内置只有 AGENTS.md；记忆靠社区插件（Letta 风格 memory blocks 插件、Hindsight） |
| MemGPT / Letta | 2023 年论文起的两层热交换鼻祖：main context 放可编辑 core memory blocks，external context 放 recall 与 archival 存储，模型经函数调用自行换入换出 |
| Mem0 | memory decay 按最近检索把得分在 0.3x 到 1.5x 间缩放；另有 eviction、矛盾取代、分层生命周期 |
| Zep / Graphiti | 时序知识图谱，边带时间有效性，失效不等同删除 |

结论（I）：分层记忆、热交换、使用反馈评分三个零件从 2023 年起分别产品化，组合形态没有原创性红利；THM 的可辩护差异只能落在驻留策略的证据选择效果、来源与恢复语义上，与[相关工作](04-related-work.md)的判断一致。

## 四、官方 issue 全景

gh CLI 检索快照（2026-09-06），按主题分组，只列与 THM 同类的条目：

分层记忆：32726（2026-05-26，四层存储替换平铺）、32198（2026-05-25，分层注入）、625（2026-03-07，置信门控时序记忆）、25456 与 59576（三层架构）、11144（已关，multi-tier fan-out）、11590（已关，MemGPT 加 BigMemory 协调插件）。

巩固与做梦：10771（2026-04-16，9 评论，Auto Dream）、25309（2026-05-14，9 评论，后台自动合并，innovation）、29431（同题插件提案）、5533（最早做梦提案）、60900 与 60902 与 60905（2026-07-08 三人同提 90% 容量软警告加自动合并）、103419（2026-09-05，P0，后台合并静默清空 USER.md）。

衰减与评分：678（2026-03-08，needs-decision，原子事实提取加遗忘）、103101（2026-09-04，生命周期管理）、99942（2026-09-01，时序感知层 RFC）、17899（holographic 检索计数从未递增的 bug）。

维护与治理：93623（2026-08-24，P2，needs-decision，去重维护工具）、96795（写治理失效）、103920（写路径护栏）、56817（分层写审批）、76883（变更可逆与本地归档）、86022（带理由的条目）、97316（批量合并回显整个 store 的性能问题）、76035（P2，幻觉满内存后破坏性合并）。

周边同类：31720（SQLite FTS5 加 Obsidian 记忆树）、103032（社区本地 RAG provider 提案）、84340（记忆文件放置契约）、44086（项目级 MEMORY.md）、11425 与 13534（skill 域使用追踪与陈旧检测）、77057（每工具使用智能）。

三个信号（I）：其一，三个主题的 issue 从 2026-03 到 2026-09 被反复提出，全部 P2/P3，多个挂着 needs-decision；其二，官方在 skills 域已有 Curator 巩固循环（现实功能），memory 域只有满时报错，不对称即切入点；其三，官方最怕自动合并出错（103419 P0、76035 P2），THM 的批量变更前先给用户过目这条红线正好是对冲设计。

## 五、贡献政策与两条路径

证据 D：CONTRIBUTING.md 与 PULL_REQUEST_TEMPLATE.md（同一 pin）。

bundled provider 通道已关闭：CONTRIBUTING 明文"We are no longer accepting new memory providers into this repo"，新 provider 一律发布独立插件仓库（pip entry point hermes_agent.memory_providers 或用户插件目录），享受全部生命周期钩子、setup 向导与 CLI 命令注册。

核心 PR 的硬性要求：Conventional Commits、关联既有 issue（Fixes #）、pytest 全绿、变更必须带测试、文档同步更新、跨平台（Windows 明确在列）、只含相关提交。贡献优先级排序：修 bug、跨平台、安全、性能、新技能、新工具、文档。

结论（I）：整套四层架构进官方树不现实，官方把记忆扩展外包给 provider 的意图明确。进主线的最可能形态是解决既有 issue 的小增量 PR，候选选题是 678 的 decay 子项或 10771、25309 的排程巩固子项；使用反馈统计是官方内置层确认缺失、issue 需求重叠、且 holographic 已有 provider 层先例的最小切入点。参与方式先评论后写码，实机的 index.json 事件流与 hit 统计是其他提案者拿不出的证据。

## 六、本仓库的行动结论

脱敏引擎 thm.py 已随 feat(engine) 提交进入本仓库（2026-09-06），公开层边界随之修订：引擎为脱敏副本，私有数据与运行实例仍在本机。后续候选：把引擎包成 MemoryProvider 适配层放入独立插件仓库；上游参与从订阅与评论 25309、678 开始。
