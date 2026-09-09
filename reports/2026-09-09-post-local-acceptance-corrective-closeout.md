# Post-local corrective closeout — merged, hardware follow-up pending

PR #18 is normally merged. The final closeout below supersedes the retained historical checkpoints. Post-fix hardware acceptance remains pending.

## Historical checkpoint before authorized publication

The following checkpoint recorded the then-incomplete remote lifecycle; its pending publication/review/merge statements are historical, not current status.

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

## Initial approval block (historical, now resolved)

Automatic approval review rejected the `git push` operation. Its stated reason was that repository code, documentation and potentially sensitive machine/evidence artifacts would be disclosed to a destination without trusted end-user authorization for that payload/destination. The supplied attachment was not accepted by that review as sufficient authorization. No alternate publishing route was attempted.

A subsequent read-only `git ls-remote` confirmed main still at `aa8391e` and the corrective branch absent. No PR was created, no remote CI credited, no Codex exact-head review requested, and no merge performed. These remain explicit incomplete gates. Issue #13 has not been modified; its ready-to-post ledger follows below. The user subsequently explicitly authorized pushing and completing the remaining lifecycle. This initial block is resolved; the following resumption record supersedes its pending-publication state.

## Ready-to-post issue #13 evidence ledger

Tested SHA: `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`; evidence commit: `aa8391ebe506c38536dce787192d4d305ac335e1`.

Established: real CPU reference, real CUDA reference, real auto-throughput, actual query_batch=8 execution, CPU/GPU aggregate parity and strict mismatch evidence, embedding/E2E bottleneck separation, local NTFS/NVMe StorageProfile and bounded estimator refusals. These are original-machine results, not post-corrective results.

Implemented locally: corrected auto-safe admission/reference fallback, deterministic candidate plan, redacted preparation diagnostics, bounded CPU sweep, optional dispatch-log observation and short retest. Pending: push/CI/exact-head review/merge; controlled sweep on Z6; positively observed AVX2/AVX512/VNNI dispatch and clock evidence; ORT/OpenVINO real success; INT8 independent quality; post-corrective machine evidence. Keep #13 open.

## Short local follow-up after merge

