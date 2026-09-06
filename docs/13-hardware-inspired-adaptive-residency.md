# THM 硬件类比审计：从脑暴到可测的自适应驻留策略

> 2026-09-07  
> 来源：本地模型旧版脑暴的七项硬件类比，经 THM 当前实现、Context Economics L4/L5、经典缓存研究与近期 prefetch 研究重新核对。  
> 状态：**研究/影子测量扩展；不改变当前 THM 1.1.1 residency、activity、validity 或索引写入语义。**

这份文档的目标不是证明“agent memory 等于 CPU/OS cache”，而是判断哪些硬件机制可以转写成
**可测、可失败、可回滚**的 THM 控制变量。

---

## 一、总裁决

| 脑暴项 | 裁决 | 处理 |
|---|---|---|
| 1. 缺页率驱动容量规划 | **强保留** | 先建立 miss taxonomy 与 penalty telemetry，再谈自动调容量 |
| 2. 拥塞控制式自适应注入 | **保留为实验** | 改名 feedback controller；影子建议，不直接类比 TCP |
| 3. 温层目录注入 | **强保留** | 做 deterministic derived projection；目录是 locator，不是 evidence |
| 4. 写合并/写放大 | **部分保留** | 删除“memory write 必然打爆 prompt cache”的旧推论；保留 derived-state fanout/batching |
| 5. 跨 profile COW | **条件保留** | 只用于 immutable shared artifacts/content-addressed blobs；默认不共享可变语义状态 |
| 6. 期望损失最小化驱逐 | **最强保留** | 与 Context Economics L4/L5 的 expected net value / cost-per-success 直接接轨 |
| 7. 分支预测式注入 | **保留为实验** | 改称 speculative memory prefetch；必须量化 accuracy/coverage/pollution |

最值得进入下一阶段的组合是：

```text
miss telemetry
    -> value-weighted residency
    -> compact warm directory
    -> bounded speculative prefetch
```

而不是直接把 ARC、TCP、COW、SSD FTL 逐字翻译进 THM。

---

## 二、第一条：缺页率驱动容量规划 —— 有用，但先定义“缺页”

旧脑暴最有价值的点，是指出 THM 目前的使用事件不等于“缺了什么”。

在 THM 里，必须先区分：

```text
resident_hit
    本次任务需要的 item 已在 resident/injected set 中

resident_miss
    本次任务需要的 item 不在 resident set，
    但随后从 T1/T2/T3 / external source 成功取回

hard_miss
    需要的 item 在 THM 可访问层也没有取回，
    需要用户重述、重新推导或外部重新获取

planned_retrieval
    设计上本来就应该按需取回，不应算 miss

stale_resident_failure
    item 虽然 resident，却因过期/作用域错误导致错误任务结果
```

这比单纯 `hit count` 更接近 OS/cache 中真正有决策价值的“未命中代价”。

### 为什么不能只优化 miss rate

THM 条目并非等长 page：

- 一个 12-token 的高价值禁令；
- 一个 300-token 的项目说明；
- 一个罕见但事故级的恢复事实；

它们的 residency 成本和 miss penalty 完全不同。

所以最终应优化：

```text
expected_miss_penalty
= Σ P(need_i | task_class)
    * P(miss_i | policy)
    * C_miss(i)
```

而不是：

```text
minimize miss_count
```

`C_miss(i)` 可以拆成：

```text
extra_tokens
extra_tool_calls
extra_latency
extra_provider_cost
retry/failure impact
```

这与 Context Economics L5 的 `cost_per_success` / `reacquisition` 口径一致。

### 理论边界

Denning 的 working-set model 支持“动态识别当前在用的信息集合”这一思路，但它研究的是分页程序行为；
不能据此推导 THM 的具体 token 预算或阈值。

参考：

- Peter J. Denning, *The Working Set Model for Program Behavior*, CACM 1968  
  https://doi.org/10.1145/363095.363141

---

## 三、第二条：拥塞控制式注入 —— 方向有用，TCP 只是类比

旧脑暴提出：

> context 接近阈值时减少注入，context 较短时增加注入。

这个方向成立，但更准确的名字是：

**feedback-controlled injection budget**

而不是 TCP congestion control。

TCP 的窗口是网络拥塞反馈；THM 的控制量至少有三种：

```text
M_t = recent miss penalty / reacquisition pressure
P_t = context pressure / latency / token bill
R_t = prefetch pollution / stale-resident risk
```

一个待实验的控制器可以写成：

```text
B_(t+1) =
clip(
    B_t
    + α * max(0, M_t - M_target)
    - β * max(0, P_t - P_target)
    - γ * R_t,
    B_min,
    B_max
)
```

其中 `B_t` 是本轮允许的 resident + prefetch token budget。

### 进入自动控制前的硬门槛

至少要求：

1. 有最小样本量；
2. 指标来自真实任务/读取 telemetry，而不是模型自报；
3. 使用 EMA / window，避免单次 miss 让预算震荡；
4. 有 hysteresis；
5. 有固定 `B_min/B_max`；
6. 先 shadow mode 输出建议，不能直接改 resident set。

