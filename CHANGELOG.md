# Changelog

This changelog is reconstructed from the repository's existing Git history. It does not invent retrospective semantic versions for commits that did not carry an explicit version identity.

## Unreleased — zero-LLM heterogeneous runtime

- Adds conservative hardware observations, explicit local backend preparation, content-bound embedding/runtime profiles and isolated bounded calibration.
- Adds coexisting profile vectors, optional float32 BLOB, exact-input cache, transactional legacy migration, configurable document batching, search_many/GEMM and FTS/encoder overlap.
- Adds bounded profile-safe scheduling, explicit sparse fallback receipts, runtime CLI, core-only ignition gate and shared harness feature configuration.
- Adds default-off temporal/alias/grammar/segment/association successors and one-shot local verification runner. Existing entity projection is reused.
- No accepted version bump, stable pointer movement, real hardware speedup claim or automatic retrieval-feature admission. See [runtime architecture](docs/17-zero-llm-heterogeneous-runtime.md).

## Unreleased — homepage and localization productization

- Replaces the oversized in-page multilingual README panels with one canonical English homepage plus seven complete standalone localized homepages.
- Reorganizes all eight homepages around THM's design philosophy, T0–T3 model, current capabilities, measured evidence, harness surfaces, invariants and evidence boundary instead of development chronology.
- Adds a shared eight-language switcher and explicit documentation/version navigation.
- Adds `VERSION` and `VERSIONING.md` to distinguish the accepted 1.4.0 package line from unreleased research successors and from evidence class.
- Updates documentation checks so standalone localized homepages are the source of truth and embedded locale copies cannot return.
- No retrieval, residency, harness or benchmark semantics change in this documentation-only productization slice.

## Unreleased — zero-LLM retrieval frontier

- Reproduces the immutable Protocol 2 baseline and separates 116 candidate misses from 353 feasible packing/ranking losses.
- Adds an opt-in Python `SearchIndex.search(..., entity_projection=True)` projection for exact speaker/identifier ranking in sparse/hybrid mode; default behavior is preserved.
- Fixed-weight Track A full any-gold: 69.39% → 72.52%; held-out 1301 questions: 69.56% → 72.33%. No generative model calls or embedding model.
- Excludes temporal, segment, bounded association and size-normalized ranking experiments from the production path; publishes their calibration ablations.
- Corrects reversed category names in the research README without rewriting historical benchmark values.
- No new stable version or archive pointer yet. See [frontier evidence](docs/16-zero-llm-retrieval-frontier.md).

## 1.4.0 accepted/stable — `e6e4dda5835e3cb345207457d5491131c6959b2c`

Archive: `archive/v1.4.0-stable`

- Adds explicit `resident_hit`, `resident_miss`, `hard_miss`, `planned_retrieval`, `stale_resident_failure` and bounded `prefetch` telemetry without converting observations into activity events. Raw misses and `avoidable=true` residency misses are reported separately; unknown telemetry fields fail instead of silently changing semantics.
- Separates all observed tasks from explicit demand tasks, so prefetch-only and planned-retrieval-only runs cannot dilute residency need rates. `min_item_demands` is enforced as a real per-item evidence gate; low-support current T0 is protected/reviewed rather than scored as zero-value.
- Adds a deterministic **T1 locator-only warm directory**. Display topics come from safe locator stems rather than legacy source-prefix keys; summaries and source content are not promoted to evidence by the projection.
- Adds an **opt-in Hermes T1 locator snapshot** with `warm_directory_budget=0` by default. The snapshot refreshes at session boundaries, not mid-session memory writes; selected targets must exist, resolve inside the current profile `memories/` root, and be files.
- Adds a **shadow value-aware T0 recommendation** using measured/caller-supplied avoidable-miss penalty versus repeated resident carry cost. Incomplete telemetry suppresses actionable `admit`/`evict` output. Positive measured candidates use deterministic exact 0/1 packing for the stated finite token objective, with explicit 100,000-budget-unit and 1,024-entry public bounds.
- Adds bounded **co-demand speculative prefetch**. Only current canonical seed items and explicit demand task co-occurrence train recommendations; prior prefetch outcomes cannot self-reinforce future prefetch/residency scores.
- Adds a bounded **shadow resident-budget feedback** step driven by avoidable miss pressure, context pressure, prefetch pollution and stale-resident risk. Raw unavoidable misses do not grow capacity, and the controller never mutates Hermes/T0 budgets automatically.
- Adds a non-authoritative local catalog for resident-cost, counterfactual miss-cost and locator measurement. The catalog cannot override canonical tier/status/validity/pin/source state; stale catalog identities and unexpected wrapper fields fail explicitly.
- Preserves the existing T0–T3 model and the older activity-only `plan` command. A pinned nonresident item is not auto-promoted. 1.4 does not auto-promote/demote tiers and makes no production optimum claim without held-out runtime/task evidence.
- Feature PR #5 was merged with a normal merge commit after PR-level validation. On the accepted merge SHA, main correctness run `34059895478`, Hermes run `34059895474`, and harness run `34059895461` succeeded. Retrieval run `34059936492` was skipped because no retrieval-path files changed; it is not a new Protocol 2 result.
- Release evidence: `reports/2026-09-07-v1.4-closeout.md` and `reports/2026-09-07-v1.4-closeout.json`.

