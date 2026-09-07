# THM 硬件类比审计：从脑暴到可测的自适应驻留策略

<!-- current-v1.4-status:start -->
> **Current release status — implemented in THM 1.4.0.** The hardware-analogy audit below is the design provenance for the accepted shadow miss/residency/prefetch/budget control surface. Stable code/content milestone: `e6e4dda5835e3cb345207457d5491131c6959b2c`; recovery pointer: `archive/v1.4.0-stable`. The implementation remains advisory: it does not silently move T0–T3 or mutate Hermes/T0 budgets, and production superiority still requires held-out runtime/task A/B evidence. See [14-residency-control-plane.md](14-residency-control-plane.md) and [15-hermes-warm-directory.md](15-hermes-warm-directory.md).
<!-- current-v1.4-status:end -->

> 2026-09-07
> 来源：本地模型旧版脑暴的七项硬件类比，经 THM 当前实现、Context Economics L4/L5、经典缓存研究与近期 prefetch 研究重新核对。
> 状态：**THM 1.4 已实现并完成 accepted/stable 工程验收；控制面保持 shadow/advisory，不自动修改 T0–T3、budget、activity、validity 或原生记忆。**

目标不是证明 agent memory 等于 CPU/OS cache，而是判断哪些硬件机制能转写成**可测、可失败、可回滚**的 THM 控制变量。

## 一、总裁决

| 脑暴项 | 裁决 | 处理 |
|---|---|---|
| 缺页率驱动容量规划 | **强保留** | 先建立 miss taxonomy 与 penalty telemetry，再谈自动调容量 |
| 拥塞控制式自适应注入 | **保留为实验** | 改名 feedback controller；影子建议，不直接类比 TCP |
| 温层目录注入 | **强保留** | deterministic derived projection；目录是 locator，不是 evidence |
| 写合并/写放大 | **部分保留** | 删除“memory write 必然打爆 prompt cache”的旧推论；保留 derived-state fanout/batching |
| 跨 profile COW | **条件保留** | 只用于 immutable shared artifacts/content-addressed blobs；默认不共享可变语义状态 |
| 期望损失最小化驱逐 | **最强保留** | 与 Context Economics L4/L5 的 expected net value / cost-per-success 对接 |
| 分支预测式注入 | **保留为实验** | 改称 speculative memory prefetch；量化 accuracy/coverage/pollution |

THM 1.4 已实现并冻结为 shadow/control surface 的组合：

```text
miss telemetry
    -> value-weighted residency
    -> compact warm directory
    -> bounded speculative prefetch
```

不应直接把 ARC、TCP、COW、SSD FTL 逐字翻译进 THM。

## 二、缺页率驱动容量规划：先定义“缺页”

THM 的使用事件不等于“缺了什么”。至少要区分：

```text
resident_hit
    本次任务需要的 item 已在 resident/injected set

resident_miss
    item 不在 resident set，但随后从 T1/T2/T3 或 external source 成功取回

hard_miss
    item 在 THM 可访问层也未取回，需要用户重述、重新推导或重新获取

planned_retrieval
    设计上本来就应按需取回，不算 miss

stale_resident_failure
    item 虽 resident，却因过期/作用域错误导致错误任务结果
```

THM 条目不是等长 page，所以不能只最小化 miss count。更合适的是：

```text
expected_miss_penalty
= Σ P(need_i | task_class)
    * P(miss_i | policy)
    * C_miss(i)
```

其中 `C_miss` 可拆成 extra tokens、tool calls、latency、provider cost、retry/failure impact。这与 Context Economics L5 的 `cost_per_success` / `reacquisition` 口径一致。

Denning 的 working-set model 支持“动态识别当前在用的信息集合”的思路，但它研究分页程序行为，不能直接标定 THM token 预算。

来源：Peter J. Denning, *The Working Set Model for Program Behavior*, CACM 1968, https://doi.org/10.1145/363095.363141

## 三、拥塞控制式注入：保留反馈控制，撤掉 TCP 等价

“context 压力高时减少注入、miss penalty 高时增加注入”方向成立，但更准确的名字是 **feedback-controlled injection budget**。

