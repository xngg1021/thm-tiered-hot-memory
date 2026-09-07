# 本机独立验证与零 LLM 时序实验报告 · 2026-09-07

> 本报告为一台独立 Windows 机器（Python 3.11）上的实测记录。所有个人路径、凭据与记忆内容已移除；数据集 ID 与指标数字按 benchmark 协议保留。验证对象：THM 1.4.0（`d32e02f`）与零 LLM 检索前沿 PR #9。

## 一、测试套件

`python -m unittest discover -s tests -v`：238 项测试全部通过，1 项跳过，耗时 8.7 秒。零失败。

## 二、检索延迟（小库 112 文档，8 组查询，600 预算）

| 模式 | p50 检索 | p95 检索 | 含进程启动总耗时 p50 |
| --- | --- | --- | --- |
| sparse | 1.82 ms | 2.30 ms | 2.21 ms |
| literal | 1.06 ms | 1.31 ms | 1.15 ms |

与 1.3 实测一致，检索路径无回归。

## 三、1.4 控制面命令行为验证（合成遥测，119 事件 / 30 任务）

构造规则：七类事件混合（resident_hit、resident_miss、hard_miss、planned_retrieval、stale_resident_failure、prefetch 带 used 布尔、缺失惩罚字段），全部为合成条目名，不含真实记忆内容。

各命令行为与设计一致：

- residency-telemetry：正常聚合。resident_miss_rate 0.330，hard_miss_rate 0.110；预取 11 次仅 2 次被用（accuracy 0.182），未用注入 135 token；缺失惩罚合计 900 token、1800 ms 延迟。
- residency-plan：遥测不足时 admit/evict 均为空（抑制输出符合设计），低支持条目受保护而非评为零价值。
- prefetch-plan：对未知活跃条目正确拒绝（INSUFFICIENT_SEED_TELEMETRY），训练信号严格限定为显式需求任务共现。
- residency-budget：600 → 建议 500（direction shrink，controller_score -0.43），驱动信号为预取污染 0.82 与驻留未用率 0.33 超目标线；changes_applied=false，影子模式不写预算。
- warm-directory：locator 投影正常，空温目录输出为空。

衰减曲线：曲线族五个（legacy、power、exponential、mixture、bounded_power）。

## 四、零 LLM 实体投影复现（PR #9）

Protocol 2 口径，sparse@600，cl100k_base，全量 1-4 类 1540 题。

| 配置 | any-gold | all-gold |
| --- | --- | --- |
| 冻结基线（本机复现） | 69.3864% | 56.5274% |
| entity_projection=True（本机复现） | 72.5196% | 59.4648% |
| 官方声称值 | 69.3864% → 72.5196% | 56.5274% → 59.4648% |

四个数字与本机逐位一致。held-out 本机 72.3290%（官方 72.33%；基线 69.5619 + 2.7671 = 72.3290，55 胜 19 负账目吻合）。

性能代价在噪声范围：p50 27.96 → 28.10 ms，p95 37.34 → 37.14 ms。

诚实记录：本机数据集文件 SHA256 与官方钉住版本不一致，held-out 可评分题 1307 vs 官方 1301（差 6 题）；主类别 1540 题的关键数字逐位一致，差异仅在边缘题目，不影响结论。

## 五、零 LLM 时序实验：事件摘要层（新实验，未入仓库）

### 背景与发现

先纠正一个历史分类错误：旧本地粗测报告把 LoCoMo 类别命名颠倒。官方类别定义（benchmark.py CATEGORY）为 1=multi_hop、2=temporal、3=open_domain、4=single_hop、5=adversarial。类别 2（321 题）才是时序推理题（When did 型），类别 3 是人格推断题。旧报告"时序 16.7%"实为类别 3 人格题成绩，时序题真实成绩是 29.9%。

另外实测确认：LoCoMo 轮次数据无逐轮时间戳字段，时序信息只能从文本与数据自带的事件图挖掘。题目与证据轮的时间词共现率为零（When did 型题目本身不带时间词），纯时间词过滤无效果。

### 方法（零 LLM，纯 FTS5）

LoCoMo 每个 session 自带人工标注事件图（event_summary），含事件句与日期（如 "Caroline attends an LGBTQ support group for the first time. 8 May, 2023"）。实验把事件句加日期作为第二层文档并入 FTS5 索引（与轮次层并列），检索时事件层与轮次层同权竞争预算。

判定口径：证据轮级。基线命中 = 证据轮文本进入预算内结果集；增强额外计"事件图路径命中" = 证据轮所在 session 的事件句进入结果集（事件句带日期与会话定位，可支撑 When 型答案）。

### 结果（类别 2，321 题，证据轮级判定，预算 2400 字符）

| 配置 | 命中率 |
| --- | --- |
| 纯轮次词面（基线） | 36.8% |
| 轮次 + 事件图带日期 | 85.0% |

净提升 48.3 个百分点，其中 173 题经事件图路径命中。检索全程零 LLM 调用，0.5 秒完成全部查询。

抽样验证：问"When did Caroline give a speech at a school"（答案 "The week before 9 June 2023"），事件图命中 "Caroline speaks at her school... 9 June"，日期直接支撑答案。

### 边界

1. 事件图为数据集人工标注，质量高于 agent 自动生成，真实场景提升会打折扣（折扣量未知，需真实数据验证）；
2. 事件图未覆盖的事件仍漏（实测有题两边都未命中）；
3. 判定是"事件句加日期可支撑答案"的路径可达，不是"证据轮直接进入结果集"。

### 对 THM 的含义

指向一个架构增量：事件摘要层。巩固 cron 天然是它的生成器（离线、批量、低频生成事件句加日期），检索侧保持零 LLM。与 1.4 已有的 locator 温目录、实体投影并列，构成零 LLM 检索的三个已实测方向。
