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
No new retrieval mechanism has yet passed holdout admission. Retrieval coverage
is not answer accuracy, and runtime correctness is not real-user task evidence.