待实验控制量可写成：

```text
M_t = recent miss penalty / reacquisition pressure
P_t = context pressure / latency / token bill
R_t = prefetch pollution / stale-resident risk

B_(t+1) = clip(
    B_t
    + α * max(0, M_t - M_target)
    - β * max(0, P_t - P_target)
    - γ * R_t,
    B_min,
    B_max
)
```

自动控制前必须有最小样本量、EMA/window、hysteresis、固定上下界，并先以 shadow mode 输出建议。当前不接生产 residency。

## 四、温层目录注入：最便宜、最稳的一条

旧脑暴提出给 T0 放一行温层目录。这个方向非常适合 THM，但实现应是 **deterministic locator projection**，而不是把 T1 内容重新摘要成第二份“事实”。

建议目录字段：

```text
topic/key
scope
current item count
newest valid revision/time
locator
```

示例：

```text
db-config | project:A | 3 current | 2026-09-04 | warm/db-config.md
```

边界：目录不是 evidence；只能从 canonical index 派生；必须版本绑定；先测试 32/64/128/256 token 档，不预设固定最优预算。

价值是把 unknown-unknown 降成 known-locator，同时不把整个 warm content 常驻。这条可进入下一轮正式设计。

## 五、写放大/写合并：拆成 prompt cache 与 derived-state fanout

当前 Hermes built-in memory 在 session start 形成 frozen snapshot，普通 mid-session memory write 不会立即重建当前 system prompt。因此：

```text
memory write -> next turn entire conversation re-prefill
```

不能作为通用规律，这部分已在 `context-economics/L4-memory-profile.md` 勘误。

仍值得测的是软件层面的 `derived_write_fanout`。一个 logical memory change 可能更新 canonical entry、index、warm directory、embedding、derived summary、observation metadata、backup/checkpoint。

```text
derived_write_fanout
= durable/derived objects updated / logical memory changes
```

然后再决定哪些派生物同事务更新、异步重建、批量 coalesce，或允许从 canonical truth 重算。

SSD 文献只能提供“冷热分离、减少无意义重写”的启发，不能给 THM 参数。参考：Dayan, Bouganim, Bonnet, *Modelling and Managing SSD Write-amplification*, https://arxiv.org/abs/1504.00229

## 六、跨 profile COW：只对不可变共享对象有意义

可考虑共享：immutable public facts、common software docs、reference artifacts、content-addressed raw sources。

不应默认共享：user preference、profile-specific constraints、current judgments、private project state。

更安全的形式：

```text
shared immutable blob (content hash)
        ↑
profile A reference + own metadata
profile B reference + own metadata
```

语义修改产生新 blob / new revision，而不是多个 profile 原地共同写一个 memory entry。只有实际测出重复 immutable bytes/tokens 足够大时才值得实现。

## 七、期望损失最小化：最应该保留的核心

旧脑暴的：

```text
E[loss] = P(miss) * C(miss) + P(stale) * C(stale)
```

方向正确，可补成：

```text
expected_net_value(item)
=
  expected_task_value(item)
- resident_cost(item)
- expected_miss_penalty_if_absent(item)
- stale/error_risk_if_present(item)
- interference_cost(item)
```

整个 policy 则与 Context Economics L5 的 task economics 对接：task value 减 token/cache、reacquisition、retry/failure、latency、stale/interference loss。

未来 admission/eviction 不应只问“哪个 activation 低”，而要问“在当前 token budget 下，移除哪个 item 带来的 expected task loss 最小”。这能处理低频高代价、 高频 stale、长但便宜可重取、短但关键等不同条目。

## 八、分支预测式注入：改称 speculative memory prefetch

“预测下一话题，提前注入 locator/excerpt”可以测，但预测错会浪费预算并制造 context pollution。

建议指标：

```text
prefetch_accuracy = used_prefetch / issued_prefetch
prefetch_coverage = misses_avoided_by_prefetch / total_relevant_misses
prefetch_pollution = unused_prefetch_tokens + displaced useful capacity
net_prefetch_value = avoided_miss_penalty - prefetch_cost - pollution_cost
```

