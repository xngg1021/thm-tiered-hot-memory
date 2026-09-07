# THM × Context Economics 对接层

本目录是 THM（T0–T3 memory Tiers）与 `context-economics`（L0–L6 analysis/control Layers）的**研究适配层**。两套分类体系保持独立；这里不把 THM 变成 Context Economics 子模块，也不把 Context Economics 变成 THM 规范。

## 对接原则

- THM 产出 retrieval/runtime telemetry；Context Economics 提供计价、证据等级和控制分析方法。
- 桥只交换可测量量：packed tokens、evidence hit、latency、budget、miss/locator/prefetch 等。
- 检索覆盖不等于答案正确率；`generation_calls=0`、`judge_calls=0` 的 benchmark 不能升级成 answer-level evidence。
- 所有美元数字都是 `model-proxy`，不是 observed provider bill，也不是 `cost_per_success`。
- full-history 对照必须与 packed retrieval 使用**完全相同的 query denominator 和 dataset bytes**；实验套件把多个 mode@budget arm 相加时，只表示实验运行总量，不能拿来和单一 policy 直接比较。

## 组件

| 文件 | 职责 |
|---|---|
| `thm_ce_bridge.py` | 读取 LoCoMo Protocol 2 rows，验证 counterfactual dataset SHA，加载显式指定的 Context Economics `Pricing` 实现，生成同查询 cost proxy、suite execution totals 和 L6 budget-grid sensitivity |
| `report_md.py` | 从 corrected bridge-v2 artifact 生成对外可读报告；拒绝旧 bridge schema；复现、预算 knee 等结论只在输入 artifact 实际支持时生成，不硬编码固定实验臂 |
| `run_suite.py` | 编排 CPU/GPU-tagged benchmark、bridge-v2 和报告；默认 `-cpu-v2/-gpu-v2`；在 benchmark 启动前用最终 suite receipt 原子占用 tag，同一 tag 即使中断也不可复用；公开 receipt 中路径自动脱敏 |
| `../recall/hardware_parity.py` | 对 CPU/GPU artifacts 做机器可验证的 retrieval-semantic parity；timing 不参与等价判定；没有 `selected_ids` 的 legacy artifact 只能判为 evidence insufficient |
| `../recall/benchmark.py` | LoCoMo Protocol 2 retrieval-only benchmark |
| `../recall/lme_retrieval.py` | LongMemEval-S session-level retrieval coverage runner；新运行会保存 selected IDs/source identities 供 parity 核验 |

## 2026-09-08 口径修正

历史 `2026-09-08-economics-bridge.json` / `suite-report.md` 存在 denominator 混用：单配置主类别实际尝试 1540 题、主评分分母 1532 题；12 个 mode@budget 配置合计是 18,480 次 config-query execution，而不是 1,986 次。旧 bridge 还用“按 conversation 去重后的平均长度”近似 full-history arm，不能与逐 query packed arm 严格配对。

bridge-v2 改为：

1. 每个配置显式记录 `attempted_questions` 与 `scorable_questions`；
2. full-history arm 先验证所给 LoCoMo bytes 的 SHA-256 与 benchmark artifact 完全一致，再按**每一条 query 所属 scope**逐行计 token；
3. suite totals 明确标为所有实验臂的运行总量，不再作为单 policy savings；
4. L6 marginal cost 使用 `USD per +1 percentage point any-gold gain`，不再把 0–1 rate 单位误称为“一个百分点”；
5. full-history same-query counterfactual 只证明 carry-vs-retrieval 的静态成本差，不单独证明 chronological `O(N²)`；
6. 默认 300/600/1200 只有三个网格点，因此 600 最多称为 `knee candidate`；自定义 budgets/modes 时，报告必须从实际 artifact 重新判断，不自动沿用该结论。

## Context Economics provenance

`thm_ce_bridge.py` 不再硬编码任何个人 Windows 路径。运行时必须显式提供 Context Economics checkout：

```bash
set CONTEXT_ECONOMICS_ROOT=D:\path\to\context-economics
# 或 Linux/macOS: export CONTEXT_ECONOMICS_ROOT=/path/to/context-economics
```

