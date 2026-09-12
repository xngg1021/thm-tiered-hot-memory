# Versioning

THM separates **stable package identity**, **unreleased research successors**, and **evidence class**.

The canonical accepted package version is stored in [`VERSION`](VERSION) and must agree with `pyproject.toml` for a stable release. Detailed historical changes live in [`CHANGELOG.md`](CHANGELOG.md); exact recovery identities and archive refs live in [`docs/12-version-history.md`](docs/12-version-history.md).

## Stable version

Current accepted implementation/integration milestone: **1.5.0**, frozen at `de26865f36df2205c29a470e51c65d5bf9beca4e`. Exact-head and main gates are recorded in the [post-merge closeout](reports/2026-09-12-v1.5-closeout.json).

The immutable recovery pointer for that implementation milestone remains:

`archive/v1.5.0-stable`

A stable version means that the corresponding implementation and its stated acceptance gates were completed for that exact historical state. It does not imply that every later experiment on `main` is part of the stable package.

## Unreleased successors

`main` may contain explicitly opt-in research after a stable package. Version 1.5 stabilizes the feature framework and executable interfaces; individual opt-in retrieval experiments retain their original positive or negative evidence and are not promoted to default behavior.

An unreleased successor must not silently move the stable recovery pointer, rewrite prior benchmark provenance, or upgrade its evidence class merely because the code is reachable from `main`.

## Evidence is not a version number

Version identity and evidence class answer different questions.

- Version identity says **which code and documentation state** is being discussed.
- Evidence class says **what that state has actually demonstrated**.

A higher version does not automatically prove better retrieval, better task quality, lower cost, lower latency, or production readiness. Retrieval benchmark evidence, harness lifecycle evidence and real task evidence remain separate.

## Release discipline

A new stable minor release is justified only when its intended capability surface is coherent, exact-head validation and review are complete, current-facing documentation is synchronized, and any required benchmark/runtime evidence has actually been rerun on the changed path. Failed or rejected experiments may remain documented without being promoted into the stable product surface.

Homepage content describes the current design and supported surface. Development chronology, exact PR/commit history and recovery details belong in the changelog and version-history documents.

## 1.5 freeze and post-merge evidence

The immutable `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c` never moves. The 1.5 archive pins the normally merged implementation commit after successful main correctness, Hermes and harness runs. `versions/history.json` records that exact accepted merge, feature head, archive and workflow IDs. Since those IDs cannot exist in the frozen tree before execution, a forward-only documentation descendant may carry the final closeout. Package version in the frozen tree must independently agree with the report. No rebase, reset, amend, squash merge or force-push is part of this release procedure.

Implementation-stable means the coherent documented code surface and its required checks passed. Integration-stable is scoped to exercised host lifecycles. Hardware-accepted, benchmark-accepted and task-outcome-accepted require their own source-bound evidence; no version number substitutes for those. Remote branch-protection administration being unavailable is a recorded governance exception, not an implementation defect.
