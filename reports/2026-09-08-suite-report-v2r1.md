# THM × Context Economics 本地实机基准报告

> 证据边界：检索指标为 runtime-measured；成本为 model-proxy，非真实账单；检索证据覆盖不等于答案正确率或任务成功。

## 1. LoCoMo Protocol 2 检索全矩阵

- 主类别 1–4：每个配置尝试 1540 题，其中 1532 题进入主评分分母。
- 数据集 pin：True；counter：cl100k_base
- generation_calls=0；judge_calls=0

| 模式 | 300 | 600 | 1200 |
|---|---|---|---|
| literal | 0.4778 | 0.5679 | 0.6436 |
| sparse | 0.6057 | 0.6939 | 0.7617 |
| dense | 0.3982 | 0.5111 | 0.6123 |
| hybrid | 0.5894 | 0.7134 | 0.8087 |

hybrid@600 = 71.34% any-gold；数值上与仓库固定 reference 71.34% 相同；hybrid@1200 = 80.87% any-gold。数值相同不单独构成完整协议复现证明；这些也都是 evidence coverage，不是 answer accuracy。

## 2. LongMemEval-S 检索覆盖

- 实例数：artifact-defined；gold 为官方 answer_session_ids。
- 命中定义是 session-level：gold session 中至少一条消息进入 packed context。
- 该口径比 LoCoMo turn-level evidence 粗，绝对分数不可横向比较。

| 模式 | 300 | 600 | 1200 |
|---|---|---|---|
| literal | 0.8800 | 0.9380 | 0.9460 |
| sparse | 0.9040 | 0.9460 | 0.9600 |
| dense | 0.9300 | 0.9420 | 0.9620 |
| hybrid | 0.9440 | 0.9440 | 0.9620 |

## 3. THM × Context Economics 同查询成本代理

主情景：`deepseek-v4-pro_offpeak_2026-08-16`，下表使用 rho=0。每一行的 packed retrieval 与 full-history counterfactual 使用完全相同的 benchmark query denominator。

| 配置 | 尝试/可评分 | packed 每查询 | full-history 每查询 | full/packed 成本倍率 | 每 any-gold 成本 |
|---|---:|---:|---:|---:|---:|
| literal@300 | 1540/1532 | $0.000188 | $0.012189 | 64.98x | $0.000395 |
| literal@600 | 1540/1532 | $0.000385 | $0.012189 | 31.64x | $0.000682 |
| literal@1200 | 1540/1532 | $0.000781 | $0.012189 | 15.61x | $0.001220 |
| sparse@300 | 1540/1532 | $0.000188 | $0.012189 | 65.00x | $0.000311 |
| sparse@600 | 1540/1532 | $0.000385 | $0.012189 | 31.63x | $0.000558 |
| sparse@1200 | 1540/1532 | $0.000780 | $0.012189 | 15.62x | $0.001030 |
| dense@300 | 1540/1532 | $0.000188 | $0.012189 | 64.86x | $0.000474 |
| dense@600 | 1540/1532 | $0.000386 | $0.012189 | 31.61x | $0.000758 |
| dense@1200 | 1540/1532 | $0.000782 | $0.012189 | 15.59x | $0.001284 |
| hybrid@300 | 1540/1532 | $0.000188 | $0.012189 | 64.70x | $0.000321 |
| hybrid@600 | 1540/1532 | $0.000387 | $0.012189 | 31.53x | $0.000545 |
| hybrid@1200 | 1540/1532 | $0.000783 | $0.012189 | 15.57x | $0.000973 |

实验套件总量只用于运行成本记账，不用于和单一 policy 做收益比较：

- 配置数：12
- config-query executions：18480
- 每配置 attempted/scorable：1540/1532
- 全部实验臂 packed-input proxy 总成本：$8.347215

## 4. L6 预算网格敏感性

这里的“每 +1pp”指整批 benchmark 上 any-gold 提升一个百分点所对应的增量 packed-input proxy 成本，不是单查询成本。表格直接枚举 artifact 中实际存在的相邻预算步长。

| 模式 | 预算步长 | Δany-gold | 每 +1pp 成本 |
|---|---|---:|---:|
| literal | 300->600 | 9.01pp | $0.033795 |
| literal | 600->1200 | 7.57pp | $0.080493 |
| sparse | 300->600 | 8.81pp | $0.034580 |
| sparse | 600->1200 | 6.79pp | $0.089617 |
| dense | 300->600 | 11.29pp | $0.026965 |
| dense | 600->1200 | 10.12pp | $0.060312 |
| hybrid | 300->600 | 12.40pp | $0.024613 |
| hybrid | 600->1200 | 9.53pp | $0.063994 |

## 5. 结论与限制

1. hybrid@600 = 71.34% any-gold；数值上与仓库固定 reference 71.34% 相同；hybrid@1200 = 80.87% any-gold。数值相同不单独构成完整协议复现证明；这些也都是 evidence coverage，不是 answer accuracy。
2. 同查询口径下，固定预算 packed retrieval 的输入 token/cost proxy 可与 full-history carry 直接比较；该比较不等于真实账单，也不单独证明 O(N²) 历史增长。
3. 在当前 artifact 的 hybrid 300/600/1200 网格里，600→1200 的每 +1pp 边际成本为 $0.063994，高于 300→600 的 $0.024613（2.60x）；因此 600 仅可称为值得进一步验证的 knee candidate，不是全局最优阈值。
4. LongMemEval-S 提供第二数据集的 session-level generalization evidence，但其命中粒度与 LoCoMo 不同。
5. CPU/GPU 一致性应由独立 parity comparator 产物确认；运行时加速与检索质量必须分开报告。
