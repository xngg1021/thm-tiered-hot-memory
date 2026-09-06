# THM version history and recovery map

Reconstructed on 2026-09-07 from the remote Git history of `xngg1021/thm-tiered-hot-memory`.

## Authority and recovery rule

Git commits are the authoritative historical record. Archive branches are convenience pointers to milestone commits and must not be moved after publication. They do not replace the commit graph.

A historical state is classified as **exactly recoverable** only when the corresponding commit object is reachable from the repository. A version number is recorded only when repository evidence explicitly names it; pre-version research and engine snapshots are preserved under descriptive IDs rather than invented semantic versions.

At reconstruction time the remote had one branch (`main`) and no version tags. The following archive branches were created without rewriting `main`:

| Snapshot | Commit | Archive branch | Evidence / meaning |
| --- | --- | --- | --- |
| Initial public research snapshot | `3fc7d6c438e167c384f20697cc1c0642d3de9e8a` | `archive/20260906-docs-initial` | Initial research review, architecture and academic-audit commit |
| Corrected research snapshot | `25a51d7c68e36d3a53c94da568ff847f066f0fed` | `archive/20260906-docs-corrected` | Theory/policy/audit corrections before the public engine line |
| Legacy public engine | `4e9b5d8ed5a05c9a538f385acc8632e641ae5908` | `archive/20260906-engine-legacy` | First sanitized paging engine; retained historical v1 defects |
| **1.1.0** | `cb2db7412035661b425dd2e5ec7f4650509da79d` | `archive/v1.1.0` | `reports/2026-09-06-engine-hardening.json` records engine version 1.1.0 |
| **1.1.1** | `2196e1de36d9dae1798a147762b3019ebf81073e` | `archive/v1.1.1` | `reports/2026-09-06-chat-followup.json` records engine version 1.1.1 |
| **1.2.0** | `432c93b17735cbdf20b240c66a6cba3739e70ab9` | `archive/v1.2.0` | Last pre-1.3 snapshot; `pyproject.toml` still declares 1.2.0 |
| **1.3.0 baseline** | `1880211f75b016e2234cbef702573022f6f983f1` | `archive/v1.3.0-baseline` | `pyproject.toml` declares 1.3.0; exact CI results remain the authority for integration closure |

The machine-readable source for this table is [`versions/history.json`](../versions/history.json).

## Version-line boundaries

### Pre-version research line

`3fc7d6c` is the original documentation-only public snapshot. `25a51d7` is the corrected documentation snapshot. These commits are preserved as historical states, but assigning retrospective `0.x` version numbers would create history that did not exist in the repository, so this reconstruction does not do that.

### Public engine before 1.1

`4e9b5d8` introduced the sanitized public paging engine. Later status documentation explicitly identifies it as the earlier public engine that retained known v1 defects. It is therefore preserved as a named legacy snapshot rather than being relabeled as an invented `1.0.0` release.

### 1.1.0

`cb2db741` is the 1.1.0 hardened public index-maintenance state. Its machine-readable hardening report records `engine_version: 1.1.0`, test counts, environment and source hashes.

### 1.1.1

`2196e1de` is the 1.1.1 closeout on the 1.1 line. Its report records the exact predecessor (`cb2db741`), `engine_version: 1.1.1`, test results and explicit non-claims.

### 1.2.0

The 1.2 line begins at `433b1256`, where the repository package first declares 1.2.0 and adds scoped recall, observation and decay measurement. Work continues through recall hardening, Protocol 2 evidence and Hermes integration. `432c93b` is frozen as the 1.2.0 archive because it is the last commit before 1.3 harness-development work begins, and its `pyproject.toml` still declares 1.2.0.

This distinction matters: the later `80fc84d` harness-neutral adapter begins 1.3-oriented development while package metadata still says 1.2.0. The history map preserves that development boundary instead of pretending every commit carrying the old metadata belongs to the stable 1.2 feature set.

### 1.3.0

1.3-oriented harness work begins at `80fc84d`. The package version is explicitly bumped to 1.3.0 at `51d33fd`. `1880211` is frozen as the first reconstructed 1.3.0 baseline because it is the `main` head at the start of this recovery operation.

The version string does **not** certify that every harness E2E is green. Release and integration status must be read from the exact workflow run for the exact commit. The archive name therefore uses `v1.3.0-baseline`, not `v1.3.0-stable`.

## Restoring any preserved state

Every commit remains directly addressable even when it is not an archive milestone:

```bash
git log --reverse --first-parent main
git show <commit>
git switch --detach <commit>
```

For milestone states:

```bash
git switch archive/v1.1.0
git switch archive/v1.1.1
git switch archive/v1.2.0
git switch archive/v1.3.0-baseline
```

For side-by-side comparison without moving the current checkout:

```bash
git worktree add ../thm-v1.2 archive/v1.2.0
git worktree add ../thm-v1.3 archive/v1.3.0-baseline
```

No historical commit needs to be replayed or rewritten to recover its tree. Rewriting `main`, force-moving archive branches, or squashing the historical chain would reduce recoverability and is outside this policy.

## What cannot be reconstructed exactly from this repository

The following are outside the recoverable Git history unless their original bytes are supplied from another source:

- local-only versions that were never committed;
- the separately delivered private reference implementation / ZIP whose bytes are not present in this repository;
- unreachable Git objects that had already been removed from the remote before this reconstruction;
- installed Hermes configuration, user memory/index contents, local cron state, provider state and external model state.

If any of those artifacts are later supplied, they should be imported as **new historical evidence** with their original timestamp/source/hash. They should not be inserted into the old commit graph with fabricated dates.

## Forward version-control discipline

For every future semantic version:

1. keep implementation commits forward-only on a work branch;
2. record the exact predecessor and intended version boundary;
3. bump package/plugin metadata only when the version line is intentional;
4. record exact HEAD, parent(s), evidence paths and CI status in a machine-readable closeout;
5. freeze the accepted commit with an immutable version ref (tag when available; archive branch remains an acceptable recovery pointer);
6. never infer a green release from a version string alone;
7. retain failed historical CI and superseded reports instead of rewriting them into success.

`versions/history.json` and `scripts/check_version_history.py` are intended to make these invariants machine-checkable.
