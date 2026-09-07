# Zero-LLM frontier: reproduced Protocol 2 baseline and failure census

Repository: `xngg1021/thm-tiered-hot-memory`. Predecessor:
`b6643224802e45d701f6710786ecb88d8e78bedf`, tree
`609370373fae86762794574691813d2f9d014947`. No open PRs existed when the
predecessor was inspected. `archive/v1.4.0-stable` was independently checked at
`e6e4dda5835e3cb345207457d5491131c6959b2c` and was not modified.

## Baseline reproduction

The [new baseline artifact](2026-09-07-zero-llm-frontier-baseline.json) reproduces
the [historical Protocol 2 summary](2026-09-06-recall-protocol2-summary.json)
exactly for literal and sparse packed/candidate any-gold coverage. Historical
files are unchanged. The SHA-256 of the upstream dataset is
`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`.

| Policy | Packed any-gold | Candidate any-gold | Scorable questions |
| --- | ---: | ---: | ---: |
| Literal, reproduced | 56.7885% | 78.7859% | 1532 |
| Sparse, reproduced | 69.3864% | 92.4282% | 1532 |
| Hybrid, historical only | 71.3446% | 97.2585% | 1532 |

Every conversation uses its own FTS database. Evidence is serialized as complete
source labels and text within 600 cl100k_base tokens. The inherited split is
conv-26/conv-30 for calibration; the other eight conversations remain holdout.
Category 5 and empty/unresolved annotations retain their historical exclusions.

The research README had reversed categories 1 and 4. It now agrees with the
unchanged runner: 1 multi-hop, 2 temporal, 3 open-domain, 4 single-hop. No historical
metric values were recomputed under different labels.

## Any-gold failure decomposition

| Category | Denominator | Candidate missing | Feasible candidate not packed | All candidate gold sources individually exceed 600 |
| --- | ---: | ---: | ---: | ---: |
| Multi-hop | 279 | 28 | 79 | 0 |
| Temporal | 321 | 26 | 55 | 0 |
| Open-domain | 92 | 31 | 20 | 0 |
| Single-hop | 840 | 31 | 199 | 0 |
| All main categories | 1532 | 116 (7.5718%) | 353 (23.0418%) | 0 |

Thus 353 of 469 failed questions already have at least one candidate gold source
that fits alone under the exact complete-source serializer and token budget.
The analysis-only oracle any-gold ceiling is 92.4282%, equal to candidate coverage.
This does not establish a label-free algorithm can attain that ceiling. Across
scorable sparse candidate encounters, the maximum standalone serialized source
size is 135 tokens; zero candidates exceed 600. Here the size problem is remaining
budget, not individually oversized source turns. Splitting also adds span-label
overhead, which must be counted.

The [machine-readable census](2026-09-07-zero-llm-frontier-census.json) includes
category denominators and example IDs. The compressed per-question trace is
`2026-09-07-zero-llm-frontier-traces.json.gz`; it contains IDs and metrics, not
conversation text. Reproduce with `research/recall/frontier_census.py`.

Temporal mismatch, alias mismatch, and structural-hop need remain causal
hypotheses; a category label alone cannot identify them. Segment-would-fit is
also insufficient to prove a supporting fragment exists. Ranking displacement
and oversized-at-remaining-budget overlap under rank-order skip packing and
must not be presented as independent additive failure totals.

## Evidence boundary

This is retrieval-only evidence: zero generative calls, zero judge calls, and
no embedding encoder loaded or downloaded. The initial 238 tests passed; added
census tests also pass. Index instrumentation runs after the production search
timer and reproduces the same coverage. Native memory, tiers, activity, validity,
Context Economics, Family HF, and historical stable references are unchanged.
