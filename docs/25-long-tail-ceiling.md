# Long-tail memory and retrieval ceilings

Track A / 0N is deterministic lexical, rule, metadata, graph and temporal retrieval without embeddings or generation. Track B / 0G permits local embedding and discriminative cross-encoder, late-interaction and learned-sparse reranking. Neither track permits generative extraction, rewriting, reranking or judging. 0API separately means no external model API. A BEAM campaign that generates and judges answers is not a zero-LLM campaign even when its retriever is 0N.

`TimeInterval` preserves day/month/year/range precision and source-anchored relative dates. The temporal algebra implements before/after, first/last, closest-before/after, overlap, same-day, ranges and interval-valued age arithmetic. Overlapping imprecise dates remain ambiguous rather than receiving invented order.

Explicit two-sided queries such as `after 2026-01-01 and before 2026-03-01` intersect both strict bounds, including reversed clause order and Chinese date-suffix forms. Invalid or multiply specified conflicting bounds are rejected. Generic ordering queries admit all bounded event candidates; explicit first/last queries select the corresponding edge. Packing orders complete source blocks by their earliest attached event interval, not their publication timestamp. Multiple events within one source remain an intact source block, so this does not claim to interleave or rewrite its individual events.

Temporal and ordering selections constrain every candidate channel and subsequent association/neighbor expansion, including dense and overlapping batch searches. Only matching event sources and their complete dependency-source closure are eligible. An empty temporal selection remains empty. The receipt distinguishes matched sources from required dependencies that may lie outside the queried interval.

`EventGraph` keeps source identities, actors, provenance parents, predecessor/successor structure, supersedes, contradicts and revocation. Cycles and foreign scopes are rejected. Newer timestamps alone do not settle truth. Explicit corrections mark prior claims superseded; unresolved contradictions remain unresolved. Graphs are derived representations, not additional memory tiers. Attached events are revalidated against current source hashes on every retrieval snapshot. Batched and overlapping searches rebuild graph dependency metadata at each actual query boundary; the complete-source guard applies through the shared option validator.

`LongTailSearchIndex` reuses the existing scoped SearchIndex transaction and optional source-derived event channels. Query classes cover entity, temporal, multi-hop, preference, update, contradiction, ordering, locator and implicit questions. Joint selection considers bounded source costs, query-term coverage and required evidence sets. Small candidate sets use exact subset search; large sets disclose a heuristic. Exact UTF-8 costs include source wrappers and separators. Nonadditive token counters use the exact reference counter with atomic dependency-closure admission and are explicitly labelled heuristic. Event dependencies require complete-source packing; combining an attached event graph with partial segment packing is rejected explicitly. These choices are default-off until appropriate held-out evidence justifies adoption.

`RetrievalCeilingReport` is evaluator-only. Serving does not receive gold. Its per-task decomposition reports:

| Quantity | Meaning |
| --- | --- |
| Candidate ceiling | Gold units present in the candidate universe |
| Budget-fit oracle | Maximum gold-unit coverage possible within the same budget; any/all-gold feasibility |
| Ranking loss | Oracle coverage lost after ranked eligibility selection |
| Packing loss | Packing-eligible feasible coverage lost in the actual context |
| Neighbor expansion gain | Feasible coverage added by neighbor/association expansion, separate from the pre-expansion candidate and ranked universes |
| Representation loss | Explicit annotations for lexical/relation/temporal/semantic/coreference ambiguity |
| Annotation ambiguity | Missing/multiple gold, parent-child mismatch, inference-only or ambiguous questions |

Coverage-mask DP discloses its bound. If state pruning occurs, the result is a heuristic lower bound and is not reported as a proven ceiling; loss quantities requiring exact ceilings remain null. With a full untruncated ranking list, ranking loss is zero and order-induced greedy losses appear in packing loss. Callers comparing a top-k ranker must supply its actual eligible subset. Parent locators never credit unselected child evidence.

All five Evaluation Fabric adapters accept `--ceiling --long-tail`. Original baseline, candidate and per-task results share task identity; dataset-wide accuracy still requires real annotations and the correct scorer. Event ordering reports set recall, comparable-pair ordering accuracy, Kendall-style concordance, missing events and extra events.

The preserved Mac baseline remains: LoCoMo literal 56.79/46.61, sparse 69.39/56.53, dense 51.11/40.01, hybrid 71.34/57.64; entity sparse any-gold 72.52. LME-S any-gold literal 93.76, sparse 94.57, dense 94.16, hybrid 94.37. BEAM answer/judge mean 28.5%, with event ordering 1.9%, contradiction 7.2%, temporal 17.9% and multi-session 24.6%. These are historical measurements, not targets or claims of 1.6 improvement.

The CPU/MPS end-to-end path is `research/recall/apple_end_to_end.py`: it compares LoCoMo and LME dense/hybrid execution using a validated local model snapshot. No model is downloaded. Component speedups are null unless separately measured; a total wall-time ratio cannot become an embedding or semantic improvement. Full datasets require explicit `--full-research`.
