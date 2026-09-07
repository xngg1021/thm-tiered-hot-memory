# Zero-generative-LLM retrieval frontier

Status: research successor to THM 1.4; no 1.5 acceptance claim.

The authoritative predecessor is `b6643224802e45d701f6710786ecb88d8e78bedf`,
tree `609370373fae86762794574691813d2f9d014947`. The immutable
`archive/v1.4.0-stable` remains at `e6e4dda5835e3cb345207457d5491131c6959b2c`.

## Question and admission rule

How much of the candidate-to-packed evidence gap can deterministic mechanisms
close at 600 cl100k_base tokens? Every mechanism needs an internal measured gap,
a minimal derived implementation, an independent Protocol 2 ablation, and a
holdout decision. Negative experiments do not become production features.

Track A uses no neural model. Track B, when locally available, uses only the
existing explicitly pinned sentence encoder and is called zero-generative-LLM
hybrid. Neither track calls a model for parsing, extraction, rewriting, graph
creation, ranking, summarization, or judging. No encoder download is authorized
by this experiment.

## Protocol contract

The dataset SHA-256 is
`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`.
Protocol 2 uses one database per conversation and complete serialized evidence
including labels within the token cap. Categories are 1 multi-hop, 2 temporal,
3 open-domain, 4 single-hop, and 5 adversarial. The main denominator excludes
category 5 and unresolved or empty evidence annotations, exactly as before.

The existing split is inherited: sorted first two conversation IDs are
calibration, the remaining eight are holdout. Parameters must freeze before
holdout evaluation. Full aggregate results are comparable with historical
Protocol 2 but are not independent generalization evidence.

`research/recall/frontier_census.py` observes the unchanged search output after
its timer stops. It separates absent candidates, feasible candidates displaced
by packing/ranking, and whole-source budget impossibility. Its oracle asks only
whether at least one candidate gold source fits alone with identical labels.
Oracle labels never enter production retrieval. Category membership alone does
not prove a temporal, entity, or structural cause.

Partial source fragments cannot automatically inherit whole-turn gold credit.
Any segment experiment must separate parent-locator coverage from conservative
complete-evidence coverage; LoCoMo does not supply exact supporting span offsets.

## Boundaries

All channels are derived locators or projections. T0–T3, native-memory authority,
validity, activity, explicit movement, and the session-frozen warm directory stay
unchanged. Retrieval, entity matches, segment selection, and association
expansion do not count as hits, extend validity, or trigger promotion.

THM does not import or modify Context Economics or Family HF. No third-party
runtime source is copied. TiMem's temporal signal, Mem0's entity channel, and
AtomMem's bounded association idea are hypotheses only; their extraction
pipelines, memory taxonomies, and graph architectures are not adopted.

## Evidence status

The existing lexical baseline has been reproduced before new algorithms.
The fixed entity projection passed the preregistered holdout metric gates; release acceptance still requires completed review and exact-commit verification. Retrieval coverage
is not answer accuracy, and runtime correctness is not real-user task evidence.

## Retained Python API surface

```python
from thm.retrieval import SearchIndex, TokenCounter

index = SearchIndex("recall.sqlite3", TokenCounter("cl100k_base"), readonly=True)
try:
    result = index.search("my-scope", "What did Caroline discuss?",
                          mode="sparse", budget=600, entity_projection=True)
finally:
    index.close()
```

The default is false. Only sparse and hybrid accept this flag. The projection
uses exact speaker names and explicit technical identifiers within already
retrieved, scope-filtered candidates. A fixed 0.25 reciprocal-rank bonus favors
matching candidates. No new candidate membership, native write, alias identity
merge, activity event, validity extension, residency move or prompt-directory
metadata is introduced. With no signal, candidate order is unchanged.

This is a candidate projection, not a general entity extractor or persistent
alias side index. Automatic bilingual alias generation and coreference are not
implemented. Adapters and MCP do not expose this new flag in this successor.
The production option is measured on Track A; hybrid support is an API capability
without a new Track B evidence claim because no local encoder was available.

## Staged admission results

At 600 tokens on calibration (231 questions), baseline hits were 158. Temporal
produced 159 with no temporal-category gain; entity 170; segment 157; adjacency
association 171 but regressed open-domain; size-normalized ranking 115; cumulative
entity plus association 158 with worse all-gold. Only entity reached holdout.
Rejected prototypes remain under `research/recall` solely for reproducibility;
there is no production temporal, segment or association engine. Narrow query
grammar was not added after these results.

On 1301 held-out questions entity produced 55 wins and 19 losses (+2.7671 pp);
conversation-cluster bootstrap 95% interval: +1.7946 to +3.8247 pp. Every official
category's point estimate improved. These intervals describe eight correlated
conversation clusters, not universal task performance. Full comparable any-gold
is 69.3864% → 72.5196%; all-gold is 56.5274% → 59.4648%. Candidate coverage stays
92.4282%. The full aggregate includes calibration and is labeled accordingly.

See [baseline and census](../reports/2026-09-07-zero-llm-frontier-baseline.md),
[calibration](../reports/2026-09-07-zero-llm-frontier-calibration.json),
[pre-holdout freeze](../reports/2026-09-07-zero-llm-frontier-freeze.json),
[full summary](../reports/2026-09-07-zero-llm-frontier-full-summary.json), and
[resource census](../reports/2026-09-07-zero-llm-frontier-resources.json).

## Review hardening and current evidence

Projection admission is bounded to 16 unique identifiers of at most 256
characters, 64 speaker names of at most 128 characters, and 3000 candidates.
At most two patterns are compiled per query. Identifier matching skips source
bodies over 8192 characters; over-complex identifier queries use the unchanged
base order. Latin compound-name and identifier/path continuations are not accepted as exact matches. Known CJK speaker names may adjoin CJK prose; longest known names take precedence. This endpoint-specific relaxation applies only to speaker metadata, never to identifier matching. It recognizes known name strings and does not resolve unknown longer names or perform general word segmentation/NER.
These are safety bounds, not holdout-tuned weights.

Current production evidence is the [reviewed manifest](../reports/2026-09-07-zero-llm-frontier-reviewed-production-summary.json).
The earlier production manifest and trace are retained as pre-review provenance,
not claimed as exact-current-source results. See [reviewed results](../reports/2026-09-07-zero-llm-frontier-reviewed-results.md).
