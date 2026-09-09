# Post-fix corrective retest — main@bb16760 (2026-09-09)

Real-machine verification of the PR #18 corrective changes (auto-safe gate, reference fallback, candidate plan, ORT diagnostics) on the local Z6 G4. Two bounded runs, ~14 minutes total, zero generation/judge calls, no LoCoMo/LME matrix.

## Corrective retest (`research/runtime/corrective_retest`, 600 s budget)

Final verdict: `status=calibrated`, `correctness_safe=true`, `optimized_auto_safe=true`.

| Check | Result |
| --- | --- |
| auto-safe calibration | calibrated, reason `measured-winner`, selection `calibrated-candidate` |
| accelerated candidate found | true, `faster_than_reference=true`, selection metric single_query_p95_ms |
| winner profile | torch_fp32 / cpu / doc batch 64 / query batch 8 / scorer torch_cpu |
| strict semantic parity | true |
| reference fallback path | exercised: calibrated, reason `no-faster-safe-candidate`, selection `reference-fallback` |
| within-run reference reuse | reused=true, class `within-run-reference-measurement` |
| candidate plan | emitted (`candidate-plan.json`) |
| ORT preparation diagnostics | conversion-failed recorded as an explicit diagnostic receipt (not a silent failure) |

This replaces the previous reproducible failure (`no-candidate-passed` across 2- and 6-candidate caps) on the same machine: the fixed gate now admits semantically equivalent CPU candidates instead of rejecting them on ~1e-07 floating-point noise.

## CPU query-batch sweep (`research/runtime/query_batch`, 240 s budget)

Fixed backend/model/thread/scorer, torch_fp32 on CPU, 108 queries per row.

| query_batch | p50 ms | p95 ms | queries/s | cpu_utilization % | semantic parity |
| --- | --- | --- | --- | --- | --- |
| 1 | 14.4 | 19.2 | 66.5 | 100.1 | admitted, bitwise true |
| 4 | 22.4 | 25.8 | 182.2 | 97.5 | admitted, bitwise false |
| 8 | 35.5 | 41.2 | 217.8 | 100.8 | admitted, bitwise false |
| 32 | 61.5 | 105.4 | 292.1 | 215.5 | admitted, bitwise false |

Throughput scales 4.4x from batch 1 to batch 32 at the cost of single-query latency (14.4 ms to 61.5 ms p50) when there is no arrival queue. Batch 32 crosses one core (215% CPU). Parity is admitted at every batch size; only batch 1 is bitwise identical, matching the expected accumulation-order behavior. `observed_kernel_dispatch` remains null and `dispatch_status` unknown — labels are not evidence of ISA dispatch.

## Evidence boundary

`full_dataset_acceptance=false` everywhere; the retest corpus is the fixed calibration corpus plus synthetic ignition. No recall or dataset quality numbers are claimed. This run closes the loop machine-discovery → code correction → post-fix machine re-verification for the auto-safe gate failure reported in `2026-09-09-local-acceptance-b1f8119.md`.

Receipts: `reports/2026-09-09-post-fix-retest-bb16760/`. Excluded per runbook: logs, caches, derived model artifacts (the `derived/` tree was empty in this run). Privacy scan clean.
