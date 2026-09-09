# Local machine evidence — main@b1f8119 on Z6 G4 (2026-09-09)

Real-hardware verification of the merged Evaluation Fabric and Physical Storage Fabric on the local workstation. All runs were zero-LLM (no generation or judge calls), used pinned local datasets, and left the checkout clean. Final acceptance verdict: `incomplete-local-run`, caused solely by the auto-safe calibration gate (section 7). No merge or acceptance authorization is derived from this report.

## Environment

- git HEAD: `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`, clean checkout, editable install `thm-local-memory 1.4.0`
- Machine: Intel Xeon Gold 6254 (36 logical / 18 physical cores, single socket), RTX 3080 10 GB (driver 616.56), CUDA 13.0 via torch 2.13.0+cu130
- Datasets: `locomo10.json` (SHA `79fa87e9…`) and `longmemeval_s` (SHA `08d8dad4…`), both matching the pinned bytes
- Model: `sentence-transformers/all-MiniLM-L6-v2`, local manifest `99f69f4e…`
- Environment repair performed before verification: the local clone was shallow and failed `check_version_history`; `git fetch --unshallow` plus full branch refs fixed it. Probe outputs were kept outside the checkout.

## 1. Core correctness

| Check | Result |
| --- | --- |
| HEAD / clean tree / `git diff --check` | pass |
| `pip install -e .` | pass |
| `python -S scripts/runtime_headless_probe.py` | pass (0 generation / provider / network calls) |
| `scripts/thm_numeric_audit.py` | 10/10 OK |
| `scripts/check_docs.py` | PASS (60 markdown, 386 links, 0 errors) |
| `scripts/check_version_history.py` | OK after unshallow (9 milestone snapshots, 6 development boundaries) |
| `python -m unittest discover -s tests` | 452 tests OK in 111 s |

## 2. Evaluation Fabric smoke

`python -m thm.evaluation --mode smoke`: passed in 2.6 s. Five benchmark receipts (locomo, longmemeval-s, longmemeval-v2, beam, memoryarena) over deterministic fixtures; V2Memory and AgentMemory sqlite interface fixtures verified; 0 generation/judge calls.

## 3. Runtime and storage probes

- `runtime doctor`: core-only available; torch/onnxruntime fp32 + onnxruntime int8 installed, openvino not installed; 36/36 CPUs visible.
- `runtime probe`: CUDA available (RTX 3080, ~9.5 GB free), CPU backend capability AVX512, onnxruntime CPU EP only.
- `storage probe/doctor`: target = local-filesystem adapter only; NVMe protocol, NTFS, 2 TB capacity, 348 GB free, physical block 4096; PMEM/CXL/SPDK/S3 and all other adapters correctly reported as extension-descriptor/unavailable.
- `storage benchmark` (5 s budget, 8 MiB scratch, used 0.14 s): 1 MiB buffered sequential ~1.38 GB/s, mmap ~0.92 GB/s, 4 KiB buffered random ~3.6 MB/s (p95 7 ms); cache state honestly reported as warm-or-os-managed.

## 4. Runtime smoke

`verify.py --mode smoke --wall-seconds 1200` (the default 300 s was refused by the budget guard, section 8). CPU reference arm: 2 LME instances, all four modes any-gold 1.0, 84 s wall. Status `incomplete-local-run`: auto-safe calibration `no-candidate-passed` with the 2-candidate cap.

## 5. Autotune gate diagnosis

Standalone `runtime autotune` (auto-safe, interactive, cpu+cuda, 12 candidates): calibrated. Admission sequence across 12 candidates: 4 retrieval-drift, then 1 strict pass, then 7 drift. Winner: torch_fp32 / cpu / doc batch 16 / query batch 1 / threads 1. Drift differences are floating-point noise: max score abs diff 1.8e-07 against a zero-tolerance gate. The machine needs roughly 4–6 candidates before one admits.

## 6. Bounded runtime acceptance

`verify.py --mode acceptance --wall-seconds 5400 --acknowledge-multi-hour-run` (the default 3300 s was refused, section 8). Completed in ~71 min. All six executed arms returned 0 with receipts.

| Arm | Dataset | Wall (s) | Doc embedding (s) | Quality headline |
| --- | --- | --- | --- | --- |
| cpu-reference | locomo (10) | 1055 | 105.7 | hybrid@600 any-gold 0.7134 |
| cpu-reference | lme (5) | 189 | 166.1 | any-gold 1.0 except dense@300 0.8 |
| cuda-reference | locomo | 940 | 9.2 | identical metrics to cpu |
| cuda-reference | lme | 29 | 5.1 | identical metrics to cpu |
| auto-throughput (cuda/b64/q8/t8/blob) | locomo | 860 | 12.0 | identical metrics to cpu |
| auto-throughput | lme | 31 | 5.9 | identical metrics to cpu |

