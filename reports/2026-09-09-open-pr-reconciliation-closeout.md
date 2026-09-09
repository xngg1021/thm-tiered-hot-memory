# Repository-wide forward-only reconciliation — 2026-09-09

This receipt is updated forward as exact-head review, guarded merges and post-merge CI complete. It supersedes earlier merge-blocking requirements for real local hardware measurements. The historical PR14 acceptance and PR16 draft receipts retain their original time-point evidence.

## Remote inventory and dependency order

Starting main: `5e03c03584f54e7ed5c868f13d84544e5e82d48f`, tree `60b0502be25186e7642df892fc1959a5d659eac6`.

All 15 pull requests were inspected: #1–#12 and #14 were already merged; #15 and #16 were the only open/Draft/unmerged PRs. #13 is an issue, not a PR. No closed-unmerged PR was found. Thirty remote branches were checked for ancestry/unique changes.

| PR | Purpose / unique content | Starting head | Dependency / overlap | Decision |
| --- | --- | --- | --- | --- |
| #15 | Scope replacement deletes vectors_v2 and vector_generations for every old profile | `3966f25092f319270e9aadaebc1a9a9db8ca0ca0` | Required PR14 correctness fix; absent from original #16 | MERGE first |
| #16 | Bounded verification and orthogonal physical storage; reference closure P1 and Windows locality P2 | `48052fe49e3f92f9df1aa01e4ef5f25c7d94fd4c` | Absorb #15/main with a normal merge; retain physical semantics | FORWARD-FIX-THEN-MERGE |

PR #15 passed exact-head Codex review (comment `5581626498`, reviewed `3966f25092`), zero unresolved threads, correctness PR run `34202825956`, push run `34202822968` and Hermes run `34202823019`. It was marked ready and merged with `expected_head_sha`, merge method `merge`.

PR #15 merge/main: `70180dd4a319c62cc839ee1b7f39b5573b3a1f66`. Its post-merge correctness `34314011517` and Hermes `34314011591` succeeded; retrieval `34314011461` and deterministic frontier `34314011504` were **skipped**, not passed.

PR #16 incorporated that main through normal two-parent merge `4d94bbb067eeb5987619f1764d551b48b98378c4`, tree `62a4a05ab30cbaa3db1561140075f9cd587c1031`, with parents `48052fe49e3f92f9df1aa01e4ef5f25c7d94fd4c` and `70180dd4a319c62cc839ee1b7f39b5573b3a1f66`. No rebase, squash, reset, force-push or published-history rewrite was used.

The unmerged branch-only experiments are outside current release scope: `work/compact-packing-20260907@8cd362675130152004e1a324d25a9613a8bc94a5` only changes source-label JSON whitespace; `work/retrieval-rerank-packing-20260907@1e9f7fb75803e33aa7470f59f47d6f981b1bde76` contains an isolated reranking/ablation experiment. Its metadata-weight fix `ca5a3f661a0ac66fa10417f91413f26fc43aa60e` affects only the experimental `thm/rerank.py`, absent from the authoritative production path. Neither strands a required production correctness fix. These histories remain preserved; neither has an open PR to close.

## Correctness corrections

- Reference-reuse protocol 3 hashes an explicit deterministic transitive local import manifest rooted at both benchmark runners and their subprocess worker. Source construction, evidence credit, SQLite/vector identity, scoring, ranking, packing and tokenizer implementation are covered; installed tiktoken version is separately bound. Future static local imports join the closure automatically; missing dependencies fail closed. Only documented worker calibration/conversion edges are excluded. Mutation regressions cover every included module and nonsemantic docs/storage-probe/physical-benchmark/scheduler exclusions.
- Windows public MSFT_Disk bus evidence admits local NVMe/SATA/SAS/USB (numeric and named values); network transports remain remote and ambiguous/virtual/unresolved disks unknown. Parser-to-planner regression proves local-only NVMe selection with measured costs and the other constraints satisfied.
- Scope replacement clears physical placement pointers in the same transaction as vectors_v2/vector_generations. No-op and failed replacements preserve them; other scopes and immutable files remain intact.

Local candidate validation: 417 unit tests passed; headless core ignition, ten numeric audit checks, docs, version-history and whitespace checks passed. Exact final candidate/main identities, CI and completed review receipts are recorded below when available, without treating pending runs as success.

## Acceptance and remaining evidence

Package remains `1.4.0`; new runtime/storage capabilities remain **Unreleased**. Stable archive remains `archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`. Real Z6 G4 speed/dispatch, full 500-instance LME, CXL/GDS/SPDK and other specialized transport performance, and retrieval-feature quality gain remain pending post-merge evidence. No hardware superiority or default feature admission follows from CI.

Short optional local acceptance, using existing local model/data and a fresh output directory:

```sh
python research/runtime/verify.py --mode smoke --model-path /local/model --model-id sentence-transformers/all-MiniLM-L6-v2 --locomo-dataset /local/locomo10.json --lme-dataset /local/longmemeval_s.json --output-dir /fresh/thm-smoke
```

Explicit optional full research (not run for this closeout):

```sh
python research/runtime/verify.py --full-campaign --acknowledge-multi-hour-run --wall-seconds 43200 --retrieval-ab --model-path /local/model --model-id sentence-transformers/all-MiniLM-L6-v2 --locomo-dataset /local/locomo10.json --lme-dataset /local/longmemeval_s.json --output-dir /fresh/thm-full
```

The 43,200-second value is a ceiling, not a measured prediction. Bounded acceptance defaults to five LME instances; smoke uses two. Performance measurements are not required to merge correctness-safe implementation.
