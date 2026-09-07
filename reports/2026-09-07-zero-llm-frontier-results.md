# Zero-LLM retrieval frontier: measured successor to THM 1.4

Status: positive retrieval holdout, opt-in implementation; release review and merge verification pending. No 1.5 stable pointer is declared.

## Identity and protocol

Repository: `xngg1021/thm-tiered-hot-memory`. Predecessor main `b6643224802e45d701f6710786ecb88d8e78bedf`, tree `609370373fae86762794574691813d2f9d014947`. Branch `work/thm-zero-llm-retrieval-frontier-20260907`, PR #9. The production projection was published at `108237a4e22db1a631e39af82879bf3d6d0f1116`.

Dataset SHA-256: `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. Protocol 2, independent per-conversation FTS/IDF, unchanged category mapping and exclusions, complete serialized cl100k_base budget. All 1986 questions run; main denominator 1532.

## Canonical 600-token result

| Policy | Any-gold | All-gold | MRR | nDCG | p50 ms | p95 ms | p99 ms | Mean tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 69.3864% | 56.5274% | 0.497354 | 0.507241 | 21.73 | 29.15 | 34.20 | 583.93 |
| entity | 72.5196% | 59.4648% | 0.537435 | 0.543583 | 22.36 | 30.36 | 34.56 | 584.12 |

Candidate coverage remains **92.4282%**. Full any-gold increases by **3.1332 percentage points**, 69 wins versus 21 losses. Candidate-present-not-packed questions fall from **353 to 305**; candidate-missing stays **116**. This is a ranking/packing gain, not increased candidate membership. The oracle analysis-only ceiling remains 92.4282%.

The production API rerun exactly matches the frozen prototype in all 3972 question-policy records at 600 tokens, including selected order, hits, candidate hits, budget use, MRR and nDCG. Timing is independently remeasured; no speedup claim is made.

Historical hybrid (not rerun): 71.3446% any-gold, 57.6371% all-gold. Track B is unavailable: no local pinned encoder cache, and no model download was performed. The new strict deterministic result must not be called a new hybrid result.

## Holdout and categories

Calibration was conv-26/conv-30 (231 scorable questions); the eight remaining conversations provided 1301 held-out questions. Weight 0.25 and admission thresholds were committed before holdout. No weight sweep was performed. The public aggregate includes calibration.

Held-out any-gold: **69.5619% → 72.3290%**, +2.7671 pp, 55 wins/19 losses/1227 ties. Conversation-cluster bootstrap, seed 20260907, 2000 replicates: **[+1.7946, +3.8247] pp**. Eight conversation clusters limit generalization.

| Held-out category | Denominator | Wins | Losses | Delta pp |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 236 | 16 | 0 | +6.7797 |
| Temporal | 258 | 10 | 3 | +2.7132 |
| Open-domain | 81 | 3 | 0 | +3.7037 |
| Single-hop | 726 | 26 | 16 | +1.3774 |

All prespecified metric gates pass: holdout gain ≥1 pp, no all-gold loss, no category regression over 2 pp, p95 ratio ≤1.25. The single-hop category interval crosses zero; its positive point estimate is not a separate strong significance claim.

## Independent calibration ablations

| Mechanism | Any-gold hits / 231 | Wins | Losses | Decision |
| --- | ---: | ---: | ---: | --- |
| Baseline sparse | 158 | — | — | Reproduced |
| Temporal metadata | 159 | 1 | 0 | Excluded: no temporal-category gain |
| Exact entity projection | 170 | 14 | 2 | Only holdout candidate |
| Segment fallback | 157 | 0 | 1 | Excluded: recall loss and latency |
| One-hop adjacency | 171 | 21 | 8 | Excluded: weak target gain, open-domain loss, negative cumulative behavior |
| Size-normalized rank | 115 | 8 | 51 | Excluded: ranking pollution |
| Entity + adjacency | 158 | 8 | 8 | Excluded: no any-gold gain, all-gold loss |

No failed mechanism was tuned on the holdout. Research prototypes remain reproducible under `research/recall`; none is enabled as a production temporal/segment/graph engine. No general alias resolver, neural NER, full temporal grammar, graph database or extra memory tier was added.

## Budget curve

The frozen prototype curve is paired at each budget. The 600-token production rerun above verifies exact selection equivalence.

| Tokens | Baseline any-gold | Entity any-gold | Baseline p95 ms | Entity p95 ms |
| --- | ---: | ---: | ---: | ---: |
| 128 | 43.4726% | 48.3029% | 10.94 | 11.56 |
| 256 | 57.8982% | 61.6841% | 17.17 | 16.07 |
| 400 | 65.1436% | 67.4282% | 22.26 | 22.96 |
| 600 | 69.3864% | 72.5196% | 31.63 | 31.04 |
| 800 | 71.9321% | 75.0000% | 39.00 | 41.04 |
| 1200 | 76.1749% | 78.5901% | 54.69 | 55.08 |

At 600, mean tokens increase only 0.1935 while any-gold gains 3.1332 pp. This rules out an undisclosed budget increase as the source of the measured improvement. Index builds took 24–65 ms per conversation in a separate resource census, databases 585728–1077248 bytes, isolated build-process peak RSS 70296 KiB (includes tokenizer, not query peak). The projection adds no persistent tables.

## Correctness, scope and evidence limits

252 local unit/invariant tests passed, including seeded budgets, unchanged no-signal order, candidate deduplication, exact fragment offsets, no inherited fragment gold credit, scope isolation, read-only DB bytes and native-memory bytes. The research README category wording was corrected; historical report numbers and old stable references were preserved.

Production use is an explicit Python `entity_projection=True` argument in sparse/hybrid mode. It is not exposed automatically to Hermes, MCP, or other adapters. Existing source speaker/identifier matches are retrieval signals only: no alias identity merge, hit, validity update, tier movement, budget mutation, prefetch learning, or native-memory write.

No generative model call occurred in these retrieval experiments; no embedding model was used. No answer was generated or judged. T0–T3 are unchanged. `context-economics` and Family HF were not modified or imported. Retrieval evidence is not answer accuracy or task-economic superiority. Stable 1.5 registration remains a separate decision after review and exact-main verification.

## Reproduction and artifacts

```bash
python research/recall/frontier_census.py --dataset /path/to/locomo10.json --output /tmp/census.json
python research/recall/frontier_ablation.py --dataset /path/to/locomo10.json --policy entity --split full --budgets 128 256 400 600 800 1200 --output /tmp/full.json
python research/recall/frontier_report.py --input /tmp/full.json --output /tmp/summary.json
```

[Baseline](2026-09-07-zero-llm-frontier-baseline.md) · [Freeze](2026-09-07-zero-llm-frontier-freeze.json) · [Production summary](2026-09-07-zero-llm-frontier-production-summary.json) · [Budget summary](2026-09-07-zero-llm-frontier-full-summary.json) · [Resources](2026-09-07-zero-llm-frontier-resources.json). Compressed JSON traces are stored alongside the summaries; they contain question/source IDs and metrics, not source conversation text.
