# 2026-09-08 machine-test evidence correction

This note corrects the economics interpretation of commit `78f47178b688f206a68a942118a463fc25489feb` without rewriting its raw retrieval artifacts. The retrieval results remain useful; the original economics aggregate/report must not be treated as an accepted matched-denominator cost comparison.

## What remains valid

- LoCoMo Protocol 2 retrieval-only measurements are runtime-measured, with `generation_calls=0` and `judge_calls=0`.
- Main-category any-gold results include hybrid@600 = 71.34% and hybrid@1200 = 80.87%.
- The main-category benchmark executes 1,540 questions per mode@budget configuration; 1,532 are fully resolved/scorable in the primary denominator.
- LongMemEval-S remains a separate session-level retrieval-coverage experiment. Its absolute scores must not be compared directly with LoCoMo turn-level evidence coverage.
- The CPU/GPU run reported identical retrieval results across the 24 tested benchmark/mode/budget configurations. A new machine-readable comparator is now provided in `research/recall/hardware_parity.py`; the historical verbal parity claim should be upgraded only after comparator receipts are generated from the archived CPU/GPU artifact pairs.

## What is superseded

The following statements in the original economics artifacts are not accepted as written:

1. `total_cost_usd_1986_queries` was mislabeled. The per-config main-category slice contained 1,540 attempted queries, not 1,986.
2. The 12 mode@budget configurations contain 18,480 config-query executions (`12 × 1,540`). The original approximately `$8.35` figure is the sum of packed-input proxy cost across all 12 experimental arms, not the cost of one deployed retrieval policy.
3. The approximately `$18.40` full-history figure was a single-arm counterfactual built from an unweighted mean across unique conversations. Comparing `$8.35` directly with `$18.40` mixes denominators and is invalid.
4. The original full-history calculation does not establish chronological `O(N²)` growth. It prices a final-history carry counterfactual; an actual growth claim requires an explicit prefix-over-time experiment.
5. The original `marginal_cost_per_point_of_recall_usd` divided by a 0–1 recall-rate delta. If “point” means one percentage point, the unit is off by 100. bridge-v2 reports `USD per +1pp any-gold gain` explicitly.
6. With only 300/600/1200 token grid points, 600 may be described as a `knee candidate` in this experiment, not an optimized global threshold.

## Corrected bridge contract

`research/economics/thm_ce_bridge.py` now:

- requires an explicit Context Economics checkout via `--ce-root` or `CONTEXT_ECONOMICS_ROOT` instead of a personal Windows path;
- records Context Economics `model.py` SHA-256 and Git commit when available;
- uses row-weighted full-history tokens so every packed query is compared with the same query's source-conversation history;
- separates `attempted_questions` from `scorable_questions`;
- labels suite-wide totals as experiment-run totals rather than policy cost;
- honors Context Economics request-rate semantics per prompt size;
- emits only model-proxy cost figures and keeps observed billing/answer accuracy explicitly unmeasured.

New outputs use `bridge-v2` / `suite-report-v2` filenames and do not overwrite the original 2026-09-08 artifacts.

## Required local regeneration

The corrected economic values depend on the local pinned LoCoMo dataset and the actual Context Economics checkout. Regenerate them from the same archived retrieval artifact:

```bash
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

For hardware parity:

```bash
python research/recall/hardware_parity.py \
  --cpu reports/2026-09-08-local-full-matrix.json \
  --gpu reports/2026-09-08-local-full-matrix-gpu.json \
  --output reports/2026-09-08-locomo-cpu-gpu-parity.json

python research/recall/hardware_parity.py \
  --cpu reports/2026-09-08-lme-retrieval.json \
  --gpu reports/2026-09-08-lme-retrieval-gpu.json \
  --output reports/2026-09-08-lme-cpu-gpu-parity.json
```

Until those v2/parity receipts exist, the strongest accepted statement is: **the retrieval benchmarks were reproduced locally and the first economics bridge demonstrated the right measurement direction, but its aggregate cost comparison contained denominator/unit errors and is superseded by this correction.**
