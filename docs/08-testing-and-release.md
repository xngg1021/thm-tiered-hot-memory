# Testing, document publication and bounded release

## Zero-touch provider gates

Provider/model tests cover public SDK call lifecycles, exact resident reuse, failed allocation cleanup, independent embedding profiles, bounded warm-worker failure, session activation/fallback, queue growth/recycling, driver freshness, and public tokenizer API compatibility with exercised cache hits, and admitted steady-state cutoff guards that avoid full rescoring on separated rankings. Core-only ignition still precedes installation of test-only NumPy/tiktoken in CI. Required workflows include correctness on Linux/Windows/macOS, Hermes and relevant harness integrations. Review, source audit and [matrix](provider-matrix.md) must match the exact final head; hardware and full-dataset runs are not default merge gates.

## Evaluation Fabric release gates

Run `python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01` for bounded offline local acceptance. [Full contract](18-evaluation-fabric.md). Correctness CI executes smoke on Linux/Windows/macOS, unit tests, README structural parity and existing documentation/history gates. Hermes and relevant harness gates remain separate. Full research workflows require manual full_research=true; no full dataset is a default gate. Clean exact-head Codex P1/P2 review and an expected-head normal merge precede post-merge CI. Current package/stable is 1.5.0; its accepted merge, archive and gates are bound in the [final release receipt](../reports/2026-09-12-v1.5-closeout.json).

Run the public checks from the repository root:

```bash
python -m unittest discover -s tests -v
python scripts/thm_numeric_audit.py
python scripts/check_docs.py
python scripts/check_version_history.py
```

The engine tests import `scripts/thm.py` directly and use temporary synthetic source stores. They cover stable IDs, prefix collisions, directory separation, ambiguous updates, invalid dates/events, retry behavior, confirmation scheduling, validity, pins, conflict rejection, write failure, migration and CLI error codes. Independent child processes test concurrent updates and release of a killed lock holder. No real profile or external model is used.

The document-check unit tests use intentionally synthetic documents and a test-specific historical digest. The standalone `check_docs.py` command checks the actual repository, including the original preserved report's fixed Git blob, relative links, JSON files, source-list shape and Python syntax. It accepts additional documents and inspects them rather than blocking every documentation addition with an exact Markdown count. Neither unit tests nor syntax checks certify external facts.

The ten numeric tests preserve the old specification and its counterexamples. A passing assertion that old high-cost entries could not be evicted is a historical diagnostic, not proof of repaired behavior. Current engine/residency tests verify current behavior separately.

## Reproducibility record

The [machine-readable hardening record](../reports/2026-09-06-engine-hardening.json) identifies the earlier engine hardening input, commands, Python version and file hashes. The 1.4 release has its own [machine-readable closeout](../reports/2026-09-07-v1.4-closeout.json), including exact feature/base/merge SHAs, archive pointer and main-workflow run IDs.

Raw local or CI logs do not become broader claims automatically. The GitHub workflows run complete repository checkouts. Workflow presence is not a pass; inspect the exact run for the exact commit. Failed operating-system/integration jobs retain their failures.

## Version acceptance

A package version string alone is not acceptance evidence.

For 1.3, the archive/version history preserves the accepted baseline/integration line as recorded in [version history](12-version-history.md).

For **1.4.0**, the exact accepted implementation/integration milestone is:

```text
e6e4dda5835e3cb345207457d5491131c6959b2c
archive/v1.4.0-stable
```

The accepted merge SHA must have, on that same exact commit:

- cross-platform THM correctness success;
- Hermes provider integration success;
- multi-harness integration success;
- retrieval workflow interpreted according to its path gate.

For 1.4, main runs were correctness `34059895478` = success, Hermes `34059895474` = success, harness `34059895461` = success. Retrieval run `34059936492` was skipped because no retrieval-path files changed. That skip is an explicit **non-result**, not permission to copy an older Protocol 2 number into a new benchmark claim.

1.4 “stable” is deliberately bounded: it certifies the public implementation/integration surface and its read-only/advisory invariants. It does not certify an optimal adaptive policy. Automatic tier/budget mutation remains disabled until separate held-out runtime/task A/B evidence exists.

## 1.4-specific test boundaries

1.4 adds contract/CLI/provider tests for:

- raw vs residency-avoidable miss accounting;
- all-task vs explicit demand-task denominators;
- real per-item minimum-demand evidence gates;
- strict telemetry/catalog schemas and stale identity rejection;
- locator-only T1 directory projection without legacy key/summary/body leakage;
- exact bounded 0/1 packing for the finite token objective;
- current/valid prefetch seed requirements and anti-self-training behavior;
- resident-budget feedback that ignores unavoidable misses as grow pressure;
- opt-in Hermes warm-directory budget/configuration;
- selected locator target existence and in-profile/symlink containment;
- frozen-session directory refresh semantics;
- byte-identical native `MEMORY.md`, `USER.md` and `.thm/index.json` across the new read-only CLI/provider operations.

