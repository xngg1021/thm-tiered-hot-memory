# THM — Tiered Hot Memory

A four-tier memory design for Hermes Agent. Cognitive science and agent-memory research provide design inspiration and comparison points; they do not establish that THM's thresholds or policies are optimal. This repository contains the public documentation and reproducible specification checks. The running system and personal memory data remain on the author's machine and were not tested in this documentation correction.

Author: Junfu Shi (SJF, xngg1021). License declaration retained from the original repository: MIT.

## What is THM

- T0 hot tier — MEMORY.md and USER.md are loaded into a frozen system-prompt snapshot at session start in the pinned Hermes implementation. Requests reuse that snapshot; a disk write does not refresh it mid-session.
- T1 warm tier — thematic files retrieved on demand.
- T2 cold tier — session history and archives retrieved through the available search tools.
- T3 external tier — locators for configurations, papers and other sources, read when needed. “Frozen” is a tier name, not a guarantee that the external content is immutable.

The documented v1.0 policy uses a weighted power-law activity score, `A = sum(w * (age_days + 1)^(-0.5))`, with hit/confirm/create weights 2.0/1.5/1.0. It is an ACT-R-inspired heuristic, not a truth score. Removing a logarithm preserves ordering of the same positive sum; adding smoothing or changing weights can change ordering.

## Documentation correction — 2026-09-06

The four-tier layout is retained. The review now distinguishes published findings, engineering analogies, specification deductions and untested proposals. The architecture preserves the v1.0 rules as historical design statements and separately labels proposed changes to high-cost eviction exemptions, capacity admission, event semantics and consistency handling. No private engine, index, cron job or deployed policy was changed.

The original “18/18 verified” report is preserved verbatim under an explicit historical-status heading, with corrections before it. Bibliographic identity, citation support, numeric consistency and end-to-end effectiveness require different evidence. The public repository does not contain the original API responses or a controlled THM-vs-Hermes benchmark.

## Repository contents (public layer only)

- [Research review](docs/01-研究综述.md) — cognitive foundations, related systems, benchmarks, ten qualified design principles and research limitations.
- [Related work](docs/04-related-work.md) — source-backed comparison of memory systems, component licenses, version boundaries and open validation questions.
- [Architecture](docs/02-架构设计.md) — four tiers, documented v1.0 rules, confirmed specification issues and explicitly unimplemented revisions.
- [Audit report and errata](reports/2026-09-06-学术工具复审.md) — corrected conclusions followed by the unmodified historical report.
- [Numeric checks](scripts/thm_numeric_audit.py) — ten standard-library tests of the original public formula and rule counterexamples; not a private-engine test.
- [Document checks](scripts/check_docs.py) — local links, JSON examples, historical-report preservation and scope labels.
- [Validation record](reports/2026-09-06-文档勘误验证.json) — executed checks and their limits.

From this repository, with Python 3.10 or newer:

```bash
python scripts/thm_numeric_audit.py
python scripts/check_docs.py
```

Neither command contacts scholarly APIs, reads personal memory, mutates Hermes configuration or runs an LLM benchmark. Native Windows/macOS and a live Hermes session were not exercised in this correction. Private warm-tier notes, memory indexes and engine scripts intentionally remain outside this repository.

## Related

- [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills) — academic tools referenced by the historical audit. Their presence or version numbers are not proof that this repository's conclusions have been validated.

## Validation contract candidate

The [validation contract](docs/03-validation-contract.md) defines measurable acceptance criteria for a future implementation without changing the historical v1.0 formula or its regression tests. It distinguishes stored records, retrieved records, constructed context and a request actually observed at the host boundary. This public candidate contains documentation and mechanical document-check improvements; it does not include a runtime memory engine or claim deployment.

Additional document-check regression tests run with `python -m unittest discover -s tests -v`. Missing or undecodable required documents now produce a structured FAIL result. The historical report's byte identity and the original numeric regression remain required.