因此，这条**值得实现控制器模拟器，但当前还不值得接生产 residency**。

---

## 四、第三条：温层目录注入 —— 这份脑暴里最便宜、最稳的一条

旧脑暴提出给 T0 放一个温层目录，例如：

```text
数据库配置 -> warm/db.md
家庭设备 -> warm/devices.md
```

这个方向非常适合 THM。

更准确的实现不是“把 T1 内容压成 T0 摘要”，而是生成一个
**deterministic locator projection**：

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

### 目录必须遵守四条边界

1. **不是 evidence**：目录只告诉 agent “哪里可能有东西”；
2. **不能自创语义**：只从 canonical index 派生；
3. **版本绑定**：源条目改动后目录 revision 一起变化；
4. **预算很小**：先测试 32/64/128/256 token 档，不预设“几十 token 一定最优”。

它的价值是把：

```text
unknown unknown
```

降成：

```text
known locator
```

同时避免把整个 warm content 常驻。

这条可以进入下一轮正式设计。

---

## 五、第四条：写放大/写合并 —— 旧结论要拆成两件事

### 1. prompt-cache 断点：旧类比已不成立

当前 Hermes 的 built-in memory 在 session start 形成 frozen snapshot。
普通 mid-session memory write 不会立即重建当前 system prompt。

因此：

```text
memory write
 -> next turn entire conversation re-prefill
```

不能作为通用规律。

这部分已经在 `context-economics/L4-memory-profile.md` 勘误。

### 2. derived-state fanout：仍然值得测

一个 logical memory change 可能触发：

```text
canonical entry
index
warm directory
embedding
derived summary
observation metadata
backup/checkpoint
```

这里确实存在一种软件层面的“写放大”，但应叫：

```text
derived_write_fanout
```

而不是 SSD WAF。

可记录：

```text
derived_write_fanout
= durable/derived objects updated
  / logical memory changes
```

然后决定哪些派生物：

- 同事务更新；
- 异步重建；
- 批量 coalesce；
- 可从 canonical truth 重算。

SSD 文献可以提供“冷热分离、减少无意义重写”的工程启发，但不提供 THM 参数。

参考：

- Dayan, Bouganim, Bonnet, *Modelling and Managing SSD Write-amplification*, 2015  
  https://arxiv.org/abs/1504.00229

---

## 六、第五条：跨 profile COW —— 能做，但不是当前高收益项

旧脑暴里的 Copy-on-Write 思路：

```text
公共页共享
profile 差异页私有
写时复制
```

只有在下列对象上值得考虑：

```text
immutable public facts
shared software docs
common reference artifacts
content-addressed raw sources
```

不适合默认共享：

```text
user preference
profile-specific constraints
current judgments
private project state
```

### 更安全的形式

不是多个 profile 指向同一“可写 memory entry”，而是：

```text
shared immutable blob (content hash)
        ↑
profile A reference + own metadata
profile B reference + own metadata
```

任何语义修改：

```text
new blob / new revision
```

而非原地共同修改。

### 何时才值得做

只有实际测出：

```text
duplicate immutable bytes/tokens
```

足够大，且共享能显著降低存储/注入/维护成本时再实现。

当前 THM 的更重要目标仍是 retrieval quality、miss penalty 和作用域正确性。

---

## 七、第六条：期望损失最小化 —— 这是最应该保留的核心

旧脑暴写：

```text
E[loss] = P(miss) * C(miss) + P(stale) * C(stale)
```

方向非常正确，而且现在可以进一步补全成：

```text
expected_net_value(item)
=
  expected_task_value(item)
- resident_cost(item)
- expected_miss_penalty_if_absent(item)
- stale/error_risk_if_present(item)
- interference_cost(item)
```

对整个 policy：

```text
J(policy)
=
  task_value
- token/cache cost
- retrieval/reacquisition cost
- retry/failure cost
- latency
- stale/interference loss
```

这已经与 `context-economics` 当前：

- L4 `expected_net_value(item)`
- L5 `cost_per_success`

完全对接。

### 对 THM 的具体意义

未来 admission/eviction 不应只问：

```text
哪个 activation 低？
```

而要问：

```text
在当前 token budget 下，
移除哪个 item 带来的 expected task loss 最小？
```

这可以自然处理：

- 很少用但缺一次代价极高的 item；
- 经常出现但已经 stale 的 item；
- token 很长但可便宜重取的 item；
- 很短但关键的约束项。

这是七条里**最值得最终进入正式 residency policy**的一条。

---

## 八、第七条：分支预测式注入 —— 改称 speculative memory prefetch

“预测下一话题，提前注入一条 locator/excerpt”是可测的。

它与 CPU prefetch 的共同边界是：

```text
预测错
 -> 浪费带宽/预算
 -> cache/context pollution
```

近期硬件 prefetch 研究仍然显示：prefetch accuracy 下降会导致明显 pollution；
因此 THM 也不能只看“猜中时省了一次检索”。

建议四个指标：

```text
prefetch_accuracy
= used_prefetch / issued_prefetch

prefetch_coverage
= misses_avoided_by_prefetch / total_relevant_misses

prefetch_pollution
= unused_prefetch_tokens
  + useful resident capacity displaced

net_prefetch_value
= avoided_miss_penalty - prefetch_cost - pollution_cost
```

