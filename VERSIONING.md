# Versioning

THM separates **stable package identity**, **unreleased research successors**, and **evidence class**.

The canonical accepted package version is stored in [`VERSION`](VERSION) and must agree with `pyproject.toml` for a stable release. Detailed historical changes live in [`CHANGELOG.md`](CHANGELOG.md); exact recovery identities and archive refs live in [`docs/12-version-history.md`](docs/12-version-history.md).

## Stable version

Current accepted/stable implementation milestone: **1.4.0**.

The immutable recovery pointer for that implementation milestone remains:

`archive/v1.4.0-stable`

A stable version means that the corresponding implementation and its stated acceptance gates were completed for that exact historical state. It does not imply that every later experiment on `main` is part of the stable package.

## Unreleased successors

`main` may contain explicitly opt-in research successors after the latest stable package. The current zero-generative-LLM entity projection is such a successor: it is merged for continued research and measurement, but it is not labeled 1.5 stable.

An unreleased successor must not silently move the stable recovery pointer, rewrite prior benchmark provenance, or upgrade its evidence class merely because the code is reachable from `main`.

## Evidence is not a version number

Version identity and evidence class answer different questions.

- Version identity says **which code and documentation state** is being discussed.
- Evidence class says **what that state has actually demonstrated**.

A higher version does not automatically prove better retrieval, better task quality, lower cost, lower latency, or production readiness. Retrieval benchmark evidence, harness lifecycle evidence and real task evidence remain separate.

## Release discipline

A new stable minor release is justified only when its intended capability surface is coherent, exact-head validation and review are complete, current-facing documentation is synchronized, and any required benchmark/runtime evidence has actually been rerun on the changed path. Failed or rejected experiments may remain documented without being promoted into the stable product surface.

Homepage content describes the current design and supported surface. Development chronology, exact PR/commit history and recovery details belong in the changelog and version-history documents.
