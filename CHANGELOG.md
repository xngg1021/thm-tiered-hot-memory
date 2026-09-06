# Changelog

This changelog is reconstructed from the repository's existing Git history. It does not invent retrospective semantic versions for commits that did not carry an explicit version identity.

## 1.4.0 development — shadow residency control

- Adds explicit `resident_hit`, `resident_miss`, `hard_miss`, `planned_retrieval`, `stale_resident_failure` and bounded `prefetch` telemetry without converting observations into activity events.
- Adds a deterministic **T1 locator-only warm directory**; summaries and source content are not promoted to evidence by the directory projection.
- Adds a **shadow value-aware T0 recommendation** using measured/caller-supplied miss penalty versus repeated resident carry cost. Incomplete telemetry suppresses actionable `admit`/`evict` output.
- Adds bounded **co-demand speculative prefetch**. Only explicit demand task co-occurrence trains recommendations; prior prefetch outcomes cannot self-reinforce future prefetch/residency scores.
- Adds a bounded **shadow resident-budget feedback** step driven by miss pressure, context pressure, prefetch pollution and stale-resident risk. It never mutates Hermes/T0 budgets automatically.
- Adds a non-authoritative local catalog for resident-cost, miss-cost and locator measurement. The catalog cannot override canonical tier/status/validity/pin/source state.
- Preserves the existing T0–T3 model and the older activity-only `plan` command. 1.4 does not auto-promote/demote tiers and makes no production optimum claim without runtime/task evidence.

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

- Hardens the public index-maintenance engine around source identity, profile-bound storage, ambiguous updates, invalid events/dates, repeat feedback, review scheduling, publication and migration behavior.
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
