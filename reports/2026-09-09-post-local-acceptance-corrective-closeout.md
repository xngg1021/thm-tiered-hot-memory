# Post-local corrective checkpoint — local gates passed, remote lifecycle blocked

This is a forward-only checkpoint, **not a completed merge or post-fix hardware acceptance**.

## Authority and implementation identity

- Repository: `xngg1021/thm-tiered-hot-memory`.
- Confirmed predecessor main: `aa8391ebe506c38536dce787192d4d305ac335e1`.
- Predecessor tree: `f72642b512eca274202aa494fbf9809d4722f691`.
- Actually tested Z6 production SHA: `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`.
- Branch: `work/post-local-acceptance-runtime-corrective-20260909`.
- Implementation head before this checkpoint-only commit: `ab2e2e83af187b9b6064282b5b34a29cc5236725`.
- Implementation tree: `ec70403a1847ccf8f0d7b61db770e1fbd3f44d7c`.
- Local commits: `12d2d38` admission/fallback, `0a774b5` diagnostics/retest, `fa9a4cf` documentation, `ab2e2e8` follow-up hardening and raw-artifact audit.
- Stable/archive/package remain 1.4.0; no raw historical receipt changed.

## Evidence audited and defects repaired

All 48 JSON/gzip machine artifacts decoded. [SHA-256 inventory and recomputed parity](2026-09-09-post-local-artifact-audit.json) bind every input. Recomputing full stored LoCoMo matrices involved no model or benchmark execution. CUDA: 23 strict rows, 3 selected-set changes; throughput: 5 strict rows, 0 selected-set changes. Both aggregate projections remain equivalent. CUDA's remaining 20 strict rows are same-set-different-order in the new disjoint taxonomy.

The old six-candidate plan substituted torch_cpu at ordinal 5; the twelve-candidate plan retained numpy_reference there. This deterministic difference explains why their fifth candidates cannot be treated as identical. The historical zero-tolerance gate rejected score changes near 1e-7.

Implemented numeric/structural/semantic parity layers with a deterministic FP32 sanity envelope and strict ranked/selected/packed identity/completeness/budget checks. Successful reference measurement self-validates and remains a calibrated fallback when no faster safe candidate exists. Acceleration, correctness, approximate policy and full-dataset claims are separate. Throughput drift remains explicitly non-strict.

Candidate plans are cap-independent, include baseline and representative backend/device/scorer classes, and expose skip/execution/admission reasons. Smoke skips export/accelerated trials, calibrates baseline and promotes the exact pilot bytes without a second matrix run. Within-run reference reuse hashes the receipt and binds its configuration/source/hardware/software identity. Source changes miss the cache. Deadline/full-research/immutable-output guards remain in place.

Preparation failure reports now include redacted stage/category, backend and dependency state. Historical ORT failure cause remains unresolved. Bounded forensic rows prioritize structural mismatches over numeric-only differences; dense scores/ranks/cutoffs are preserved, absent legacy sparse/fused values stay null. Optional raw oneDNN execution-log observation preserves unknown dispatch when only capability banners exist. Controlled CPU batch sizes 1/4/8/32 have a separate local-only microbench. Timing summaries state nested/overlapping stage semantics.

English and seven localized READMEs, current validation/status/testing/runtime/evaluation/storage docs, changelog and the historical report's forward addendum were reconciled. The current reference transitive import manifest has **zero changed files** relative to the predecessor, so expensive protocol-3 reference artifacts are not invalidated. Cross-run reuse still requires the exact private sidecar key; keys were not weakened.

## Local validation

- 467 unit/regression tests passed (including 15 new corrective regressions).
- Core-only headless probe passed, zero generation/provider/network calls.
- Numeric audit passed.
- Documentation and localized section checks passed.
- Version-history/archive checks passed.
- `git diff --check` passed.
- Historical raw artifact directory and VERSION unchanged; reference semantic closure unchanged.
- No multi-hour campaign or new Z6 measurement was executed.

## Remote lifecycle and approval block

Automatic approval review rejected the `git push` operation. Its stated reason was that repository code, documentation and potentially sensitive machine/evidence artifacts would be disclosed to a destination without trusted end-user authorization for that payload/destination. The supplied attachment was not accepted by that review as sufficient authorization. No alternate publishing route was attempted.

A subsequent read-only `git ls-remote` confirmed main still at `aa8391e` and the corrective branch absent. No PR was created, no remote CI credited, no Codex exact-head review requested, and no merge performed. These remain explicit incomplete gates. Issue #13 has not been modified; its ready-to-post ledger follows below. Continue only after the user explicitly confirms pushing this branch/payload to this repository and the requested review/guarded-merge lifecycle.

## Ready-to-post issue #13 evidence ledger

Tested SHA: `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`; evidence commit: `aa8391ebe506c38536dce787192d4d305ac335e1`.

Established: real CPU reference, real CUDA reference, real auto-throughput, actual query_batch=8 execution, CPU/GPU aggregate parity and strict mismatch evidence, embedding/E2E bottleneck separation, local NTFS/NVMe StorageProfile and bounded estimator refusals. These are original-machine results, not post-corrective results.

Implemented locally: corrected auto-safe admission/reference fallback, deterministic candidate plan, redacted preparation diagnostics, bounded CPU sweep, optional dispatch-log observation and short retest. Pending: push/CI/exact-head review/merge; controlled sweep on Z6; positively observed AVX2/AVX512/VNNI dispatch and clock evidence; ORT/OpenVINO real success; INT8 independent quality; post-corrective machine evidence. Keep #13 open.

## Short local follow-up after merge

See [the exact commands and scope](../docs/19-post-local-corrective.md#short-local-retest). The corrective retest has a 600-second process-tree ceiling; optional CPU sweep adds 240 seconds. Neither requires LoCoMo/LME matrices. Post-fix real-hardware acceptance remains pending, including unresolved legacy forensic components and ORT root cause.
