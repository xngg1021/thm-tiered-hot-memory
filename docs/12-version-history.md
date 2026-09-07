# Version history and exact recovery map

This document maps the repository's explicit historical milestones to exact Git commits and immutable-by-policy archive branches. Git commit identity is authoritative. Version strings are recorded only when the repository itself contains explicit evidence for that version.

Machine-readable source: [`versions/history.json`](../versions/history.json).

## Current stable milestone

THM **1.4.0** is accepted as an implementation/integration stable milestone at:

```text
e6e4dda5835e3cb345207457d5491131c6959b2c
```

Recovery pointer:

```text
archive/v1.4.0-stable
```

Feature PR #5 merged the 1.4 line from feature head `a1bd23d6abfa1181327d9ec23887cf3903be3ea0` without squashing or rebasing the 11 semantic feature commits. The accepted merge SHA then passed main-branch correctness (`34059895478`), Hermes integration (`34059895474`) and multi-harness integration (`34059895461`). Retrieval benchmark run `34059936492` was **skipped by the retrieval-path gate** because 1.4 did not change retrieval-path files; that skip is not a new Protocol 2 result.

Formal evidence: [1.4 closeout](../reports/2026-09-07-v1.4-closeout.md) · [machine-readable closeout](../reports/2026-09-07-v1.4-closeout.json).

“Stable” here means the public 1.4 implementation, read-only/advisory control boundaries, Hermes opt-in T1 locator projection and integrations reached an exact, tested recovery milestone. It does **not** mean automatic tier/budget mutation is enabled or that the shadow adaptive policy has beaten a fixed baseline on held-out real tasks.

## Historical recovery table

| Milestone | Exact commit | Archive branch | Meaning |
| --- | --- | --- | --- |
| Initial public research | `3fc7d6c438e167c384f20697cc1c0642d3de9e8a` | `archive/20260906-docs-initial` | Documentation-only research/design/audit snapshot |
| Corrected research | `25a51d7c68e36d3a53c94da568ff847f066f0fed` | `archive/20260906-docs-corrected` | Corrected theory, policy claims and audit provenance |
| Legacy public engine | `4e9b5d8ed5a05c9a538f385acc8632e641ae5908` | `archive/20260906-engine-legacy` | First sanitized paging engine; retained known v1 defects |
| 1.1.0 | `cb2db7412035661b425dd2e5ec7f4650509da79d` | `archive/v1.1.0` | Hardened public index-maintenance engine |
| 1.1.1 | `2196e1de36d9dae1798a147762b3019ebf81073e` | `archive/v1.1.1` | Retry/selector/cross-platform follow-up |
| 1.2.0 | `432c93b17735cbdf20b240c66a6cba3739e70ab9` | `archive/v1.2.0` | Final pre-1.3 retrieval/measurement snapshot |
| 1.3.0 baseline | `1880211f75b016e2234cbef702573022f6f983f1` | `archive/v1.3.0-baseline` | Multi-harness package baseline; not itself a stable-integration claim |
| Version-recovery closeout | `8e1f7f70b39386667ac00f47bb4f61ccc3f86b28` | `archive/20260907-version-recovery-merged` | Version-history and MCP/OpenClaw recovery merged by PR #1 |
| **1.4.0 stable** | **`e6e4dda5835e3cb345207457d5491131c6959b2c`** | **`archive/v1.4.0-stable`** | Shadow residency/control + opt-in session-frozen Hermes T1 locator directory; main correctness/Hermes/harness acceptance passed |

Archive branches are milestone pointers. Once published, they are not to be moved to a different commit. Later documentation closeout commits do not redefine the code/content snapshot represented by the archive pointer.

## Development boundaries

### 1.2

`433b1256bbaca8680f3c41d67a1e23e97b36bd7c` is the first repository commit that declares package version 1.2.0 and adds the scoped retrieval/measurement line.

### 1.3

Harness-neutral adapter work begins at `80fc84deeb481bea5d06e11553590c9702e43bcb` while package metadata still declares 1.2.0. The package version is bumped to 1.3.0 at `51d33fddc24c23b81ed6bb88841be9d2dd0e1ce1`.

`1880211f75b016e2234cbef702573022f6f983f1` is retained as the explicit 1.3.0 baseline. The version string alone did not certify every harness integration; exact workflow evidence governed acceptance.

### 1.4

`05129a14b61afa96161df4381a86985604e9ac94` begins the 1.4 shadow-residency implementation line from `main@deb86b40b97e0fc96e1905f66ae180836c38b1fa`.

The line adds miss/prefetch telemetry, T1 locator projection, value-aware shadow T0 recommendation, bounded co-demand prefetch, bounded shadow budget feedback and an opt-in Hermes T1 locator snapshot. The existing **T0–T3 tier model remains intact**.

Feature head `a1bd23d6abfa1181327d9ec23887cf3903be3ea0` was merged by PR #5 into accepted merge commit `e6e4dda5835e3cb345207457d5491131c6959b2c`. That merge commit is the stable 1.4 recovery point; later closeout documentation does not move it.

## What exact recovery restores

Checking out one of the commits or archive branches above restores repository bytes reachable from that Git object: source, tests, public docs, public reports and package metadata as committed at that point.

Example:

```bash
git switch --detach archive/v1.4.0-stable
```

or:

```bash
git switch --detach e6e4dda5835e3cb345207457d5491131c6959b2c
```

For an editable recovery branch:

```bash
git switch -c recovery/my-v1.4 archive/v1.4.0-stable
```

## What the repository cannot reconstruct

Git recovery does not fabricate bytes that were never committed. In particular, this repository alone cannot exactly reconstruct:

- local-only historical states that never entered Git;
- any separately delivered private reference implementation/ZIP whose bytes are not in this repository;
- remote Git objects that had already become unreachable and unavailable before the history reconstruction;
- installed Hermes configuration;
- private user `MEMORY.md`, `USER.md`, `.thm/index.json`, recall databases, residency catalogs or telemetry traces;
- local cron/task state;
- external provider/model/service state.

Those require their original artifacts or independent backups.

## Recovery and evidence are separate

A recoverable commit is not automatically a quality claim. Historical benchmark, integration or task results apply only to the exact revisions and protocols that produced them. In particular:

- Protocol 2 retrieval evidence remains attached to its recorded retrieval revisions;
- 1.4's skipped heavy retrieval workflow does not refresh those benchmark numbers;
- 1.4's main-branch correctness/Hermes/harness successes establish implementation/integration acceptance, not held-out adaptive-policy superiority;
- automatic T0–T3 or budget mutation remains gated on separate runtime/task A/B evidence.

This separation is intentional: version history answers **what bytes can be recovered**, while reports and workflows answer **what was actually tested**.

## Unreleased retrieval successor

The opt-in Python entity projection and its Protocol 2 evidence are documented in [the zero-LLM frontier](16-zero-llm-retrieval-frontier.md). It does not enable a harness option, change residency/activity/validity semantics, or move the 1.4 stable pointer.
