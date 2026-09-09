# Repository-wide forward-only reconciliation — 2026-09-09

Code reconciliation is complete: both required PRs are normally merged, all seven actionable P1/P2 findings are resolved, exact-head Codex review is clean, and post-merge main correctness/integrations pass. This receipt supersedes earlier merge-blocking requirements for real local hardware measurements. The historical PR14 acceptance and PR16 draft receipts retain their original time-point evidence.

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

First forward-fix head `3c5f6e81173e5cd6a494b57c5b1b07c1a2b029fa`, tree `6cbd75e2e255a6ed7435d68d593080baa146ff65`, passed 417 local tests, correctness PR `34314841331` and push `34314838121` (all three OSes), and Hermes `34314838059`. Retrieval `34314838109` and frontier `34314838099` were skipped. Codex review `PRR_kwDOUP17J88AAAABMvk4HQ` found a P1 same-generation re-embed/export publication race and a P2 macOS locality gap, so this head was not merged. The next forward fix revalidates the exact vector snapshot within the publication write transaction and admits positively observed macOS local buses conservatively. Regressions cover JSON/BLOB re-embedding from a second database connection while retaining its newer placement, plus macOS parser-to-planner locality.

Validation includes the full unit suite, headless core ignition, ten numeric audit checks, docs, version-history and whitespace checks. Final candidate/main identities and completed CI/review evidence follow below; prior failed review candidates remain explicitly historical.

Second forward-fix head `216b3706c0068173c8fe53fb980e61b595598463`, tree `7f068c5078c910c14a92622c4c570fac16a01a16`, passed 419 tests, correctness PR `34315736073`, push `34315733812` and Hermes `34315733771`; retrieval `34315733776` and frontier `34315733748` were skipped. Codex review `PRR_kwDOUP17J88AAAABMvqnxw` completed with three actionable P2s, so this head was not merged: resolve a macOS descendant to its actual volume before diskutil, avoid Linux filesystem-only locality inference, and protect physical objects shared across retrieval databases from retirement.

The next forward fix adds a tested df-to-diskutil command path, conservative sysfs transport/stacked-backing locality, and exclusive canonical-index root ownership. New roots refuse foreign publications and loads; existing unowned/shared roots remain readable and copyable but cannot be claimed or retired. Two-database regressions cover identical objects in foreign owned destinations and preservation of legacy shared publications. Source-retirement crash recovery still runs through all six checkpoints.

## Final merges, review and main validation

| Item | Exact identity / result |
| --- | --- |
| PR #15 source head | `3966f25092f319270e9aadaebc1a9a9db8ca0ca0` |
| PR #15 normal merge | `70180dd4a319c62cc839ee1b7f39b5573b3a1f66` |
| PR #16 final reviewed source head | `65d63c9cbd75fa65acaf2ed84bf3988d2dcfc073` |
| PR #16 source tree | `209b0082ed0a09d1e71bf6817d035eba642c79a0` |
| Ending implementation main / PR #16 normal merge | `3512aa02015d6eb10e390e1fe7f06309fd84b6c6` |
| Ending implementation main tree | `209b0082ed0a09d1e71bf6817d035eba642c79a0` |
| Merge parents, in order | `70180dd4a319c62cc839ee1b7f39b5573b3a1f66`, `65d63c9cbd75fa65acaf2ed84bf3988d2dcfc073` |
| Exact-head Codex review | [Clean review comment 5596701439](https://github.com/xngg1021/thm-tiered-hot-memory/pull/16#issuecomment-5596701439), reviewed `65d63c9cbd`; completed 2026-09-09 06:07:51 UTC |
| Review threads | 7 actionable findings forward-fixed (2 P1, 5 P2); all resolved before merge; zero unresolved |
| Tests | 424 unit tests on the exact reviewed source and again on merged main; all required local gates passed |
| Remaining Open/Draft/unmerged PRs | 0; all 15 PR source heads independently verified as ancestors of main |
| Closed as superseded/obsolete in this task | None needed; #15 and #16 each contained required unique work and were merged |

Both merge operations used `merge_method=merge` and the exact `expected_head_sha` guard. The merged source tree equals the reviewed tree. PR #15 is the first parent of the final implementation merge, so its cleanup cannot be stranded on a sibling branch.

| Exact commit | Workflow | Run | Result |
| --- | --- | --- | --- |
| `65d63c9cbd` | Correctness PR: Ubuntu 3.10, Windows 3.13, macOS 3.13 | [34317141241](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317141241) | success, all 3 jobs |
| `65d63c9cbd` | Correctness push | [34317138553](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317138553) | success |
| `65d63c9cbd` | Hermes integration | [34317138599](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317138599) | success |
| `65d63c9cbd` | Retrieval / deterministic frontier | `34317138471` / `34317138474` | skipped, not passed |
| `3512aa0201` | Post-merge correctness: Ubuntu 3.10, Windows 3.13, macOS 3.13 | [34317795502](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317795502) | success, all 3 jobs |
| `3512aa0201` | Post-merge Hermes integration | [34317795505](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317795505) | success |
| `3512aa0201` | Post-merge harness integrations | [34317795507](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34317795507) | success: Python harnesses, Codex CLI, Claude Code, Gemini CLI, OpenClaw MCP |
| `3512aa0201` | Retrieval / deterministic frontier | `34317795601` / `34317795506` | skipped, not passed |

Final local commands passed on merged main: `python -S scripts/runtime_headless_probe.py`, `python -m unittest discover -s tests -v`, `python scripts/thm_numeric_audit.py`, `python scripts/check_docs.py`, `python scripts/check_version_history.py`, and `git diff --check`. The headless probe reports zero generation/provider/network calls. Historical evidence remains preserved.

This completed receipt and the implementation-status update are published as a documentation-only forward successor of the validated implementation main. Its **exact final repository main/tree and post-publication CI** are recorded in the linked [final publication receipt](https://github.com/xngg1021/thm-tiered-hot-memory/pull/16#issuecomment-5596725956). A Git commit cannot literally contain its own final hash or its future CI run IDs; that linked receipt binds the documentation publication without rewriting history or falsely labeling the preceding code merge as the last documentation commit.

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