## Unreleased — version-history recovery controls

- Added immutable-by-policy archive branches for historical research, engine and semantic-version milestones.
- Added `versions/history.json` as the machine-readable recovery map.
- Added `docs/12-version-history.md` with exact restoration boundaries and commands.
- Added `scripts/check_version_history.py` and wired it into cross-platform correctness CI.
- Preserved all prior commits and reports; no rebase, squash, force-push or historical rewrite is part of this reconstruction.

## 1.3.0 accepted/stable

- Adds pinned real-runtime E2E jobs for Claude Code 2.1.263, Codex CLI 0.153.4 and Gemini CLI 0.58.0.
- Synchronizes all seven non-English README files with the 1.3 integration and evidence boundaries.
- Acceptance requires the correctness, Hermes and harness matrices to pass on one exact commit. The immutable `v1.3.0` tag and `archive/v1.3.0-stable` ref formally identify that accepted SHA; see the release/ref itself for the value.

## 1.3.0 baseline — `1880211f75b016e2234cbef702573022f6f983f1`

Archive: `archive/v1.3.0-baseline`

- Package metadata declares `1.3.0` beginning at `51d33fddc24c23b81ed6bb88841be9d2dd0e1ce1`.
- Adds harness-neutral recall integration and adapters for Hermes, OpenAI Agents, LangChain/LangGraph and MCP/OpenClaw-oriented use.
- Extends Hermes setup/lifecycle validation and combined-budget handling.
- This historical baseline is not relabeled `stable`; exact workflow results remain authoritative for harness-specific closure.

## 1.2.0 — `432c93b17735cbdf20b240c66a6cba3739e70ab9`

Archive: `archive/v1.2.0`

- The 1.2 line begins at `433b1256bbaca8680f3c41d67a1e23e97b36bd7c`.
- Adds scoped recall, sparse/dense/hybrid retrieval, source packing, local embeddings, zero-weight mention observations, decay/residency evaluation and optional Hermes provider integration.
- Adds reproducible LoCoMo retrieval work, Protocol 2 evidence, latency/ranking metrics and local-only decay calibration export.
- `432c93b` is the last pre-1.3 development snapshot while `pyproject.toml` still declares `1.2.0`.

## 1.1.1 — `2196e1de36d9dae1798a147762b3019ebf81073e`

Archive: `archive/v1.1.1`

- Fixes cross-day explicit-event retries, selector ambiguity, malformed event handling, strict config selection, lazy-home resolution and symlinked warm-directory rejection.
- Historical evidence: `reports/2026-09-06-chat-followup.json` records `engine_version: 1.1.1`, predecessor `cb2db741...`, test counts and explicit non-claims.

## 1.1.0 — `cb2db7412035661b425dd2e5ec7f4650509da79d`

Archive: `archive/v1.1.0`

- Hardens the public index-maintenance engine around source identity, profile-bound storage, ambiguous updates, invalid dates/events, retry behavior, confirmation scheduling, validity, pins, conflict rejection, write failure, migration and CLI error codes.
- Adds engine/document regression coverage and cross-platform CI.
- Historical evidence: `reports/2026-09-06-engine-hardening.json` records `engine_version: 1.1.0`.

## Historical pre-version snapshots

### Legacy public engine — `4e9b5d8ed5a05c9a538f385acc8632e641ae5908`

Archive: `archive/20260906-engine-legacy`

First sanitized public paging engine. Later repository status documentation records that this engine retained known v1 defects. No retrospective `1.0.0` label is created.

### Corrected research snapshot — `25a51d7c68e36d3a53c94da568ff847f066f0fed`

Archive: `archive/20260906-docs-corrected`

Corrects theory, policy claims, audit provenance, arithmetic and evidence boundaries while retaining the four-tier design.

### Initial public research snapshot — `3fc7d6c438e167c384f20697cc1c0642d3de9e8a`

Archive: `archive/20260906-docs-initial`

Initial public research review, architecture design and academic audit report.

## Recovery boundary

Exact recovery is guaranteed only for states represented by reachable Git commits. Local-only private implementations, user memory/index data, installed configuration, external model/provider state and other bytes never committed to this repository require their original artifacts to reconstruct; they are not fabricated into old history.
