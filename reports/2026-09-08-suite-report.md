# THM × Context-Economics 本地对接基准全家桶报告

> **Historical artifact — economics section superseded.** Retrieval tables are retained as originally generated. The economics denominator/unit issues are documented in [`2026-09-08-machine-test-evidence-correction.md`](2026-09-08-machine-test-evidence-correction.md); use bridge-v2 outputs for new economic claims.

- 生成时间:2026-09-08(本机,Windows,HP Z6 G4)
- 引擎:thm-local-memory 1.4.0(engine-1.3 随公开仓 main)
- 经济模型:context-economics Pricing(L0)与证据纪律
- 编码器:sentence-transformers/all-MiniLM-L6-v2(pin 1110a243,CPU)

## 证据等级(CE 纪律)

| 指标类 | 等级 | 说明 |
|---|---|---|
| 检索指标 | runtime-measured | 本机实测,零 LLM(generation_calls=0, judge_calls=0) |
| 成本数字 | model-proxy | 定价换算的代理指标,不是真实账单 |
| 定价 | provider-doc-as-relayed | 第三方转述,多口径并列,不选边 |
| 检索覆盖 | - | 证据覆盖 ≠ 答案正确率 |

## 1. LoCoMo Protocol 2 检索全矩阵(any-gold hit rate,主类别 1-4)

- 问题数:1540(类别 5 仅诊断,不计入主指标)
- 数据集 pin:True,counter:cl100k_base
- 开发集 2 会话、hold-out 8 会话;未用 QA 结果调参

| 模式 | 300 | 600 | 1200 |
|---|---|---|---|
| literal | 0.4778 | 0.5679 | 0.6436 |
| sparse | 0.6057 | 0.6939 | 0.7617 |
| dense | 0.3982 | 0.5111 | 0.6123 |
| hybrid | 0.5894 | 0.7134 | 0.8087 |

对照:公开 README 报告 hybrid@600 = 71.34%,本机复现一致。hybrid@1200 达 80.87%。

## 2. LongMemEval-S 检索覆盖(session-level evidence)

- 500 实例、54 haystack 会话/实例(平均);证据 = 官方 answer_session_ids
- 会话级命中:至少一条来自 gold 会话的消息进入预算打包上下文

| 模式 | 300 | 600 | 1200 |
|---|---|---|---|
| literal | 0.8800 | 0.9380 | 0.9460 |
| sparse | 0.9040 | 0.9460 | 0.9600 |
| dense | 0.9300 | 0.9420 | 0.9620 |
| hybrid | 0.9440 | 0.9440 | 0.9620 |

## 3. THM × CE 经济学桥(deepseek-v4-pro off-peak 情景,rho=0 无缓存)

| 配置 | 每查询召回成本 | 每 gold-hit 成本 | 全携带每查询成本 | 携带/召回倍率 |
|---|---|---|---|---|
| literal@600 | $0.000385 | $0.000635 | $0.011951 | 31.0x |
| sparse@600 | $0.000385 | $0.000490 | $0.011951 | 31.0x |
| hybrid@600 | $0.000387 | $0.000470 | $0.011951 | 30.9x |
| hybrid@1200 | $0.000783 | $0.000801 | $0.011951 | 15.3x |

L5 总计(1986 题、12 配置全部召回输入之和,off-peak,rho=0):

- 召回方案总成本:$8.3472
- 全历史携带对照(1986 次查询):$18.40(hybrid@600 口径下的均值会话估算)

L6 边际分析(预算翻倍的增量成本,off-peak,rho=0):

| 模式 | 300→600 每召回点 | 600→1200 每召回点 | 倍率 |
|---|---|---|---|
| literal | $3.39 | $8.07 | 2.38x |
| sparse | $3.47 | $8.99 | 2.59x |
| dense | $2.70 | $6.05 | 2.24x |
| hybrid | $2.47 | $6.42 | 2.60x |

## 4. 结论(带保留意见)

1. hybrid@600 在本机复现 71.34% any-gold,与公开基准一致;检索路径可信。
2. 经济学对接成立:600-token 预算打包把每次查询的输入成本压到约 $0.00039,
   全历史携带需要 $0.012,相差约 31 倍;这是 CE O(N^2) 论证在 LoCoMo 上的具体数值。
3. 预算翻倍(600→1200)的边际成本约为第一档的 2.4-2.6 倍,收益递减明确;
   600 是本次检索任务上的经济拐点附近档位。
4. 保留意见:所有成本是 model-proxy 而非账单;检索覆盖不是答案正确率;
   定价口径存在矛盾信源(0.435 促销价与 0.66 峰谷价系列);LME-S 会话级证据
   比 LoCoMo 的 turn 级证据粗,不可直接横向对比绝对分数。
