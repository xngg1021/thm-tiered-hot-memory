# THM recall hardening publication status — 2026-09-06

The follow-up recall hardening package has now been published to `main`.

- Baseline: `e7c6b9d1c93811d5bb0b735e223658a4d205d360`
- First publication commit: `998f0ea40e8d9b9d5cfd26b2c9dda2a55109f3a4`
- Published tree: `8c84d4926fc1383c58299055c0e09699eed9405f`
- Publication was a non-forced fast-forward of `main`.

The package includes the patched recall, source, scan, residency-policy and Hermes-provider modules; protocol-2 evaluation code; the performance probe; new regression tests; integration-review documentation; local test evidence; and the historical protocol-1 benchmark summary. No personal memory, private HF material, model weights or credentials were included.

`docs/10-recall-integration-review.md` and `reports/2026-09-06-recall-review.json` preserve the pre-publication local verification state, including the statement that the patch had not yet been pushed at the time that record was created. This file is the successor publication record and must be used for current synchronization status.

Publication does not convert unrun checks into evidence. In particular, corrected protocol-2 full LoCoMo, a live installed-Hermes lifecycle run, real-user end-to-end QA, and user-specific decay calibration remain separate validations. Exact-commit GitHub CI status must be read from the workflow run for the final publication tip.
