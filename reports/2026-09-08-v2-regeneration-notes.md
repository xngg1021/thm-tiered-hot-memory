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
待办:为 conversation_tokens 补一条真实 TokenCounter + 真实数据集路径的集成测试。

## 三、regeneration contract 与实际执行的偏差

1. contract 步骤 1 按原样执行会首先撞上 BUG-1,不修复则无法继续。
2. contract 预期 LME 用新 runner 重跑 CPU/GPU 后 comparator 可给出 equivalent=true。实测 LoCoMo 历史 artifact 即已 equivalent=false:23832 行数值指标最大差异 0.0,但 25 处 dense/hybrid 模式的 selected_ids 相邻换位。根因为 CPU/GPU 矩阵乘浮点微差改变 dense 相似度排序,hybrid 的文档 ID 次级排序键只能覆盖完全平局,覆盖不了"接近但不相等"的分数。LME parity 在相同机制下预期同样拿不到 equivalent=true,除非检索核心增加显式平局判定(分数差小于阈值时按文档 ID 决序)或 comparator 放宽为"集合相等加顺序近似"。

## 四、实测发现

1. 历史报告"24/24 配置全部一致、最大差异 0"在聚合指标层面成立,在严格行级语义下不成立。parity receipt 已将该声称精确化。
2. LME GPU v2(新 runner,含 selected_ids/selected_sources)与历史 LME artifact 的聚合 summary 逐项一致,差异为零。
3. bridge-v2 修正口径后的结果:packed 与 full-history 同分母对照,倍率从 300 档约 65x 递减至 1200 档约 15.6x;hybrid 每 +1pp 边际成本 300→600 为 0.025 美元,600→1200 为 0.064 美元(2.60 倍)。

## 五、纯 CPU 加速分析(指令集与管道)

1. 指令集未被闲置。PyTorch CPU wheel 经 oneDNN 运行时检测并自动 dispatch AVX2/AVX-512 kernel,Xeon Gold 6254(Cascade Lake)支持 AVX-512 与 VNNI,现已在被调用。
2. CPU 慢的根因在管道形态:文档嵌入为批量编码,查询嵌入为逐条编码(检索核心中 `encoder([query])`),batch=1 前向使宽执行单元空转,单条约 25 毫秒的主要成本即源于此。
3. 优化路线按性价比排序:查询批量编码(先收集全部查询再批量嵌入,预期单条摊销至数毫秒,纯管道改动,不动模型);线程数与 batch-size 调优(零成本);ONNX Runtime 加 int8 量化(VNNI 指令主场,预期 2-4 倍,但量化误差会破坏 CPU/GPU 逐位一致,仅限快跑场景)。
4. AVX-512 降频注意:Cascade Lake 在重 AVX-512 负载下触发功耗许可降频,纯 AVX-512 负载可能反而慢于 AVX2,需实测对比。
5. FTS 索引重建与 JSON 加载是 I/O 与字符串处理,与浮点指令集无关,指令集优化无法覆盖。
6. 原则:parity 场景需要"慢但逐位一致",加速场景需要"快但近似",两者在浮点层面互斥,须分开设计。

## 六、未完成事项

1. LME parity 的 CPU 半边:需用新 runner 重跑一次 CPU(约 50 分钟),与 GPU v2 artifact 配对后 comparator 才能给出 LME 的 identity_complete 结论。
2. BUG-1 的真路径集成测试(见二)。
3. parity 顺序差异的呈现方式:当前仅存在于 receipt JSON,尚未写入任何报告正文。