桥通过 `importlib` 加载该 checkout 的 `model.py`，并把 `git_commit`（可取得时）和 `model_sha256` 写入 artifact。这样 THM 只依赖一次显式研究运行，不形成 production cross-repo dependency。`run_suite.py` 的公开 receipt 只保留 `<PYTHON>`、`<THM_ROOT>`、`<DATASETS_ROOT>`、`<MODEL_PATH>`、`<CONTEXT_ECONOMICS_ROOT>`、`<REPORTS_DIR>` 等占位符，不保存用户名或本机目录。

## 推荐运行方式

```bash
# CPU 全套；默认原子占用 -cpu-v2。若该 tag 已存在或曾中断，必须换新 tag
python research/economics/run_suite.py \
  --device cpu \
  --ce-root ../context-economics

# GPU 全套；默认原子占用 -gpu-v2
python research/economics/run_suite.py \
  --device cuda --batch-size 64 \
  --ce-root ../context-economics

# 如需重复实验，显式使用新的唯一 tag；失败/中断的 tag 也不复用
python research/economics/run_suite.py \
  --device cpu --artifact-tag cpu-v2-rerun-02 \
  --ce-root ../context-economics

# 只重算修正后的经济桥（无需重跑 retrieval）
python research/economics/thm_ce_bridge.py \
  --results reports/2026-09-08-local-full-matrix.json \
  --dataset ../datasets/locomo10.json \
  --ce-root ../context-economics \
  --output reports/2026-09-08-economics-bridge-v2.json

python research/economics/report_md.py \
  --locomo reports/2026-09-08-local-full-matrix.json \
  --lme reports/2026-09-08-lme-retrieval.json \
  --econ reports/2026-09-08-economics-bridge-v2.json \
  --output reports/2026-09-08-suite-report-v2.md
```

## CPU/GPU semantic parity

GPU 加速和检索质量是两件事。用独立 comparator 检查 selected IDs、hits、MRR/nDCG、budget use 等 retrieval semantics；timing、embedding throughput 和环境字符串不参与等价判定。

历史 LoCoMo CPU/GPU artifact 已保存 `selected_ids`，可以直接跑 comparator：

```bash
python research/recall/hardware_parity.py \
  --cpu reports/2026-09-08-local-full-matrix.json \
  --gpu reports/2026-09-08-local-full-matrix-gpu.json \
  --output reports/2026-09-08-locomo-cpu-gpu-parity.json
```

历史 LongMemEval-S artifact **没有**保存 selected document identities，因此只能证明聚合指标一致，不能产生 positive semantic-parity receipt。当前 runner 已补 `selected_ids` / `selected_sources`；必须用新 runner 重跑 CPU/GPU 后再验证：

```bash
python research/recall/hardware_parity.py \
  --cpu reports/2026-09-08-lme-retrieval-cpu-v2.json \
  --gpu reports/2026-09-08-lme-retrieval-gpu-v2.json \
  --output reports/2026-09-08-lme-cpu-gpu-parity-v2.json
```

只有 comparator receipt 同时满足 `identity_complete=true` 与 `equivalent=true` 时，才把 CPU/GPU 结果称为 checked semantic parity。

## 指标映射

| THM telemetry | CE 位置 | 可支持的结论 |
|---|---|---|
| `budget_used` | L0/L4 | packed context input-cost proxy |
| `hits` / `any_gold_hit_rate` | L5 | evidence-coverage / cost curve；不是 task success |
| `latency_ms` | L5 | retrieval runtime observation |
| `builds` | L4 | derived-index build/residency overhead |
| same-query full-history tokens | L3/L5 | full carry 与 fixed-budget retrieval 的静态 counterfactual |
| tested budget grid | L6 | finite-grid sensitivity / budget feedback candidate；具体 knee 结论必须由 artifact 本身支持 |

定价仍使用情景口径并明确 provenance；如果定价来源互相冲突，必须并列而不是挑选最有利 headline。