LoCoMo quality on the pinned 10-instance subset (1540 questions, 1532 scorable): hybrid@600 any-gold 0.7134 — exactly the pinned historical 71.34%; hybrid@1200 0.8087; sparse@1200 0.7617; dense@1200 0.6123; all modes empty-context 0.

Parity vs cpu-reference:

| Arm | Dataset | Strict | Aggregate |
| --- | --- | --- | --- |
| cuda-reference | lme | true | true |
| cuda-reference | locomo | false | true |
| auto-throughput | lme | true | true |
| auto-throughput | locomo | false | true |

The LoCoMo strict failures reproduce the 2026-09-08 finding: numeric deltas are zero, strict parity fails only on adjacent-document tie ordering from floating-point accumulation order.

Performance observations: GPU doc embedding is ~11.5x faster than CPU on LoCoMo; LME end-to-end is 6.5x faster on GPU; LoCoMo end-to-end gains only ~11% because the bottleneck has moved to per-query scoring/encoding, consistent with the 2026-09-08 pure-CPU analysis. auto-throughput end-to-end gains: 1.18x on LoCoMo, 6.2x on LME.

## 7. Auto-safe gate: reproducible failure pattern

Three experiments on the same machine and code:

| Experiment | Candidate cap | Result |
| --- | --- | --- |
| runtime smoke | 2 | no-candidate-passed |
| runtime acceptance | 6 | no-candidate-passed |
| standalone autotune | 12 | calibrated (5th candidate admitted, reason strict) |

The zero-tolerance semantic gate rejects candidates whose scores differ by ~1e-07 from reference, which is the expected noise of changing CPU batch accumulation order. With caps of 2 and 6 the machine has a realistic chance of missing the ~1-in-5 admitting candidate entirely. This is a reproducible hardware-path behavior of the current main, related in kind to open issue #13 (CPU query-embedding batching and AVX/VNNI execution paths): the gate tolerance and the candidate budget are not matched to CPU floating-point behavior.

## 8. Budget-guard behavior (all by design)

| Attempt | Wall budget | Projection | Guard action |
| --- | --- | --- | --- |
| smoke | 300 s | 84 s matrix vs remaining budget after autotune | refused (`within_budget` false) |
| acceptance | 3300 s | 3962 s total (LoCoMo CPU extrapolation 3407 s) | refused (`multi-hour projection requires acknowledgement`, `within_budget` false) |
| acceptance + ack | 5400 s | accepted | completed in ~71 min, no interruption |

The guard measured, projected, and refused before spending hours — exactly the behavior the bounded verification contract promises.

## 9. What this evidence does not establish

- `full_dataset_acceptance` is false everywhere; LME-S covers 5/500 instances, LoCoMo covers the pinned 10-instance subset. No full-campaign numbers are claimed or implied.
- The LLM-agent-outcome layer remains not-run by design; fixture receipts cannot satisfy it.
- No kernel dispatch was observed; backend labels are not proof of ISA dispatch.
- The acceptance verdict is `incomplete-local-run` because auto-safe has no calibrated winner. The reference and auto-throughput evidence above stands on its own, but the overall gate is not green.

## Artifacts

Receipts are in `reports/2026-09-09-local-acceptance-b1f8119/` (prefixes: none = acceptance run, `smoke-` = runtime smoke, `eval-smoke-` = evaluation smoke). Large matrices are gzipped (`*.json.gz`). Excluded per runbook: all `.log` files, sqlite caches, embedding cache, derived models, and the pilot dataset slice (`pilot-locomo-input.json`). The private-path scan over every staged JSON is clean.

- `runtime-doctor-*.json`, `runtime-probe-*.json`, `storage-cost-*.json`, `storage-profile-*.json`
- evaluation smoke: `eval-smoke-acceptance.json`, `eval-smoke-completed.json`, five per-benchmark receipts
- runtime smoke: `smoke-comparison.json`, `smoke-runtime-estimate.json`, `smoke-cpu-reference-lme.json`, `smoke-auto-safe-autotune.json`
- acceptance: `comparison.json`, `runtime-estimate.json`, `hardware.json`, `storage.json`, `lme-census.json`, `plan.json`, execution receipts, LME result matrices, four parity receipts, `auto-safe-autotune.json.gz`, `auto-throughput-autotune.json.gz`, and the gzipped LoCoMo matrices
- gate diagnosis: `tune-diag.json.gz`
