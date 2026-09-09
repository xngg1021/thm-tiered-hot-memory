# Draft PR: bounded verification and orthogonal physical storage

The previous verification entry point ran full LongMemEval for every reference and winner. On the reported target machine that turned ordinary local verification into an 8–12 hour campaign. This successor introduces explicit smoke/acceptance/full-research modes, pilot-based refusal and a whole-process-tree wall ceiling. Default acceptance uses five fixed LME instances; full research requires both explicit flags. Reference reuse is exact-key and provenance-bearing.

The production addition separates source/segment identity, representations, transfers and allocations. Conservative public OS probes feed storage targets and measured bounded cost profiles. SQLite keeps control metadata and FTS; optional contiguous immutable vector files provide buffered/mmap data reads. Explicit migration checks content and generation before publishing a manifest and preserves the source by default. Receipt-first execution planning binds the physical representation to an existing complete runtime profile. T0–T3, source validity and semantic demand remain independent.

## Authority and publication boundary

- Repository: `xngg1021/thm-tiered-hot-memory`.
- Branch: `work/high-resolution-physical-storage-fabric-20260909`.
- Verified predecessor main: `5e03c03584f54e7ed5c868f13d84544e5e82d48f`.
- Predecessor tree: `60b0502be25186e7642df892fc1959a5d659eac6`.
- PR14 merge remains an ancestor: `e6227cc5f6308bc2903222adfdbb1ee814053938`.
- Stable archive remains `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`.
- Package line remains `1.4.0`; successor remains Unreleased.
- No merge, rebase, reset, history rewrite or stable-pointer movement.

Automatic approval review rejected the initial branch push, stating that it had not identified clear end-user authorization for external publication of the committed payload. No alternate publication route was attempted. This document is the concrete draft PR payload prepared locally; the remote Draft PR, CI runs and exact-head Codex review remain pending publication authorization.

## Validation scope

Local deterministic coverage includes format corruption with recomputed checksums, BLOB/segment and mmap/buffered parity, stale generation refusal, all six requested migration interruption stages with database reopen, source retention, physical-read/semantic-state isolation, role/constraint planning, public parser fixtures, process deadline retention, reference reuse invalidation and complete-profile execution planning. The existing full regression suite, headless probe, numeric audit, document checks, version-history check and whitespace gate are required on the final local commit before handoff.

The existing correctness workflow already defines Ubuntu/Python 3.10, Windows/Python 3.13 and macOS/Python 3.13. Its existence does not establish new-head CI success. No new remote CI or independent exact-head reviewer result is credited yet. No full LME campaign, generative LLM call, backend installation or real workstation performance experiment was performed.

## Implemented versus pending

The executable physical backend is a portable local regular-file adapter with buffered/mmap reads, contiguous vector shards and explicit migration. Enterprise/media extension descriptors are not native implementations. Archive pricing/durability and unmeasured latency/write-amplification constraints fail closed. The validated matrix is materialized in DRAM; zero-copy/GPU-direct performance is not claimed. Detailed HMAT/CDAT, processor-group and hardware-specific fabric observations remain incomplete or unknown. Device power-loss durability and target-machine performance remain unvalidated.

[Architecture, backend matrix, CLI, bounded commands and evidence limits](../docs/physical-storage-fabric.md).

After publication, leave the PR in Draft, run the existing three-platform correctness matrix and request Codex review on the exact head. Fix concrete P1/P2 findings forward-only, repeat required gates on any changed head, and stop without merging or declaring stable acceptance.
