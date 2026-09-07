# Public engine 1.1: commands, data and migration

<!-- current-v1.4-status:start -->
> **Current release status — THM 1.4.0 accepted/stable implementation milestone.** Stable code/content milestone: `e6e4dda5835e3cb345207457d5491131c6959b2c`; immutable recovery pointer: `archive/v1.4.0-stable`. This document retains its original research/design/1.2/1.3 scope as historical foundation rather than rewriting old evidence as a new result. Current implementation state is tracked in [07-implementation-status.md](07-implementation-status.md), the 1.4 shadow control plane in [14-residency-control-plane.md](14-residency-control-plane.md), the opt-in Hermes T1 surface in [15-hermes-warm-directory.md](15-hermes-warm-directory.md), and the exact acceptance record in [the 1.4 closeout](../reports/2026-09-07-v1.4-closeout.md).
<!-- current-v1.4-status:end -->

Implementation: [scripts/thm.py](../scripts/thm.py). This guide describes the public CLI, not a separate private reference implementation. The script maintains its index and emits review proposals. It never changes MEMORY.md/USER.md, invokes a model, enables cron or performs tier moves.

## Configuration and isolated state

For the memory directory, precedence is `--mem-dir`, `THM_MEM_DIR`, the exact `mem_dir=` key in thm.conf, then `$HERMES_HOME/memories` (fallback: `~/.hermes/memories`). For state, precedence is `--state-dir`, `THM_STATE_DIR`, the exact `state_dir=` config key, then `<resolved memory directory>/.thm`. The fallback does not infer Hermes' sticky active profile or every native Windows installer layout: pass the actual directory or HERMES_HOME explicitly.

Paths expand `~` and environment variables and resolve to absolute paths. Relative config values are relative to the config file; relative CLI/environment values are relative to the current working directory. The simple config accepts only one mem_dir and one state_dir assignment, plus blank/comment lines. Do not quote values as shell expressions. A custom config is selected with `--config`.

Global options precede the subcommand. Running with no command or `--help` does not read configuration or personal memory. A missing source file is an error, not an empty successful store. The index binds the normalized memory directory; using it with another profile fails. This is accidental state-separation protection, not an operating-system sandbox.

The state directory contains `index.json`, the stable `index.lock`, `index.previous.json` after a later successful update, optional `legacy-index.backup.json`, and an optional `warm/` directory. Keep this directory private and out of Git. Switching state directories does not migrate existing state or warm files.

## Commands

| Command | Behavior |
| --- | --- |
| `seed` | Register complete parsed content plus source filename; repeat calls preserve IDs and index bytes when nothing changes |
| `register MEMORY.md selector high` | Register exactly one matching section, with explicit cost; add `--pin` for fixed residency protection |
| `audit` | Report activity, low-activity pinned entries, orphaned/changed sources, due reviews, duplicate hints and demotion/archive proposals; no index write |
| `hit entry-id note --event-id run-1-use-1` | Record task use; explicit IDs distinguish independent uses and retries |
| `confirm entry-id --evidence user:check-1 --event-id check-1` | Record a caller-supplied confirmation reference; at most one counted confirmation per calendar day |
| `pin entry-id` / `unpin entry-id` | Explicitly set residency protection; does not change validity or perform a tier move |
| `manifest` | List thematic Markdown files in this state's warm directory; missing directory has an explicit status |
| `migrate /path/to/legacy-index.json` | Preview v1 adoption without writing |
| `migrate /path/to/legacy-index.json --apply` | Back up exact source bytes, verify, then create a new v2 index; never overwrite an existing target |

Exit code 0 means a completed operation (including an identified idempotent retry), 1 an operational failure, and 2 invalid CLI arguments. Successful results are JSON on stdout; operational errors are JSON on stderr. Missing records and ambiguous selectors are failures. Multiple exact duplicate occurrences of the same normalized section in the same file share one indexed record; different source files or different complete content remain separate.

## Feedback and validity

Exact IDs take priority over text selection. Text selectors must resolve to one record. A feedback operation verifies that a T0 record's complete content fingerprint still appears in the same source file. Changed or deleted sources must be reconciled explicitly; feedback cannot silently bless the old summary. T1/T2/T3 feedback requires a future source adapter and currently returns an explicit unsupported error.

Without an event ID, identical same-day event type, record, note and evidence produce a deterministic retry ID. This intentionally merges indistinguishable uses; supply distinct IDs for distinct genuine uses. Reusing an ID with different content fails. A retry on a later calendar day may conflict rather than create a second event. Repeated confirmations with different IDs on the same day do not multiply score or advance the review ladder repeatedly.

A confirmation's evidence reference is an assertion by the caller, not an external verification performed by this CLI. Missing evidence fails. Display, retrieval, promotion and demotion have zero activity weight. Unknown event types and invalid/future event dates fail. Historic unverified confirmations are preserved on migration, labelled, and given zero weight. The 3/7/30/90-day schedule and score thresholds remain tunable heuristics, not empirically optimal parameters.

Optional `valid_from` and exclusive `valid_until` dates filter audit ranking and feedback. Invalid, deleted and unresolved legacy records are excluded. Pinning does not bypass those filters. There is no automatic interpretation of contradictory sentences, source-version reconciliation or comprehensive deletion service in this release. Newly seeded records use the registration date, explicitly not the unknown original creation date.

## Explicit v1 migration

1. Point `--mem-dir` to the intended isolated profile. Keep the old index and source files unchanged. The repository-root legacy index is not adopted automatically.
2. Run migrate without `--apply`. Inspect unresolved IDs and policy changes. The preview does not create a target index or backup.
3. On apply, the original v1 bytes are copied to `legacy-index.backup.json` and read back. The source stays unchanged; unknown metadata and legacy IDs are retained.
4. A v1 key/summary is matched only within its recorded source store. Unresolvable records remain `unresolved_legacy`, not active guessed content. Invalid dates or malformed metadata block migration without rewriting the original.
5. Legacy high-cost protection is translated into a pin requiring review. It is not silently cancelled. After reviewing a record, use `unpin` explicitly. Warm files, transcripts, cron and the installed runtime are not migrated by this command.

The original short-prefix identity is not used for new records. A source fingerprint contains the full parsed section and source filename; the stable record ID is independent. Editing content creates a new registration when seeded; this CLI does not infer whether it supersedes an older record.

## Persistence and recovery limits

Mutations lock a stable file using the operating system's local advisory locking, load the current index, compare the read version and digest, serialize before touching the destination, save the previous index and replace a same-directory temporary file. POSIX also synchronizes the directory. The lock file is deliberately not unlinked. Cooperating child processes are covered by regression tests.

A failure before replacing index.json leaves its earlier bytes intact. Failure after replacement but during directory sync is reported as commit-visible/sync-uncertain; inspect the index before retrying and reuse the event ID. The backup/index pair is not a multi-file transaction. No automatic recovery guesses which backup is authoritative. Do not restore index.previous.json over an active writer; use a separate state directory to inspect it first.

Process-kill lock release and replacement-failure tests are different from electrical power-loss tests. A killed process can leave an unused temporary file; it is not loaded as active state. This release does not promise correct behavior against malicious path replacement or all network filesystems. A file larger than 8 MiB fails explicitly; raising scale limits requires new measurement.

Hermes integration context: [upstream findings](05-hermes-upstream.md). The native memory tool remains responsible for authorized T0 changes and native budgets. The audit report is not a model-facing context bundle and does not claim a prompt-token limit.