### 第一版只允许两类 speculative payload

1. **locator-only**：最安全；
2. **very small excerpt**：有严格 budget。

不得：

- 自动把 prefetch 记为 `hit`；
- 自动增加 activity；
- 因 prefetch 被展示就续期；
- 在低置信度时大量塞全文。

参考：

- 经典 prefetch 文献长期强调 latency benefit 与 cache pollution 的权衡；
- 2026 SmartScout 的结果也直接显示更激进的错误路径 prefetch 会降低准确率并污染 I-cache。  
  https://doi.org/10.1145/3797905.3815060

---

## 九、ARC 与 TinyLFU：能借什么，不能借什么

### ARC

ARC 的核心不是“机器学习”，而是在线维护 recency/frequency 两类历史，
并通过 ghost lists 自适应调节二者占比。

可以借：

```text
recency pool
frequency pool
ghost/history signal
online balance
scan resistance
```

不能直接借：

- page 大小一致；
- hit ratio 是唯一主要目标；
- 每次访问语义相同；
- stale/authority/scope 不存在。

来源：

- Megiddo & Modha, *ARC: A Self-Tuning, Low Overhead Replacement Cache*, FAST 2003  
  https://www.usenix.org/conference/fast-03/arc-self-tuning-low-overhead-replacement-cache

### TinyLFU / W-TinyLFU

TinyLFU 更值得 THM 借的是：

> **admission 与 replacement 分开。**

即新条目出现时，不是默认塞入 T0 再想办法淘汰，而先问：

```text
new candidate value
vs
current eviction candidate value
```

可以借：

- recent frequency sketch；
- admission gate；
- window for recency；
- main region for stable frequency。

不能直接照搬：

- 只按 frequency 决策；
- 把所有 item 当等成本；
- 无视 miss penalty / stale risk / token length。

来源：

- Einziger, Friedman, Manes, *TinyLFU: A Highly Efficient Cache Admission Policy*  
  https://arxiv.org/abs/1512.00727

### 最适合 THM 的合成方向

未来真正值得测试的不是“THM-ARC”或“THM-TinyLFU”品牌化版本，而是：

```text
candidate admission
    = value density + validity gate

resident replacement
    = recency/frequency dual signal
      + variable token cost
      + miss penalty
      + stale/interference risk
```

---

## 十、落地顺序

### Phase A — 只测，不控制

新增 shadow telemetry：

```text
resident_hit
resident_miss
hard_miss
stale_resident_failure
prefetch
```

并统计：

```text
miss rate
hard miss rate
avoidable miss rate
miss penalty
prefetch accuracy
prefetch waste
```

本仓新增：

```text
research/residency/miss_telemetry.py
```

它不写 THM index，不产生 `hit`/`confirm`，只聚合显式事件。

### Phase B — 温层目录

先做 deterministic warm locator projection。

验收：

```text
directory token cost
locator hit rate
warm retrieval latency
wrong-locator rate
```

### Phase C — shadow residency recommendation

只输出：

```text
recommended resident budget
recommended admission/eviction candidates
```

不自动执行。

### Phase D — speculative prefetch

只在合成/回放任务中测试 locator-only 与 tiny-excerpt 两档。

### Phase E — 自动控制

只有当真实 trace 能证明：

```text
lower cost_per_success
or
higher success at same budget
```

才允许 feedback controller 改变注入预算。

---

## 十一、停止条件

以下任何一项成立，就不应把硬件类比继续推进成自动控制：

- miss 事件无法稳定标注；
- prefetch accuracy 不足且 pollution 大；
- 自动容量变化导致频繁震荡；
- stale resident failure 上升；
- token 下降但 task-level cost/per-success 没改善；
- profile 隔离或 provenance 变弱；
- controller 只能通过模型自报“我用了这条记忆”获得反馈。

---

## 十二、与当前 THM / Context Economics 的关系

当前 THM 已经明确：

- `mention_observed` 权重为 0；
- display/retrieval/movement 不冒充 usage；
- validity/pinning 先于 activity；
- retrieval benchmark 与 answer accuracy 分开。

因此这份硬件类比审计**不需要推翻当前机制**。

它补的是下一层：

```text
activity
    ↓
miss / penalty telemetry
    ↓
value-aware residency
    ↓
adaptive budget / prefetch
```

Context Economics 已经提供另一半：

```text
resident_cost
reacquisition
retry
latency
failure
cost_per_success
```

所以两项目之间最自然的接口是**指标和实验设计**，无需把 Family HF 或另一个通用 runtime 搬进 THM。

---

## 当前状态声明

本次新增的 telemetry 只用于离线/影子测量：

- 不修改 `scripts/thm.py` 的 activity 公式；
- 不改变 T0/T1/T2/T3；
- 不自动 promote/demote；
- 不把 prefetch/mention/retrieval 变成 hit；
- 不声称 ARC/TinyLFU/TCP/SSD 机制已在 THM 上验证有效。

只有真实任务数据达到 Phase E 门槛后，才讨论自动控制。
