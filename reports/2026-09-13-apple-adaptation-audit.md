# Apple 适配现状审计与 MPS 数值对等性实测 · 2026-09-13

> 本报告在一台 Apple Silicon 机器（macOS 26.6.2，arm64，torch 2.8.0）上完成。审计对象为当前 `main` 分支的 `thm/` 源码；MPS 实测使用 LME 同款本地模型 `sentence-transformers/all-MiniLM-L6-v2`（`/tmp/minilm`，fp32）。所有路径、行号以审计时提交为准。

## 一、结论摘要

THM 对 macOS 的适配分两层，深浅不一：

- **系统/资源核算层**：对 macOS 是认真做的，用了 libproc 私有 API 和 sysctl（含 Apple Silicon 大小核拓扑），与 Linux/Windows 三平台对称实现。
- **计算加速层**：基本未吃到 Apple 硬件。Apple 加速器（Metal/MPS、CoreML、Accelerate/BNNS、ANE）在 catalog 里多为"注册条目/扩展接缝"，不是可执行适配器；当前两个基准（LME、BEAM）全部跑通用 CPU 路径。

实测证明 MPS 路径本身是通的、数值安全、有确定性加速（2.3–2.4×），是当前投入产出比最高的一个开关。

## 二、Apple 适配现状审计

### 2.1 已实现（darwin 专属系统/资源 API）

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| 进程资源核算 | `thm/runtime/fabric/resources.py:91-111` | `ctypes.CDLL('/usr/lib/libproc.dylib')` 调 `proc_pid_rusage`（RUSAGE_INFO_V2），读 phys_footprint、resident_size、diskio_bytesread/written、CPU 纳秒时间。与 Linux（`/proc` + getrusage，`resources.py:113-167`）、Windows（Job Object，`resources.py:64-89`）三平台对称。 |
| 硬件拓扑探测 | `thm/runtime/hardware.py:134-143` | Darwin 分支用 `sysctl -a` 读 `hw.memsize`、`hw.physicalcpu`、`hw.logicalcpu_max`、`machdep.cpu.brand_string`，并特意读 `hw.perflevel.*` 系列——即 Apple Silicon 性能核/能效核大小核拓扑。 |
| MPS 能力探测 | `thm/runtime/capabilities.py:20` | `torch.backends.mps.is_available()`。 |

### 2.2 有代码路径、当前未激活

| 能力 | 位置 | 状态 |
| --- | --- | --- |
| MPS 检索 | `thm/runtime/fabric/indexes.py:197` | `api = torch.backends.mps if device == 'mps'`，仅当 `device='mps'` 时走 Metal。当前 LME 用 `--device cpu`。 |
| MPS 显存测量 | `thm/runtime/fabric/model_worker.py:112` | `torch.mps.current_allocated_memory()`，同样仅在 mps 设备下触发。 |
| 编码器设备白名单 | `thm/runtime/backends/__init__.py:76` | `device` 已放行 `('cpu','cuda','mps')`，但无 MPS 专属优化路径，只是把 device 透传给 `SentenceTransformer`。 |

### 2.3 仅注册条目/扩展接缝（非可执行适配器）

| 条目 | 位置 | 说明 |
| --- | --- | --- |
| `apple.coreml` | `thm/runtime/fabric/catalog.py:52` | `inference:CoreMLInference`，依赖 `coremltools`，devices cpu/gpu/npu，os=Darwin，compile=True。catalog 声明，未见推理实现。 |
| `apple.mpsgraph` | `thm/runtime/fabric/catalog.py:74` | 库 `MetalPerformanceShadersGraph`，`maturity=1`。 |
| `apple.bnns` | `thm/runtime/fabric/catalog.py:75` | 库 `Accelerate`，`maturity=1`。 |

关键证据是 `catalog.py:66` 的注释原文："Public C/ObjC extension seams have explicit maturity, never masquerade as executable adapters"——这些 Apple 条目是 C/ObjC 扩展接缝，明确不是可执行适配器。

