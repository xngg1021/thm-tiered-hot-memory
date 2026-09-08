# One-shot local runtime verification — pending-real-local-runtime

Predecessor main: `9eb904c21fd25aa0a77d2420ed080702fac17e59`. Successor branch: `work/zero-llm-heterogeneous-runtime-autotune-20260908`. Use the final exact PR head recorded in its closeout comment. This plan does not authorize merge or certify any performance result.

## One command package

From a clean checkout of that branch on the actual Z6 G4, with existing local model and datasets, paste:

```powershell
$ErrorActionPreference = 'Stop'
$model = (Read-Host 'Existing local model directory').Trim('"')
$locomo = (Read-Host 'Pinned locomo10.json full path').Trim('"')
$lme = (Read-Host 'Pinned longmemeval_s JSON full path').Trim('"')
$output = (Read-Host 'Fresh report directory outside the checkout').Trim('"')
python research/runtime/verify.py --model-path "$model" --model-id sentence-transformers/all-MiniLM-L6-v2 --locomo-dataset "$locomo" --lme-dataset "$lme" --output-dir "$output" --include-approximate --retrieval-ab
if ($LASTEXITCODE -ne 0) { throw 'Verification incomplete; inspect retained receipts and use a fresh directory for retry' }
```

Optional dependencies must already be installed explicitly. Core: `pip install .`. Torch: `pip install '.[semantic-torch]'`. ORT/OpenVINO: corresponding `semantic-onnx` / `semantic-openvino` extras. The runner never installs packages or downloads models. CUDA-enabled Torch availability is verified by the explicit backend probe. Model files and private logs stay local; share JSON receipts after inspecting them, not the derived-model directory or embedding cache.

Add `--plan-only` for a no-model planning run in a fresh directory. `--max-candidates 12` bounds calibration. Document candidates span 16/32/64/128/256 and query candidates 1/4/8/32; resource constraints and cap can prune them. Full matrices run reference and measured policy winners, not the full Cartesian product. The package retains failed/unsupported candidate receipts. It does not require the user to rerun a benchmark during implementation.

## Stages and artifacts

| Stage | Artifact/contract |
|---|---|
| Reservation | Fresh directory and `plan.json`; existing directory refused |
| Hardware | `hardware.json`: actual machine, CPU availability, backend/provider observations, Git/implementation/model hashes; observed dispatch null unless separately supplied |
| LME census | `lme-census.json`: exact input counts/reuse by ordinal and avoided bytes/counter units; speedup null |
| Optional conversion | `*-preparation.json` and local content-addressed `derived-models/`; source bytes unchanged |
| Calibration | `auto-safe-autotune.json`, `auto-throughput-autotune.json`, optional approximate: samples/timings/semantic gate/trials/winner |
| CPU reference | `cpu-reference-locomo.json`, `cpu-reference-lme.json` |
| CUDA reference | `cuda-reference-*.json` only when real CUDA is available |
| Winners | `auto-safe-*.json`, `auto-throughput-*.json`, optional `approximate-performance-*.json` |
| Overlap/GPU batch | `cuda-batched-overlap-*.json` on actual CUDA |
| Algorithm A/B | `feature-{entity,explicit_alias,temporal,query_grammar,segment,association}-locomo.json`; separate from speed comparison |
| Runtime execution | `*-execution.json`: return code, wall time, artifact SHA, feature identity |
| Score diagnostics | `*-score-deltas.json`: per-candidate reference/candidate scores and deltas, selected order/cutoff/profile; missing observations remain unknown |
| Comparison | `*-parity.json` plus `comparison.json`: strict and aggregate results; no automatic acceptance/merge |

Both datasets must match the prior pinned bytes. LoCoMo SHA256: `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. LME SHA256: `08d8dad4be43ee2049a22ff5674eb86725d0ce5ff434cde2627e5e8e7e117894`. FTS remains one database per conversation/instance. Source model manifest and package versions are collected locally, not inferred from model_id.

## Individual stage commands

```powershell
python -m thm runtime doctor --json doctor-new.json
python -m thm runtime probe --json probe-new.json
python -m thm runtime autotune --model-path "$model" --model-id sentence-transformers/all-MiniLM-L6-v2 --device cpu --device cuda --output tune-new.json
python -m thm runtime status --profile tune-new.json --model-path "$model"
python -m thm runtime prepare --model-path "$model" --backend onnxruntime_fp32 --cache-root derived-new --output prepare-new.json
```

Profiler hooks remain explicit: run the chosen local profiler around an individual benchmark command, retain its raw output, then import a JSON containing `embedding_profile_id`, `profiler`, and `observed_kernel_dispatch` using `runtime import-dispatch --input ... --embedding-profile-id ... --output ...`. A hardware flag or provider name alone is not observed dispatch.

## Acceptance

Compare actual build/embedding throughput, single-query p50/p95 and batch throughput separately, whole LoCoMo/LME wall time, memory/VRAM and utilization where available. Null utilization or ISA dispatch is not zero. Read selected/ranked IDs, budgets, any/all-gold, macro/micro recall, MRR/nDCG and parity together with timing. Candidate score arrays identify near-tie queries for diagnosis; no new tie threshold is authorized.

A performance refactor aims at reference semantic parity. Each algorithm feature has a separate A/B result, with segment parent-locator coverage separated from conservative complete-evidence coverage. A micro-corpus calibration pass does not admit a feature or establish global speedup. No CPU/CUDA/AVX/VNNI/INT8/temporal/segment/association improvement is asserted by this plan.

Final implementation state must remain **NOT MERGED — awaiting real local runtime acceptance**. Prior machine artifacts and archive stable remain unchanged.