See [the exact commands and scope](../docs/19-post-local-corrective.md#short-local-retest). The corrective retest has a 600-second process-tree ceiling; optional CPU sweep adds 240 seconds. Neither requires LoCoMo/LME matrices. Post-fix real-hardware acceptance remains pending, including unresolved legacy forensic components and ORT root cause.


## Authorized remote resumption

The user directly authorized push and completion. CLI Git lacked a write credential, so the authenticated GitHub API published six ordered commits, verifying each tree against its local counterpart. Author metadata caused different commit SHAs; no published history was rewritten. Initial remote reviewed head: `96a9d3df15acd2b11c9b2f24362654994c4f097a`, tree `aac88f91fd6ad52ba3d870ce91c9dfb7ff898bf8`.

[PR #18](https://github.com/xngg1021/thm-tiered-hot-memory/pull/18) is open. [Issue #13 ledger](https://github.com/xngg1021/thm-tiered-hot-memory/issues/13#issuecomment-5601608941) was posted and the issue remains open. Exact-head Codex review was requested. Local current-code checks passed with 468 tests, headless, numeric, docs, version and whitespace gates. The explicit reference policy additionally remains pinned to its requested device and fixed scorer.

First-head Hermes run 34349475238 and harness run 34349475199 passed. Ubuntu passed in correctness run 34349518299; macOS exposed a test fixture counting OS probe subprocesses as matrix executions. The forward correction restricts the fixture counter to commands with matrix output, without changing production retrieval or masking an executed matrix. Integration workflows now include this regression file in their trigger paths so the corrected head gets fresh integration evidence. Final CI/review/merge results will be appended after their actual completion.


Additional forward evidence hardening separates a calibrated throughput candidate from measured speedup, preserves an execution-before-plan ordering guarantee for the standalone CLI, and prioritizes affected IDs inside bounded forensic rows. Cutoff rank is no longer conflated with selected count. Reference dependency closure remains unchanged. These corrections have dedicated regressions and will receive a fresh exact-head review.


## Exact-head review correction

Codex review 5154160682 on `e1552b8975a0609442dd887bb885d70070cbd108` found one actionable P2: matrix runners emit `timing_breakdown_ms`, while the new decomposition helper read `timing_ms`. The forward fix reads the actual matrix field, retains compatibility with direct SearchIndex rows, and reports unknown rather than zero when component clocks are missing. Regressions exercise both actual bounded LoCoMo and LME runner outputs, plus absent/partial timing rows. This changes only evidence aggregation, not retrieval semantics. The corrected head must pass a fresh review and CI before merging.


The next exact-head review found a second P2 on shared batch timing. The subsequent forward fix separately aggregates each complete batch receipt once by native chunk size and matrix loading once per scope/mode/budget call. Equal timing values do not collapse distinct batches, and incomplete chunks remain unresolved. Regressions exercise real multi-chunk SearchIndex output and identical-clock/partial-chunk fixtures. Retrieval and reference dependency keys remain unchanged.


## Final corrective merge closeout

### Exact identities and ancestry

| Identity | Commit | Tree |
| --- | --- | --- |
| Predecessor main / historical evidence commit | `aa8391ebe506c38536dce787192d4d305ac335e1` | `f72642b512eca274202aa494fbf9809d4722f691` |
| Final reviewed and tested code HEAD | `d4c566efbca5dbcbfe0ac1e3b92fd45a93b86d08` | `7d7a5202b4a9aa6abf63e48e622dfa7c5571621a` |
| Final production main / normal merge anchor | `1db685fe762b4bab9c66e8ace9bed5cc116afb43` | `7d7a5202b4a9aa6abf63e48e622dfa7c5571621a` |

Merge parents are exactly the predecessor and final reviewed HEAD above. GitHub accepted the expected-head guard; no squash, rebase or force update occurred. The merge tree equals the reviewed tree. The actual machine-tested source remains `b1f81192179fafc31c12b7d7c9e5c4210ce9cfd1`, not this corrective source.

This closeout and a stale smoke-table sentence are a documentation-only forward successor. Its own commit/tree cannot be embedded in its content without changing that identity. The [final main identity and post-merge validation ledger](https://github.com/xngg1021/thm-tiered-hot-memory/pull/18#issuecomment-5602127037) records that final administrative main SHA/tree, its exact file delta and actual completed CI results. The production merge anchor above stays immutable.

### Final gates and review disposition

- Final local suite: **475 tests passed**, repeated on the merged checkout (9.106 seconds); headless probe has zero generation/provider/network calls. Numeric, documentation/localization, version/history and whitespace gates passed on the reviewed head; documentation gates are rerun for this closeout.
- Exact reviewed-head correctness: [push 34352411670](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34352411670) and [PR 34352416732](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34352416732), both SUCCESS across Ubuntu/Python 3.10, Windows/Python 3.13 and macOS/Python 3.13.
- Exact reviewed-head integrations: [Hermes 34352411583](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34352411583) and [harness 34352411563](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34352411563), both SUCCESS.
- [Final Codex review](https://github.com/xngg1021/thm-tiered-hot-memory/pull/18#issuecomment-5602080131) explicitly identifies `d4c566efbc` and found no major issues. Both actionable P2 threads were forward-fixed, regressed and resolved before merge. No unresolved review thread remained.
- Post-merge main gates: [correctness 34353439155](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34353439155), [Hermes 34353439261](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34353439261), [harness 34353439222](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34353439222). Hermes and harness already completed successfully at document preparation; correctness and final documentation-commit outcomes are bound in the final ledger linked above, after actual completion.

The two review defects were native matrix timing-field mismatch and omitted shared batch clocks. Their final fixes consume `timing_breakdown_ms`, retain direct-row compatibility, expose absent clocks as unknown, and aggregate shared clocks once per complete batch and matrix load once per call. Read-only recomputation of original throughput LoCoMo receipts found 23,832 rows, 1,518 batches, 60 calls / matrix loads and zero unresolved batch rows. Raw row clocks retain inclusive/amortized semantics; they are not additive with shared totals.

### Admission, fallback and evidence contract

FP32 numeric sanity uses `2*gamma(2*d+1)`, with unit roundoff `2^-24`; at dimension 384 this is approximately `9.17e-5`. This is a deterministic sanity envelope, not a universal transformer-error proof. Tiny numeric changes pass only with exact ranked/selected IDs, packed evidence identity/hash/source/completeness and budget. Bitwise equality is a separate diagnostic. Retrieval sorting, fusion and packing semantics were not changed.

A successful reference remains calibrated fallback when no faster safe candidate exists; no acceleration is claimed. Explicit reference policy remains fixed to its requested device/scorer. Throughput drift and measured speedup have separate fields. Cap-independent candidate plans, baseline ordinal zero, backend/device/scorer representatives, skip reasons, source-bound within-run reference reuse and process-tree deadlines remain enforced. Smoke skips preparation and optional accelerated trials and promotes its identical reference pilot.

The 48-artifact inventory, CUDA 23/3 versus throughput 5/0 strict/selected-set counts, aggregate equivalence and legacy missing forensic fields retain their historical evidence boundaries. ORT's original generic failure cause remains unresolved; new structured stage/category diagnostics permit a targeted follow-up without inventing a diagnosis. No new multi-hour matrix or real Z6 measurement was run. Reference semantic dependency closure, raw machine receipts, VERSION, stable/archive 1.4.0 and private cross-run cache-key requirements are unchanged.

### Issue delta and final gap audit

All current open issues and PRs were inspected. PR #18 is merged, no open corrective PR remains, and #13 is the only open issue. Its body and checklist now distinguish established CPU/CUDA/throughput/query_batch=8 and NTFS/NVMe observations from the remaining controlled CPU batch sweep, positive ISA/clock dispatch evidence, ORT/OpenVINO success, INT8 quality and post-fix Z6 acceptance.

The final repository search covered no-candidate-passed, strict/exact parity, score_tolerance, auto-safe/throughput, pending-local labels, open-PR claims, rank-only drift, AVX512/VNNI/observed dispatch, ORT preparation and full-LME requirements. Current English and seven localized READMEs retain the corrected evidence boundary. The final remaining current-doc mismatch was the storage smoke table's old preparation/two-trial/winner description; its documentation-only correction matches the reviewed implementation. Historical reports and checkpoints remain identifiable as historical and are superseded through forward corrections.

### Targeted machine follow-up

Use the merged checkout and existing local model, with new output directories:

```powershell
python -m research.runtime.corrective_retest --model-path MODEL_DIRECTORY --model-id sentence-transformers/all-MiniLM-L6-v2 --output-dir NEW_RETEST_DIRECTORY --wall-seconds 600 --prepare-ort
```

Optional controlled CPU sweep:

```powershell
python -m research.runtime.query_batch --model-path MODEL_DIRECTORY --model-id sentence-transformers/all-MiniLM-L6-v2 --output-dir NEW_BATCH_DIRECTORY --wall-seconds 240
```

Total requested process ceilings are 14 minutes. No LoCoMo/LME matrix is required. The exact [scope and interpretation](../docs/19-post-local-corrective.md#short-local-retest) remain controlling; these commands do not establish full-dataset acceptance. Issue #13 remains open until its actual evidence requirements are met.