### 2.4 完全缺失

1. 无 Accelerate（vDSP/BNNS）实算：未直接调 Accelerate framework 做矩阵/归一化运算。
2. 无 CoreML / ANE 推理实现：`apple.coreml` 只有条目，无 `coremltools` 转换与加载路径。
3. 无 NEON / AMX 手写内核。
4. kernel dispatch 证据只认 x86：`thm/runtime/dispatch_evidence.py:14-15` 仅解析 oneDNN 的 `avx512_core_vnni` / `avx512_core` / `avx2`，无 Apple Silicon（AMX/NEON/Metal）对应的 dispatch 检测。

## 三、MPS 数值对等性实测（本机）

### 3.1 环境

- macOS 26.6.2（arm64），torch 2.8.0，`torch.backends.mps.is_available() == True`
- 模型：`sentence-transformers/all-MiniLM-L6-v2`（fp32，90.8 MB 权重）
- CPU 侧使用 `OMP_NUM_THREADS=4`（与 LME benchmark 一致）
- 测试脚本：`research/recall/mps_parity.py`（本次新增，可复跑）

### 3.2 数值对等

10 条中英混合文本（含长短句），归一化 embedding 逐句对比：

| 指标 | 值 |
| --- | --- |
| 最小余弦相似度 | 0.9999998808 |
| 最大绝对误差 | 1.825e-07 |
| 平均绝对误差 | 3.643e-08 |

结论：误差在 fp32 精度量级，CPU fp32 与 MPS 数值对等。

### 3.3 检索对等

query "When is the deadline for the patent response?" 对 10 条文档取 top-5：

- CPU：`[1, 6, 4, 0, 7]`
- MPS：`[1, 6, 4, 0, 7]`

顺序完全一致。

### 3.4 吞吐（64 条/批 × 20 轮，warmup 后）

| 设备 | 平均 | 最快 |
| --- | --- | --- |
| CPU（4 线程） | 61.0 ms | 50.8 ms |
| MPS | 26.1 ms | 22.6 ms |

加速比 2.34×。MPS 显存占用 90.9 MB（≈ 权重体积）。

## 四、建议 / 行动项

1. **立即可用**：dense/hybrid 相关的 embedding 负载把 `--device cpu` 改为 `mps`，预期 2.3–2.4× 加速、数值对等、检索顺序一致。落地前先用 `--limit 3` 跑 sanity（LME 走 `Execution`/`SentenceEncoder` 路径，需确认 `preencode`/`embed` 在 mps 上无误）。
2. **补齐 Apple 加速器实现**：把 `apple.coreml` / `apple.mpsgraph` / `apple.bnns` 从 catalog 占位推进到可执行适配器（coremltools 转换 + MPSGraph/BNNS 内核），并给出与 CPU 的对等性证据。
3. **补齐 Apple Silicon dispatch 证据**：`dispatch_evidence.py` 目前只认 x86 oneDNN；增加 MPS/ANE 的 kernel dispatch 采集，使 Apple 平台的"加速已发生"可被证明，而不是仅凭能力横幅。
4. **纳入 CI**：`mps_parity.py` 可作为 Apple 平台的数值对等门禁（`--parity-tol` 默认 1e-4，退出码 0=通过）。

## 五、边界与诚实记录

- 审计只覆盖 `thm/` 与 `research/` 源码路径，未审计 `docs/`、`scripts/`、`plugins/` 中的平台描述。
- MPS 实测为单模型（MiniLM-L6-v2）、单批大小（64）结果；大模型或大 batch 下 MPS 的内存上限与速度关系未测。
- "整体加速"不等于 embedding 加速：LME 的 literal/sparse 检索与 SQLite 索引构建仍在 CPU 路径，切 mps 只会加速 dense/hybrid 的 embedding 段，整体加速比会低于 2.3×。
