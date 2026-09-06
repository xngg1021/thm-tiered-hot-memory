# THM — Tiered Hot Memory

A 4-tier memory architecture for AI agents, grounded in cognitive science (ACT-R base-level activation, complementary learning systems, spacing effect) and current agent-memory engineering. This repository hosts the public documentation layer; the running system lives on the author's machine.

Author: Junfu Shi (SJF, xngg1021). License: MIT.

## What is THM

- T0 hot tier — injected into the system prompt every turn (working memory / L1)
- T1 warm tier — thematic files, agent reads on demand (semantic LTM / L2)
- T2 cold tier — session history, keyword retrieval (episodic memory / main storage)
- T3 frozen tier — pointers to the outside world: configs, papers, docs (no internalization)

Core mechanics: power-law decayed activation score A = Σ w·(t+1)^(−0.5) with event weights (hit ×2.0, confirm ×1.5, create ×1.0), promote/demote thresholds, offline consolidation, extended-interval re-verification. The design goal function mirrors Anthropic's context engineering ("smallest set of high-signal tokens").

## Repository contents (public layer only)

- `docs/01-研究综述.md` — research review: 10 design axioms distilled from cognitive science and agent-memory engineering literature, with a bibliography cross-checked across OpenAlex/Crossref (18/18 verified), an engineering-systems comparison table, benchmark landscape, and a "controversies and boundaries" section
- `docs/02-架构设计.md` — architecture design: 4-tier layout, cache-line metadata, activation score, promote/demote policy
- `reports/2026-09-06-学术工具复审.md` — academic audit report: full literature re-verification, counter-evidence findings, math recheck

Private data (warm-tier notes, memory index, engine scripts) intentionally stays out of this repository.

## Related

- Skills repository: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills) (the verification/literature/writing/computation skills used to produce the audit)
