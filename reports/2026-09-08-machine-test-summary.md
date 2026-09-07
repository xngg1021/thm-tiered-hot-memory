# 2026-09-08 实机测试汇总:THM 全矩阵基准 × GPU 切换 × CE 经济学桥

> 证据等级:检索指标 runtime-measured(本机实测,零 LLM);成本数字 model-proxy(定价换算,非账单);定价 provider-doc-as-relayed(多口径并列,不选边);检索证据覆盖 ≠ 答案正确率。

## 1. 环境

- 机器:HP Z6 G4,Xeon Gold 6254(18C36T),96GB DDR4-2666 ECC,RTX 3080 10GB
- 软件:Python 3.11.15,thm-local-memory 1.4.0(engine-1.3,本目录),SQLite 3.53.1
- 编码器:sentence-transformers/all-MiniLM-L6-v2(pin 1110a243,Apache-2.0)
- GPU:torch 2.13.0+cu130(驱动 616.56 / CUDA 13.4)。cu128 通道仅有 2.11.0 且与 transformers 不兼容,已换 cu130 通道同版本号 2.13.0
- 计数器:cl100k_base;数据集 pin 校验通过(locomo10.json,SHA256 匹配)

## 2. LoCoMo Protocol 2 检索全矩阵(any-gold hit rate,主类别 1-4,1540 题)

| 模式 | @300 | @600 | @1200 |
|---|---|---|---|
| literal | 0.4778 | 0.5679 | 0.6436 |
| sparse | 0.6057 | 0.6939 | 0.7617 |
| dense | 0.3982 | 0.5111 | 0.6123 |
| hybrid | 0.5894 | 0.7134 | 0.8087 |

- hybrid@600 = 71.34%,与公开 README 基准一致,本机复现成功
- hybrid@1200 = 80.87%;micro evidence recall 最高 63.89%(hybrid@1200)
- 开发集 2 会话 / hold-out 8 会话,未用 QA 结果调参;generation_calls=0,judge_calls=0

## 3. LongMemEval-S 检索覆盖(500 实例,会话级证据,官方 answer_session_ids)

| 模式 | @300 | @600 | @1200 |
|---|---|---|---|
| literal | 0.8800 | 0.9380 | 0.9460 |
| sparse | 0.9040 | 0.9460 | 0.9600 |
| dense | 0.9300 | 0.9420 | 0.9620 |
| hybrid | 0.9440 | 0.9440 | 0.9620 |

- hybrid@1200 = 96.2% any-gold、macro 88.51%
- 口径注明:会话级证据比 LoCoMo turn 级粗,绝对分数不可与 LoCoMo 横向对比
- 数据集含重复 haystack_session_ids,文档 ID 编码会话出现序号后无冲突

## 4. GPU 切换与一致性

| 项 | CPU | GPU | 备注 |
|---|---|---|---|
| 嵌入吞吐 | ~25 ms/条 | 0.13 ms/条 | ~190x |
| LME-S 全量 | ~50 min | ~12 min | 4.2x |
| LoCoMo 全矩阵 | ~40 min | ~8 min | 5x |
| 检索延迟(hybrid@600) | 45.6/53.1 ms | 45.4/48.9 ms | LoCoMo 持平,LME-S 略降 |

- 24/24 配置(2 基准 × 4 模式 × 3 预算)GPU 与 CPU 结果逐项对比,全部一致,最大差异 0
- SentenceEncoder 新增 device/batch_size 参数,默认 cpu,向后兼容
- 剩余瓶颈:FTS 索引重建与 JSON 加载(与 GPU 无关)

## 5. THM × CE 经济学桥(deepseek-v4-pro off-peak,rho=0)

| 配置 | 每查询召回成本 | 每 gold-hit 成本 | 全携带每查询成本 | 携带/召回倍率 |
|---|---|---|---|---|
| literal@600 | $0.000385 | $0.000635 | $0.011951 | 31.0x |
| sparse@600 | $0.000385 | $0.000490 | $0.011951 | 31.0x |
| hybrid@600 | $0.000387 | $0.000470 | $0.011951 | 30.9x |
| hybrid@1200 | $0.000783 | $0.000801 | $0.011951 | 15.3x |

- L5:1986 题 12 配置召回输入总和 $8.35(off-peak,rho=0);全携带对照 $18.40
- L6 边际:预算 300→600 每召回点 $2.5-3.5;600→1200 每召回点 $6.4-9.0,倍率 2.2-2.6x,收益递减明确

## 6. 产物清单

- reports/2026-09-08-local-full-matrix.json.gz(完整 rows,25.8MB 原始 → 1.8MB gz)
- reports/2026-09-08-local-full-matrix-gpu.json.gz(GPU 重跑,同上)
- reports/2026-09-08-lme-retrieval.json / -gpu.json(2.6MB each,含 rows)
- reports/2026-09-08-economics-bridge.json(24KB)
- reports/2026-09-08-suite-report.json(144KB,编排器产物)
- reports/2026-09-08-suite-report.md(3.4KB)
- research/economics/(thm_ce_bridge.py、run_suite.py、report_md.py、README.md)
- research/recall/lme_retrieval.py
- research/recall/benchmark.py 与 thm/retrieval.py(device/batch-size 参数,默认兼容)

## 7. 保留意见

- 全部成本为 model-proxy,非真实账单;未接 provider 认证 trace
- 检索证据覆盖不是答案正确率;与业界答案级分数(如 Mem0 LoCoMo 92.5)不同口径,不可直接比
- deepseek-v4-pro 定价存在矛盾信源(促销 0.435 系列 vs 峰谷 0.66/1.32 系列),报告按情景并列
- dense 单独在 LoCoMo 上仅 51.1%(@600),纯语义检索不占优;hybrid 是推荐配置
