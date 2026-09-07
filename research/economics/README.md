# THM × Context-Economics 对接层

本目录是 THM(T0–T3 记忆分层)与 context-economics(CE,L0–L6 上下文经济学)的本地对接实验区。

## 对接原则(继承 CE README 的边界)

- THM 的 T0–T3 与 CE 的 L0–L6 是两套独立的分类体系,不合并。
- 两者只通过 telemetry/contract 交换证据:miss、hit、locator、prefetch、budget、latency。
- THM 负责产出检索遥测;CE 负责把遥测换算成经济指标。任何"策略更好"的声明必须带证据等级标签。

## 组件

| 文件 | 职责 |
|---|---|
| `thm_ce_bridge.py` | 读 THM 基准结果 JSON,按 CE Pricing 模型计算 L5 每配置经济学与全历史携带对照臂 |
| `../recall/benchmark.py` | LoCoMo Protocol 2 检索基准(THM 侧,已存在) |
| `../recall/lme_retrieval.py` | LongMemEval-S 检索覆盖率 runner(新增,零 LLM) |

## 证据等级(CE 2026-09-07 纪律)

- 检索指标:`runtime-measured`(本机实测)。
- 成本数字:`model-proxy`(定价换算的代理指标,不是真实账单)。
- 定价:`provider-doc-as-relayed`。deepseek-v4-pro 存在互相矛盾的第三方口径
  (2026-05-22 促销价 0.435/0.003625/0.87 与 2026-08-16 峰谷价 0.66/1.32 系列),
  桥脚本一律按情景并列呈现,不选边。
- 检索证据覆盖 ≠ 答案正确率:两套基准 generation_calls=0、judge_calls=0。

## 运行

```bash
# 1. LoCoMo 全矩阵(THM 侧)
cd memory-system/engine-1.3
python research/recall/benchmark.py --dataset ../datasets/locomo10.json \
  --counter cl100k_base --modes literal sparse dense hybrid \
  --budgets 300 600 1200 \
  --model-path ../models/all-MiniLM-L6-v2 \
  --model-id sentence-transformers/all-MiniLM-L6-v2 \
  --output reports/2026-09-08-local-full-matrix.json

# 2. LongMemEval-S 检索覆盖(THM 侧;--threads 按本机核数调,默认 8)
python research/recall/lme_retrieval.py --dataset ../datasets/longmemeval_s \
  --counter cl100k_base --modes literal sparse dense hybrid \
  --budgets 300 600 1200 \
  --model-path ../models/all-MiniLM-L6-v2 \
  --model-id sentence-transformers/all-MiniLM-L6-v2 \
  --threads 16 \
  --output reports/2026-09-08-lme-retrieval.json

# 3. 经济学桥(CE 侧)
python research/economics/thm_ce_bridge.py \
  --results reports/2026-09-08-local-full-matrix.json \
  --dataset ../datasets/locomo10.json \
  --output reports/2026-09-08-economics-bridge.json
```

## 指标映射(telemetry/contract)

| THM 遥测 | CE 层 | 用途 |
|---|---|---|
| `budget_used`(预算打包后实际 token) | L0/L4 | 记忆驻留租金、每查询输入成本 |
| `hits` / `any_gold_hit_rate` | L5 | 每命中成本、召回-成本曲线 |
| `latency_ms` | L5 | 检索延迟,任务经济学观测项 |
| `builds`(文档数、建索引秒数) | L4 | 索引驻留成本 |
| 全历史 tokens(对照臂) | L3/L5 | O(N²) 携带 vs 固定预算打包 |
| budget 300→600→1200 增量 | L6 | budget feedback、边际成本 |
