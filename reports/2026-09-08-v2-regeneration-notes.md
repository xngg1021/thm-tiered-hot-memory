# 2026-09-08 v2 证据再生:执行记录与问题分类

本文件记录 2026-09-08 在本机重新生成 bridge-v2、LME GPU v2、CPU/GPU parity receipt 与 suite-report-v2 的过程中发现的全部问题,按类别归档。所有路径已脱敏为相对表述。

## 一、执行环境与前置问题

1. 正式 checkout 目录为空。仓库文档所暗示的正式工作目录在本机不存在(空目录),历史实机测试的实际执行环境与公开仓 checkout 分离。本轮执行在独立 clone 中完成,模型、数据集、CE 检出均通过显式参数指向仓库外的本机目录。
2. 默认路径假设不成立。run_suite 的 DEFAULT_MODEL_PATH / DEFAULT_DATASETS 假设模型与数据集位于引擎父目录,本机实际布局为模型在记忆系统目录、数据集在同级 datasets 子目录,直接按默认路径运行会失败,必须显式传参。
3. Hermes 自带 Python 环境无 pytest,仓库测试套件需 `uv run --with pytest` 或独立测试环境才能运行。
4. uv 执行在仓库根产生 uv.lock 与 *.egg-info 目录,均非仓库依赖声明方式,已补充 .gitignore。

## 二、代码缺陷

BUG-1(thm_ce_bridge.py):conversation_tokens 调用 `counter.count(text)`,而 thm.retrieval.TokenCounter 的接口是 `__call__`,执行即抛 AttributeError。已修复为 `counter(text)`。
根因:test_machine_test_recovery.py 中行加权相关测试以预计算 token 字典直调 economics_for_rows,绕过了 conversation_tokens 的真实集成路径,该路径无测试覆盖。
状态：fixed + regression-gated。新增真实 TokenCounter、LoCoMo-shaped synthetic dataset、conversation_tokens 与 build_report 集成测试，纳入 correctness unit discovery。

## 三、regeneration contract 与实际执行的偏差

1. contract 步骤 1 按原样执行会首先撞上 BUG-1,不修复则无法继续。
2. 旧 receipt 最多保存 25 条 mismatch preview，只能据此证明至少达到 cap；其中既有 ranked-order drift，也有 selected-set substitution。v2r1 完整扫描 23832 行，测得 25 个 mismatch entries、22 个不同的行：19 行 rank-only，3 行 selection-set substitution；主类别 16 行，category 5 诊断类别 6 行。聚合语义指标一致，strict selected-document semantics 不一致。CPU/GPU 浮点微差引发 near-tie 排序变化是推断；当前没有 candidate score/delta 证据，不能作为已证明根因。LME CPU v2 未运行，strict parity 尚无结论。核心 ranking、tie-breaking 和 embedding runtime 未修改。

## 四、实测发现

1. 历史报告"24/24 配置全部一致、最大差异 0"在聚合指标层面成立,在严格行级语义下不成立。parity receipt 已将该声称精确化。
2. LME GPU v2(新 runner,含 selected_ids/selected_sources)与历史 LME GPU artifact 的聚合 retrieval-quality 指标逐项一致，差异为零；timing 不参与此比较，完整 summaries JSON 并不相同。
3. bridge-v2 修正口径后的结果:packed 与 full-history 同分母对照,倍率从 300 档约 65x 递减至 1200 档约 15.6x;hybrid 每 +1pp 边际成本 300→600 为 0.025 美元,600→1200 为 0.064 美元(2.60 倍)。

## 五、CPU 优化后续实验

源码可确认 query path 调用 `encoder([query])`，即单 query embedding。实际指令集 dispatch、batch=1 的具体耗时归因、批量后可达到的毫秒数、ONNX int8 的加速倍数、AVX2 与 AVX-512 优劣均需要独立实测。本次没有 kernel trace 或 score-level diagnostics，不把这些推测列入 accepted measured results。后续实验比较同数据、同网格、质量与 selected IDs、throughput、p50/p95、CPU utilization、batch sweep、AVX2/AVX-512；ONNX/int8 单列 approximate fast mode。速度与严格语义是否能同时保持也由实验决定。

## 六、denominator drift 与 successor

benchmark canonical 为 1532，bridge-v2 为 1536；根因是 `_scorable()` 漏掉 `evidence_count > 0`，误纳 4 条 no-gold questions。benchmark 与 bridge 现在共享轻量纯 helper，bridge 和 report 按每配置 canonical summary 验证 attempted/scorable 与 suite totals，不一致即拒绝。economics-bridge-v2.json 和 suite-report-v2.md 已被 v2r1 同名 successor 替代，原文件保留。

attempted-query token/carry/pricing accounting 经逐配置 delta audit 完全不变。scorable suite executions 修正为 18384；hybrid 300→600 / 600→1200 为 12.4021pp / 9.5300pp，model-proxy 边际成本为 $0.024613 / $0.063994 每 +1pp。原旧 receipt 也保留，由 parity-v2r1.json 给出完整统计。

CE commit 保持 2aef1e7043273637adff1453d22dafc83d5e0e94。该 commit 的 LF model.py SHA 为 043b5db7c0f8c52e90dcc1ecb09293867a2943f4f60dd5adb4aec1a1c8a30f55；转为原 Windows CRLF 后，精确匹配原 artifact 的 8a80417468f138268db99784420f414add0fc1c213f6511de99142da0742affd。再生使用后者，未更换 CE 源码 revision。

run_suite 现在要求显式 --datasets-root/THM_DATASETS_ROOT、--model-path/THM_MODEL_PATH（dense/hybrid）、--ce-root/CONTEXT_ECONOMICS_ROOT，并在 reservation 与长跑前检查输入；保留路径脱敏和 atomic tag reservation。

## 七、剩余事项

LME CPU v2：pending-real-local-runtime。当前 Work 没有用户 Z6 G4 控制接口，未以云 CPU 替代。GPU v2 有 selected_ids/selected_sources；其 CPU 对应运行与 strict parity 均待本机执行。可复制命令见 canonical [v2r1 closeout](2026-09-08-machine-test-v2r1-closeout.md)。

## 八、PR #12 首轮 review forward-fixes

首轮 exact-head Codex review 返回 4 个 P2，均已 forward-fix：独立 CLI 和 README 覆盖风险、summary 完整性、aggregate 最大数值差异、解析/哈希重读竞态。新的 `2026-09-08-locomo-cpu-gpu-parity-v2r2.json` 保留同样 25 entries / 22 rows 和 aggregate=true / strict=false，额外通过完整 schema coverage，输入哈希来自解析的同一 byte buffer。先前 v2r1 receipt 保留，不覆盖。economics/report 在新读取实现下以临时新文件重算，字节与已提交 v2r1 完全相同。
