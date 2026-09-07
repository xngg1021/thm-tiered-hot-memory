# 2026-09-08 实机测试汇总:THM 全矩阵基准 × GPU 切换 × CE 经济学桥

> **勘误状态：检索结果继续有效；原经济学聚合已被 supersede。** 详见 [`2026-09-08-machine-test-evidence-correction.md`](2026-09-08-machine-test-evidence-correction.md)。新的 bridge-v2 必须重新生成后才能发布修正后的经济数字。
>
> 证据等级:检索指标 runtime-measured(本机实测,零 LLM);成本数字 model-proxy(定价换算,非账单);定价 provider-doc-as-relayed(多口径并列,不选边);检索证据覆盖 ≠ 答案正确率。

## 1. 环境

- 机器:HP Z6 G4,Xeon Gold 6254(18C36T),96GB DDR4-2666 ECC,RTX 3080 10GB
- 软件:Python 3.11.15,thm-local-memory 1.4.0(engine-1.3,本目录),SQLite 3.53.1
- 编码器:sentence-transformers/all-MiniLM-L6-v2(pin 1110a243,Apache-2.0)
- GPU:torch 2.13.0+cu130(驱动 616.56 / CUDA 13.4)。cu128 通道仅有 2.11.0 且与 transformers 不兼容,已换 cu130 通道同版本号 2.13.0
- 计数器:cl100k_base;数据集 pin 校验通过(locomo10.json,SHA256 匹配)

## 2. LoCoMo Protocol 2 检索全矩阵(any-gold hit rate,主类别 1-4)

- 每配置 attempted questions:1540;主评分 scorable:1532;类别 5 仅诊断,不计入主指标

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

- 原始本机对比报告称 24/24 配置(2 基准 × 4 模式 × 3 预算)CPU/GPU 聚合结果一致、最大差异 0
- 历史 LoCoMo rows 已保存 `selected_ids`,可由 `research/recall/hardware_parity.py` 进一步生成机器可验证的 semantic-parity receipt
- 历史 LME-S rows 未保存 selected document identity,因此**不能**从旧 artifact 生成 positive semantic-parity receipt;当前 runner 已补 `selected_ids` / `selected_sources`,需要用新 runner 重跑 CPU/GPU 才能升级该证据
- SentenceEncoder 新增 device/batch_size 参数,默认 cpu,向后兼容
- 剩余瓶颈:FTS 索引重建与 JSON 加载(与 GPU 无关)

## 5. 历史 THM × CE 经济学桥(已 supersede)

下表和两条聚合结论保留用于追踪原始运行,**不得作为当前 accepted economics claim**。旧实现混用了 1540/1986/18480 denominator,full-history arm 又使用了按唯一 conversation 求均值的近似。新 bridge-v2 改为验证 dataset SHA 后逐 query scope 配对并明确 percentage-point 单位。

| 配置 | 每查询召回成本 | 每 gold-hit 成本 | 全携带每查询成本 | 携带/召回倍率 |
|---|---|---|---|---|
| literal@600 | $0.000385 | $0.000635 | $0.011951 | 31.0x |
| sparse@600 | $0.000385 | $0.000490 | $0.011951 | 31.0x |
| hybrid@600 | $0.000387 | $0.000470 | $0.011951 | 30.9x |
| hybrid@1200 | $0.000783 | $0.000801 | $0.011951 | 15.3x |

历史原文中的 `$8.35 vs $18.40`、`O(N²) 实机证明`、以及“每召回点”美元单位均已撤回;修正后的可发布数字等待同一 raw retrieval artifact 上重新运行 bridge-v2。

## 6. 产物清单

- reports/2026-09-08-local-full-matrix.json.gz(完整 rows,25.8MB 原始 → 1.8MB gz)
- reports/2026-09-08-local-full-matrix-gpu.json.gz(GPU 重跑,同上)
- reports/2026-09-08-lme-retrieval.json / -gpu.json(2.6MB each,含 rows;历史版缺 selected identities)
- reports/2026-09-08-economics-bridge.json(历史,经济口径已 supersede)
- reports/2026-09-08-suite-report.json / .md(历史;见勘误)
- reports/2026-09-08-machine-test-evidence-correction.md(当前勘误入口)
- research/economics/(thm_ce_bridge.py、run_suite.py、report_md.py、README.md)
- research/recall/hardware_parity.py
- research/recall/lme_retrieval.py
- research/recall/benchmark.py 与 thm/retrieval.py(device/batch-size 参数,默认兼容)

## 7. 保留意见

- 全部成本为 model-proxy,非真实账单;未接 provider 认证 trace
- 检索证据覆盖不是答案正确率;与业界答案级分数不可直接横比
- deepseek-v4-pro 定价存在矛盾信源(促销 0.435 系列 vs 峰谷 0.66/1.32 系列),报告按情景并列
- dense 单独在 LoCoMo 上仅 51.1%(@600),纯语义检索不占优;hybrid 是当前 tested-grid 推荐配置
