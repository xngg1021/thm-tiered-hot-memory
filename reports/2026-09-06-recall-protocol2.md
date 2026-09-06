# THM LoCoMo retrieval benchmark — Protocol 2

Date: 2026-09-06. This report records the completed Protocol 2 GitHub Actions run. It measures evidence retrieval under a fixed context slice; it does **not** measure generated-answer accuracy.

## Run identity

- THM commit: `702ad5c7973f7376e575734948847204cf5a4b0c`
- Workflow run: `34042410130`
- Artifact: `9992240586` (`thm-retrieval-metrics-protocol2`)
- Artifact SHA-256: `3facba77d1f5cbf6f1e76b57a43b44a6246fa6325ba9092afb1e22b3537893b9`
- LoCoMo upstream commit: `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`
- Dataset SHA-256: `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4` (pinned reference match: yes)
- Main denominator: 1532 fully resolved, non-adversarial questions
- Counter: `cl100k_base`; IDF scope: `one_database_per_conversation`; generation calls: 0; judge calls: 0
- Dense model: `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41`

## 600-token evidence slice

| Mode | Any gold | All gold | Macro evidence recall | MRR | nDCG | Candidate any-gold | p95 retrieval+packing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| literal | 56.79% | 46.61% | 51.03% | 0.381 | 0.397 | 78.79% | 24.07 ms |
| sparse | 69.39% | 56.53% | 62.43% | 0.497 | 0.507 | 92.43% | 34.55 ms |
| dense | 51.11% | 40.01% | 44.95% | 0.287 | 0.310 | 84.53% | 36.06 ms |
| hybrid | 71.34% | 57.64% | 63.96% | 0.459 | 0.481 | 97.26% | 57.88 ms |

At this exact protocol, hybrid improves any-gold coverage over sparse by 1.96 percentage points, while p95 retrieval+packing latency increases by 23.32 ms. This is a workload-specific tradeoff, not a universal default recommendation.

## Sparse budget sweep

| Budget | Any gold | All gold | Macro recall | MRR | nDCG | Mean budget used | p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 300 | 60.57% | 49.02% | 54.12% | 0.482 | 0.475 | 284.1 | 20.39 ms |
| 600 | 69.39% | 56.53% | 62.43% | 0.497 | 0.507 | 583.9 | 34.55 ms |
| 1200 | 76.17% | 62.79% | 69.17% | 0.503 | 0.528 | 1182.5 | 61.78 ms |

This sweep shows the expected budget/coverage tradeoff: sparse any-gold coverage rises from 60.57% at 300 to 76.17% at 1200, while p95 retrieval+packing latency also rises.

## Decay result included in the same workflow

The chronological decay sweep used `synthetic-regime-switch-v1`, selected `bounded_power@3d` on the development half, and obtained a held-out residency hit rate of 56.39%. `policy_installed` is false. This remains synthetic and must not be used as a user-specific decay setting.

## What Protocol 2 fixed

Protocol 2 uses the corrected LoCoMo category mapping, creates a separate FTS database per conversation so BM25/IDF statistics cannot leak across conversations, and records MRR, nDCG and p99. The workflow asserts protocol identity, the pinned dataset digest and IDF scope before accepting the artifact.

## Boundaries

Evidence retrieval is a necessary input to many memory QA tasks, not proof that a model will answer correctly. Dense and hybrid numbers include a pinned local sentence encoder but no generative model. User-specific decay remains unmeasured until a private chronological hit trace is exported and replayed; the repository does not publish personal memory data.

Machine-readable summary: [2026-09-06-recall-protocol2-summary.json](2026-09-06-recall-protocol2-summary.json).
