# THM 本地验证报告 · 2026-09-13

本目录是一次完整的本地验证,在 macOS 26.6.2 (arm64) / Python 3.11.16 上跑通 THM 1.5.0 的全部测试集与三个检索基准。所有数字均可复现,原始结果 JSON 见各子目录。

## 环境

- 仓库: xngg1021/thm-tiered-hot-memory @ 全量历史
- Python 3.11.16 独立 venv; 核心包纯标准库; numpy 2.4.6 / tiktoken 0.14.0 按文档补装
- dense/hybrid 编码: sentence-transformers/all-MiniLM-L6-v2 @ pinned revision 1110a243
- BEAM 判分模型: deepseek-v4-pro(OpenAI 兼容接口)

## 一、测试集(qa.yml 全绿)

| 检查项 | 结果 |
|---|---|
| runtime_headless_probe(-S 纯标准库) | pass, 0 网络/0 provider/0 generation |
| 单元测试 unittest discover | 669 tests OK, 0 失败 0 错误, 6 跳过 |
| thm_numeric_audit | 10/10 OK |
| evaluation --mode smoke | passed |
| evaluation --mode acceptance | status=passed, 5 基准 fixtures |
| check_docs | PASS, 0 错误 |
| check_version_history | OK, 10 里程碑 + 7 边界 |
| check_completion | OK, 28 域 / 71 provider |

## 二、LoCoMo Protocol 2(精确复现 README 声明)

1532 可评分题, 600 cl100k_base 证据切片。格式为 any-gold / all-gold。

| 检索模式 | 实测 | README 声明 | 结论 |
|---|---|---|---|
| Literal@600 | 56.79% / 46.61% | 56.79% / 46.61% | 完全一致 |
| Sparse@600 | 69.39% / 56.53% | 69.39% / 56.53% | 完全一致 |
| Dense@600 | 51.11% / 40.01% | 51.11% / 40.01% | 完全一致 |
| Hybrid@600 | 71.34% / 57.64% | 71.34% / 57.64% | 完全一致 |

前沿基准(实体投影): sparse any-gold 69.39% → 72.52%(+3.13pp, 95% CI [2.17, 4.20]), 预注册验收 passed。与 README 声明一致。

## 三、LongMemEval-S(500 实例, 精确复现历史报告)

held_out 497 题, session 级证据。

| 检索模式 | any_gold | all_gold |
|---|---|---|
| literal@600 | 93.76% | 69.82% |
| sparse@600 | 94.57% | 70.22% |
| dense@600 | 94.16% | 65.79% |
| hybrid@600 | 94.37% | 69.82% |

literal@300 held_out any_gold = 88.13%, 与 reports/2026-09-08-lme-retrieval.json 的 88.13% 一致。

## 四、BEAM(2000 题, 首次用 THM 检索 + deepseek 判分跑通)

这是本次验证里唯一没有现成 README 数字的:BEAM 的官方评分需要 LLM 生成答案 + judge 对照 rubric,THM 离线 CLI 给不出。我用 THM 的 sparse 检索(4000 token 预算)+ deepseek-v4-pro 生成答案 + 官方 unified_llm_judge_base_prompt 判分,忠实复现官方评测流程(官方 answer_generation_for_rag + unified judge prompt)。harness 见 beam/harness/。

### 按规模(规模→退化)

| 规模 | 题数 | 平均准确率 |
|---|---|---|
| 100K | 400 | 32.2% |
| 500K | 700 | 28.9% |
| 1M | 700 | 27.9% |
| 10M | 200 | 22.0% |

### 按能力类别(10 类)

| 能力 | 准确率 |
|---|---|
| preference_following | 55.4% |
| abstention | 55.0% |
| information_extraction | 44.1% |
| instruction_following | 32.5% |
| knowledge_update | 30.8% |
| multi_session_reasoning | 24.6% |
| temporal_reasoning | 17.9% |
| summarization | 16.0% |
| contradiction_resolution | 7.2% |
| event_ordering | 1.9% |

### 解读

- 总平均 28.5%。规模越大越差(100K 32.2% → 10M 22.0%),这印证 BEAM 论文的核心发现:长上下文检索在 10M tokens 规模退化。
- 检索友好的能力分高:abstention 55.0%、preference_following 55.4%、information_extraction 44.1%。需要跨证据聚合的能力分极低:event_ordering 1.9%、contradiction_resolution 7.2%。
- 这是 THM 零 LLM sparse 检索的真实基线。BEAM 论文里 Mem0 在 BEAM-10M 约 48.6%(LLM 提炼记忆),LIGHT 更强。THM 偏弱的原因是它拒绝用 LLM 做记忆提炼,这是设计取舍不是 bug。

## 文件清单

- locomo/lexical.json — LoCoMo literal/sparse 全预算结果
- locomo/semantic.json — LoCoMo dense/hybrid 结果
- locomo/frontier-full.json, frontier-summary.json — 实体投影前沿基准
- locomo/decay.json — 合成衰减扫描
- longmemeval-s/lme-full.json — LongMemEval-S 全量
- beam/beam-all-results.json — BEAM 2000 题判分结果
- beam/beam-10m-sample.json — BEAM 10M/1 的 20 题样本
- beam/harness/beam_harness.py, beam_driver.py — BEAM 判分 harness 源码