These tests establish deterministic implementation behavior. They do not show that a warm directory or adaptive recommendation improves real task success.

## Publication inventory

The [document index](README.md) lists the maintained project documents. Existing research/architecture and original reports are retained. The public bundle includes the engine guide, implementation status, retrieval/harness evidence, version history, 1.4 residency-control design/runtime documentation, closeout reports and current tests.

Personal indexes, actual memory text, private residency catalogs/telemetry, configuration, private reference code, mixed-project chat exports and protected third-party project material are not public documents in this repository. Missing private ZIP bytes are not reconstructed or claimed uploaded. Source code and documentation publication does not install the tool or migrate user data.

## Finite next evidence work

The public 1.4 implementation is closed as a stable milestone. The remaining adaptive-policy question is empirical rather than missing core code: compare the stable fixed-budget/activity baseline against shadow recommendations on held-out runtime tasks, measuring task quality together with avoidable miss/reacquisition cost, latency, stale-state failures and prefetch waste. Only after that evidence should automatic T0–T3 or budget mutation be considered.

## Unreleased retrieval successor

The opt-in Python entity projection and its Protocol 2 evidence are documented in [the zero-LLM frontier](16-zero-llm-retrieval-frontier.md). It does not enable a harness option, change residency/activity/validity semantics, or move the 1.4 stable pointer.


## Post-local corrective evidence

See the [current corrective contract and short retest](19-post-local-corrective.md). Z6 CPU/CUDA/auto-throughput and local NTFS/NVMe are machine-observed at b1f8119. Aggregate parity, strict parity, calibrated policy and post-fix acceptance remain separate claims. Auto-safe now allows a measured reference fallback; lack of acceleration does not itself fail correctness. No version/stable promotion or full-dataset acceptance is implied.

## 1.5 implementation and evidence contract

[1.5 implementation surface](24-full-power-implementation.md) defines the executable configured provider/storage lifecycle, allocation and joint-planning APIs, explicit actuator, five benchmark/environment/outcome interfaces, independent CE bridge, and LangGraph/Deep Agents lifecycle. Automatic memory mutation remains false and rejected features remain default-off. Hardware, full-research and real task evidence are separately recorded in the [completion ledger](../reports/2026-09-12-thm-full-power-completion.md).

## 1.5 exact-head release checklist

1. Fetch the sole successor head and immutable archive refs; use a normal forward-only branch.
2. Run correctness on Ubuntu Python 3.10–3.14 and Windows/macOS 3.13, eight tiktoken rows, numeric audit, all five evaluation fixtures, feature A/B and Track B regressions.
3. Run Hermes and all harness lifecycle jobs on that exact head. Check docs, localization, package identity, completion census and version history.
4. Resolve actionable P1/P2 reviews with forward fixes and regressions. Request exact-head review; an evidenced external service outage permits at most two attempts and is recorded separately.
5. Independently fetch current `main` immediately before admission. Validate the fetched snapshot with `scripts/verify_merge_gate.py --expected-head HEAD_SHA --expected-base CURRENT_MAIN_SHA SNAPSHOT`. A changed base invalidates admission: refresh the snapshot and integrate the new base before repeating exact-head CI/review. Re-read PR head/main immediately before the normal GitHub merge with `expected_head_sha`; this API has no atomic expected-base parameter. Verify the returned merge parents using `verify_merge_result(receipt, parents=actual_parents)` before release/archive acceptance. An intervening base change fails that postcondition and requires refreshed evidence and re-admission; no stale admission may authorize an archive.
6. Require successful main correctness, Hermes and harness. Create the new immutable archive at the accepted merge. Record tree/parents, checks and review in a forward-only closeout; verify all prior archives and close implementation PRs.

Remote branch protection could not be administered through the current integration (403). Repo-local checks and guarded merge receipts implement the available discipline, but do not claim server enforcement of no-force-push.

## 1.5 accepted closeout

THM 1.5.0 is implementation/integration stable at `de26865f36df2205c29a470e51c65d5bf9beca4e`, normally merged by PR #21 from `d33fc70677e61d6733fdbc8c0f71bced6168dff4`. The immutable `archive/v1.5.0-stable` pins that accepted implementation main. Exact-head and post-merge correctness, Hermes and harness workflows passed; 669 local unit tests ran with zero failures/errors and 3 expected skips. The 28 domains are implemented with zero external implementation gaps; remaining hardware, target-machine, full-research, private-workload and real-environment work is evidence-only. [Final acceptance receipt](../reports/2026-09-12-v1.5-closeout.json). Remote branch-protection administration remains an integration 403 governance limitation.
