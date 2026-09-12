# Testing, document publication and bounded release

## Zero-touch provider gates

Provider/model tests cover public SDK call lifecycles, exact resident reuse, failed allocation cleanup, independent embedding profiles, bounded warm-worker failure, session activation/fallback, queue growth/recycling, driver freshness, and public tokenizer API compatibility with exercised cache hits, and admitted steady-state cutoff guards that avoid full rescoring on separated rankings. Core-only ignition still precedes installation of test-only NumPy/tiktoken in CI. Required workflows include correctness on Linux/Windows/macOS, Hermes and relevant harness integrations. Review, source audit and [matrix](provider-matrix.md) must match the exact final head; hardware and full-dataset runs are not default merge gates.

## Evaluation Fabric release gates

Run `python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01` for bounded offline local acceptance. [Full contract](18-evaluation-fabric.md). Correctness CI executes smoke on Linux/Windows/macOS, unit tests, README structural parity and existing documentation/history gates. Hermes and relevant harness gates remain separate. Full research workflows require manual full_research=true; no full dataset is a default gate. Clean exact-head Codex P1/P2 review and an expected-head normal merge precede post-merge CI. Package/stable remains 1.4.0.

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