第一版只允许 locator-only 和 very-small-excerpt 两档。prefetch 不得自动变成 hit、增加 activity、续期或在低置信度时注入全文。

硬件 prefetch 研究同样需要权衡 latency benefit 与 cache pollution；2026 SmartScout 也显示激进错误路径 prefetch 会降低准确率并污染 I-cache：https://doi.org/10.1145/3797905.3815060

## 九、ARC 与 TinyLFU：能借什么，不能借什么

ARC 的核心不是机器学习，而是在线维护 recency/frequency 两类历史，并通过 ghost lists 自适应调节两者占比。可借 recency pool、frequency pool、ghost/history signal、online balance、scan resistance。

不能直接借 page 大小一致、hit ratio 作为唯一目标、访问语义统一、无 stale/authority/scope 等前提。来源：Megiddo & Modha, *ARC: A Self-Tuning, Low Overhead Replacement Cache*, FAST 2003, https://www.usenix.org/conference/fast-03/arc-self-tuning-low-overhead-replacement-cache

TinyLFU 更值得借的是 **admission 与 replacement 分开**：新条目出现时先比较新 candidate 与当前 eviction candidate 的价值，而不是默认塞进 T0 再淘汰。可借 recent frequency sketch、admission gate、recency window 与 stable-frequency main region；不能只按 frequency、等成本、忽略 miss penalty/stale risk/token length。来源：Einziger, Friedman, Manes, *TinyLFU: A Highly Efficient Cache Admission Policy*, https://arxiv.org/abs/1512.00727

更适合 THM 的组合是：

```text
candidate admission
    = value density + validity gate

resident replacement
    = recency/frequency dual signal
      + variable token cost
      + miss penalty
      + stale/interference risk
```

## 十、落地顺序

### Phase A — 只测，不控制

新增 shadow telemetry：`resident_hit`、`resident_miss`、`hard_miss`、`stale_resident_failure`、`prefetch`，统计 miss rate、hard miss rate、avoidable miss rate、miss penalty、prefetch accuracy 和 prefetch waste。

本仓新增 `research/residency/miss_telemetry.py`。它不写 THM index，不产生 hit/confirm，只聚合显式事件。

### Phase B — 温层目录

实现 deterministic warm locator projection，验收 directory token cost、locator hit rate、warm retrieval latency、wrong-locator rate。

### Phase C — shadow residency recommendation

只输出 recommended resident budget 与 admission/eviction candidates，不自动执行。

### Phase D — speculative prefetch

只在合成/回放任务中测试 locator-only 与 tiny-excerpt。

### Phase E — 自动控制

只有真实 trace 能证明 lower cost_per_success 或 higher success at same budget，才允许 feedback controller 改变注入预算。

## 十一、停止条件

以下任一项成立就不推进自动控制：miss 事件无法稳定标注；prefetch accuracy 低且 pollution 大；容量变化震荡；stale resident failure 上升；token 下降但 task-level cost/per-success 不改善；profile 隔离或 provenance 变弱；反馈只能靠模型自报“我用了这条记忆”。

## 十二、与当前 THM / Context Economics 的关系

当前 THM 已明确 `mention_observed` 权重为 0、display/retrieval/movement 不冒充 usage、validity/pinning 先于 activity、retrieval benchmark 与 answer accuracy 分开。因此本审计不推翻现有机制，而是在 activity 之上增加 miss/penalty telemetry，再为 value-aware residency、adaptive budget、prefetch 提供证据。

Context Economics 已提供 resident cost、reacquisition、retry、latency、failure、cost-per-success。两个项目最自然的接口是**指标和实验设计**，无需把 Family HF 或另一个通用 runtime 搬进 THM。

## 当前状态声明

本次新增 telemetry 只用于离线/影子测量：不修改 `scripts/thm.py` activity 公式；不改变 T0/T1/T2/T3；不自动 promote/demote；不把 prefetch/mention/retrieval 变成 hit；不声称 ARC/TinyLFU/TCP/SSD 机制已在 THM 上验证有效。
