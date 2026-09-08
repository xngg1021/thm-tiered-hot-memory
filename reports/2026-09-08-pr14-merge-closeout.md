# PR #14 merge closeout — zero-LLM heterogeneous runtime

Date: 2026-09-08

Status: **MERGED TO MAIN / SOFTWARE CONTRACTS ACCEPTED FOR MAIN / REAL LOCAL HARDWARE AND FEATURE-QUALITY EVIDENCE PENDING**

Repository: `xngg1021/thm-tiered-hot-memory`

PR: `#14` — `Unreleased zero-LLM heterogeneous runtime and local acceptance package`

## Immutable identity

- predecessor `main`: `9eb904c21fd25aa0a77d2420ed080702fac17e59`
- final PR source head: `0b90efe54de3a39d2021540575fcb012753cceed`
- final PR source tree: `85867f7cc81e321680238fba1e6d904f998bc9db`
- normal merge commit: `e6227cc5f6308bc2903222adfdbb1ee814053938`
- merge parents: `9eb904c21fd25aa0a77d2420ed080702fac17e59`, `0b90efe54de3a39d2021540575fcb012753cceed`
- stable archive remains: `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`
- package line remains: `1.4.0`
- runtime/retrieval successor status: `Unreleased`

No rebase, reset, amend, force-push, squash merge or stable-pointer move was used for this closeout.

## Source-head verification

The final source head records:

- 393 local regression tests passing;
- core-only no-network/no-tensor/provider ignition passing direct recall and MCP initialize/tools/list/status/recall;
- numeric audit passing;
- documentation checks passing;
- version-history checks passing;
- whitespace checks passing;
- exact-head PR correctness run `34200520158` green on Ubuntu/Python 3.10, macOS/Python 3.13 and Windows/Python 3.13;
- exact-head push correctness run `34200514166` green.

The completed review history before the merge contained 45 actionable findings, 1 P1 and 44 P2, all forward-fixed and resolved. The final source-head corrections make calibration scorer measurements follow the configured query chunks and make source timestamp parsing accept adapter/Hermes ISO datetimes before explicit English/date fallback.

A duplicate exact-head Codex review request was still running against the already verified same source SHA when the user explicitly authorized the merge. It had not produced a new unresolved thread at the merge point. This closeout therefore does **not** claim a separate final reviewer approval state beyond the resolved 45-finding history and exact-head correctness evidence above.

## What entering `main` means

The merge accepts the implementation and compatibility contracts into the current development line, including:

- conservative hardware/runtime probing;
- explicit embedding/runtime profile identity;
- local Torch / ONNX Runtime / OpenVINO execution contracts;
- non-destructive vector/profile coexistence and optional float32 BLOB storage;
- exact-input embedding cache with scope/profile identity;
- source-generation-checked publication;
- bounded query/document batching and calibrated scorer paths;
- CPU lexical preparation / encoder overlap;
- isolated bounded AutoTune and semantic gates;
- session-pinned / throughput scheduler behavior and explicit sparse fallback;
- zero-generative-LLM headless operation;
- typed default-off temporal, alias, segment and association retrieval successors;
- the one-shot local verification package and its evidence receipts.

The merge does not change the meaning of THM T0–T3, activity, validity, residency, explicit demand or the existing advisory/nonmutating residency plane.

## What entering `main` does not mean

No merge-time evidence establishes:

- local Xeon 6254 speedup;
- RTX 3080 speedup;
- actual AVX2 / AVX-512 / VNNI kernel dispatch;
- actual CUDA / ORT / OpenVINO winner on the target workstation;
- strict CPU/GPU semantic equivalence for a measured full matrix;
- safety/equivalence of an approximate-performance profile;
- quality improvement from the new default-off retrieval features;
- generated-answer accuracy;
- a universal optimal hardware/runtime profile;
- a new stable/release designation.

Those claims remain `pending-real-local-runtime` until measured on the target machine with pinned datasets and immutable receipts.

## Next acceptance step

Run the post-merge local procedure in:

`reports/2026-09-08-post-merge-local-runtime-acceptance.md`

The intended first target is the HP Z6 G4 with Xeon Gold 6254 and RTX 3080 10 GB. The runbook keeps the original dataset hashes, requires a clean checkout and fresh output namespaces, separates reference / auto-safe / auto-throughput / approximate policies, and lists the artifacts that can be returned for review after manual privacy inspection.

A failed local run remains evidence. Do not overwrite its output directory; rerun into a new namespace.
