# Public engine 1.1 hardening report

Starting repository commit: `570570162039f600cf323a856104cf88c8d334b5`. Starting engine blob: `36e8a5af570c644d55ecee1f7577aaac53c95c0b`. Work applies to the public main script; it does not merge or publish a separate private reference implementation.

## Changes

The 24-character key remains a display/selector clue, no longer unique identity. Complete section content plus source store produces a fingerprint; stable IDs remain distinct across source files. Source directory binding prevents accidental reuse of another profile's index. New state defaults outside the repository, under the selected memories directory.

Index writes now use local operating-system advisory locks, optimistic version/digest checks, serialization before destination mutation, a previous-index backup, same-directory atomic replacement and readback. Real child processes exercise update contention and release of a killed lock holder. Failure injection before replacement preserves the old valid index.

Feedback rejects ambiguous matches and stale source content, deduplicates event IDs, rejects invalid dates/types and requires an evidence reference for confirmation. Same-day confirmation retries do not advance through the whole ladder. Movement/display/retrieval do not earn activity score. High cost and explicit pinning are distinct; migration preserves old high protection until reviewed.

The old CLI names remain. Invalid arguments, missing records and missing source files now fail explicitly. `migrate` previews without writes, preserves original v1 bytes and unknown metadata, and marks unresolved records rather than inventing matches. It does not migrate warm files or alter an installed Hermes instance.

Documentation now includes a complete index, commands, migration, behavior coverage, tests and corrected upstream hook semantics. The old upstream research is preserved as a historical file. Other existing research and audit documents retain their original bytes; the current-state documents explain their dated scope. The document checker now validates JSON source manifests and returns structured errors for failed reads and invalid Python encoding.

## Actual validation

See the [machine-readable record](2026-09-06-engine-hardening.json) and raw [unit-test](2026-09-06-engine-tests.txt) / [numeric-test](2026-09-06-numeric-tests.txt) logs. Counts belong to the exact file hashes recorded there. Unit tests use the actual repaired engine, not a reimplementation of its logic inside tests.

Local execution is Linux/Python 3.13.5. The repaired source, tests and new documents were materialized locally. Unchanged large remote research documents were not downloaded through the container network, so a full-checkout local document-validation pass is not claimed. The CI workflow is the separate path for full-remote-tree document checks and native platform jobs; inspect its actual commit-specific outcome.

## Remaining limits

This is an advisory index CLI. Full tier-moving transactions, semantic retrieval, tokenizer-aware context assembly, automatic revision interpretation, MemoryProvider integration and real-model effectiveness remain unimplemented/unverified here. All tests use synthetic data. No user index, source memory file, live configuration or cron was modified. A confirmation reference is recorded caller evidence, not independently verified by the CLI. Native Windows/macOS and electrical power-loss tests were not executed locally.

The original ten specification tests and old diagnostic report are retained separately. Previously reported private-reference test counts are not attributed to this public implementation. Current usage and remaining work are in the [implementation status](../docs/07-implementation-status.md).
