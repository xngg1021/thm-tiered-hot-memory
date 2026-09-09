# Post-local-acceptance corrective contract (Unreleased)

The 2026-09-09 Z6 G4 run tested `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`; its evidence commit is `aa8391ebe506c38536dce787192d4d305ac335e1`. These measurements predate this corrective code. Package 1.4.0 and `archive/v1.4.0-stable` remain unchanged.

## Admission and fallback

`numeric_parity`, `structural_retrieval_parity` and `semantic_admission` are separate. Numeric sanity uses FP32 unit roundoff u = 2^-24, gamma(n) = n*u/(1-n*u), and tolerance 2*gamma(2*d+1) for embedding dimension d. This conservative envelope models two normalized length-d dot products, with Cauchy–Schwarz bounding the absolute-product sum. It is a deterministic sanity limit, not a proof that every transformer backend has this error bound. At d=384 it is approximately 9.17e-5; at d=8 approximately 2.03e-6. Both maximum embedding and score deltas must fit it. Tiny noise can pass only with identical ranked IDs, selected IDs, packed identities/hash/source/completeness and budget. Bitwise equality remains a separate diagnostic. No retrieval rounding, epsilon tie policy, fusion, sorting or packing changes are made.

A successful, self-validated CPU reference is always available as the baseline. An auto-safe candidate must also beat the reference on the selected measured metric; otherwise `selection=reference-fallback`, `status=calibrated`, `optimized_auto_safe=false`. This is micro-corpus calibration, not a universal semantic guarantee. A later strict auto-safe matrix mismatch still fails correctness acceptance. A throughput candidate that is slower than reference is not credited as acceleration (`faster_than_reference=false`). Throughput may admit measured drift; its receipt states `semantic_gate=measured-drift`, `strict_semantic_parity=false`, and aggregate quality remains unknown until separately measured.

## Candidate planning, budget and reuse

The baseline is ordinal 0 outside the trial cap. Round-robin backend/device representatives precede deeper batch/thread variants. Representative scorer variants follow the first backend/device representatives, before deeper tuning; no candidate is substituted at cap-dependent positions. The complete bounded plan records configs, ordinals, families, execution/skip reasons and admission outcomes. Standalone autotune (`OUTPUT.plan.json`), corrective retest and verification write a separate immutable plan before execution.

The historical six-candidate run changed candidate 5 to `torch_cpu`, whereas the twelve-candidate run retained `numpy_reference` at ordinal 5. The latter measured exactly equal scores; the former differed by 1.19e-7. No randomness is involved. Both used torch CPU/CUDA after ORT preparation failed.

Model-backed smoke skips optional backend export and accelerated trials. It calibrates the safe baseline, then promotes the identical two-instance LME pilot instead of loading and running it again. The enclosing process-tree deadline, explicit full-research acknowledgement, projection guards and immutable output namespace remain active. A 300-second budget is a ceiling, not a hardware-independent completion promise.

A caller-owned reference session reuses the same measured baseline across policies. The key binds hardware/software fingerprint, source manifest, reference config and micro corpus; receipt content is hashed and revalidated. There is no global cache. Pilot promotion records the source receipt hash and artifact identity. Production reference import closure is unchanged; protocol-3 semantic keys are not weakened. Existing private `.reference.json` sidecars are still required for cross-run dataset reuse; the published machine package does not contain them.

## Evidence, diagnostics and remaining hardware work

CUDA LoCoMo has 23 strict mismatch rows, including 3 selected-set changes. Auto-throughput LoCoMo has 5 strict mismatch rows and no selected-set changes. Both have equivalent measured aggregate quality. The disjoint primary taxonomy distinguishes numeric-only, rank-only, same-set-different-order, selected-set-change, packed-boundary-change and other semantic change. Category-five diagnostic rows are a separate cohort, not additive categories.

Bounded forensic rows include dense scores/deltas/ranks, selected state, budget and cutoff information when the source receipt contains them. Forensic candidate caps prioritize changed selections and boundary IDs. Cutoff rank is derived only from a full ranked-ID list; selected count is separate and missing legacy ranks stay unknown. Legacy sparse/fused numeric components are unavailable and remain null; these receipts cannot establish near ties as the sole cause. Current evidence is consistent with near-boundary floating-point sensitivity. No source text is copied into forensic output.

Preparation reports stage, stable error code/class, backend, dependency versions, retryability and redaction status. Source-copy, export, discovery, quantization, verification and publication are differentiated. The old generic ORT exception cannot establish its cause: **cause unresolved; improved diagnostic required**. Optional oneDNN raw execution-log import rejects capability-only banners; observed Windows ISA/kernel dispatch remains unknown without execution evidence and acquisition provenance.

Performance decomposition reports FTS, query embedding, matrix loading, scoring, fusion, expansion, packing and materialization with overlap semantics. Transfer is nested within scoring; FTS within sparse; shared batch clocks must not be summed once per row. Unmeasured orchestration residual remains unknown. The measured GPU document embedding gain does not imply the same end-to-end gain.

Local filesystem/NTFS/NVMe and bounded storage costs are machine-observed. Media class, NUMA, PCIe BDF, DAX and GDS remain unknown. PMem/DAX, CXL, SPDK, GDS, ORT/OpenVINO success, INT8 quality and post-fix hardware acceptance remain pending. Issue #13 stays open for the controlled batch sweep and positive dispatch evidence.

## Short local retest

From the merged clean checkout, use the existing local model and a new output directory:

```powershell
python -m research.runtime.corrective_retest --model-path MODEL_DIRECTORY --model-id sentence-transformers/all-MiniLM-L6-v2 --output-dir NEW_RETEST_DIRECTORY --wall-seconds 600 --prepare-ort
```

This covers synthetic ignition, real baseline fallback, two bounded CPU candidates, plan receipts, within-run reuse and optional ORT diagnostics. The deadline covers the entire process tree. It does not rerun LoCoMo or LME. CPU sweep is separate optional research, normally budgeted at 240 seconds:

```powershell
python -m research.runtime.query_batch --model-path MODEL_DIRECTORY --model-id sentence-transformers/all-MiniLM-L6-v2 --output-dir NEW_BATCH_DIRECTORY --wall-seconds 240
```

The CPU sweep holds backend/model/thread/scorer fixed and measures batch sizes 1/4/8/32 over the same micro workload, recording batch completion p50/p95, throughput, CPU use, construction overhead, offline wait=0, scorer/transfer times and semantic parity. Neither command establishes full-dataset acceptance; total requested ceilings are 14 minutes.
