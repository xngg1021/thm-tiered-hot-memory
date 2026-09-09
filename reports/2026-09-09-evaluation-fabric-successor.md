# Evaluation Fabric successor

Authoritative predecessor: `main@44cf057fd7aa37ee9a93bef6e94648d5201eb705`. Successor: [PR #17](https://github.com/xngg1021/thm-tiered-hot-memory/pull/17), branch `work/evaluation-fabric-20260909`. All changes are forward-only; package and stable archive remain 1.4.0 (`archive/v1.4.0-stable@e6e4dda5835e3cb345207457d5491131c6959b2c`).

## Scope delivered

- Typed schema thm-evaluation/1 for adapter, task, evaluator-only ground truth, result and receipt; independent logical/compute/physical taxonomy fields.
- Shared LoCoMo Protocol 2 and LongMemEval-S dataplane metrics while retaining evidence-unit and legacy-report distinctions.
- Native V2 public-state insert/query and upstream registration; BEAM batch/turn/probing inputs; MemoryArena ordered tasks and cross-session memory interface. Original tiny fixtures only.
- Three evidence layers, external trace-bound outcome import, separate physical StorageProfile/placement/extent I/O probe, and explicit unavailable SQLite I/O telemetry.
- Offline bounded smoke/acceptance with process-tree deadlines, source/task caps, immutable output namespace, and supervisor-only acceptance publication after worker exit.
- Explicit full-research dataset entrypoints and manually enabled research CI; existing bounded runtime verifier and economics suite calls updated.
- Eight READMEs reorganized around three planes and Evaluation Fabric; docs CI checks section identity/order, headings, exact command blocks and table structure. Current documentation surfaces and CHANGELOG synchronized.

## Verified development evidence

Initial source `a1bc9c590db0c8f480b2954d8ada681a80813a60` passed 434 local tests, headless, numeric audit, document and version-history checks; installed core smoke worked outside the checkout. Initial remote correctness found EOF whitespace and Windows CRLF in transient smoke receipts. Hermes and harness gates passed. Those correctness failures were fixed forward, not waived.

Source `597a4912fc87711a163aaab144bc43cf46b67937` passed 435 local tests. It adds calling-thread SQLite connections with serialized memory updates, LF receipt writes, CI output in runner scratch, and exact localized command parity. Remote correctness [PR run 34321868507](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34321868507) and [push run 34321864831](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34321864831) passed on Ubuntu/Windows/macOS. [Hermes 34321864827](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34321864827) and [harness 34321864847](https://github.com/xngg1021/thm-tiered-hot-memory/actions/runs/34321864847) passed.

The following forward fix initializes empty per-task memory, makes the supervisor the sole acceptance publisher, and propagates explicit research opt-in through the economics suite. The final exact source/tree, Codex P1/P2 review outcomes, normal expected-head merge and post-merge main runs are recorded in the PR conversation. Earlier-head CI is historical and cannot stand in for those final gates. A commit cannot contain its own future merge/CI identities.

## Evidence not claimed

No full LoCoMo/LME/V2/BEAM/MemoryArena campaign was executed in Work. No live reader/judge/agent environment outcome was produced. V2 is explicitly text-only; missing gold locators remain unscorable. Physical probes do not establish Z6 G4 performance, CPU/GPU dispatch, CXL/DAX/SPDK/GDS support or an end-to-end speedup. All new capabilities remain Unreleased.

The [Evaluation Fabric contract](../docs/18-evaluation-fabric.md) contains the bounded Windows acceptance command and independent full-research entrypoints.

## Review-driven LME forward fixes

Codex review of `597a4912fc` found the suite opt-in and documented command omissions (P1/P2), both fixed in `183630fe64`. Its follow-up review of `183630fe64` found repeated LME session position collisions (P1) and missing native LME parent-locator session counts (P2). The next successor gives each session occurrence a unique positional identity while retaining its original source ID for gold scoring, and maps parent locators through document-to-session identities. Regressions execute repeated-session indexing and real partial-segment retrieval, asserting parent coverage without complete-evidence credit. All four review threads are retained in PR #17 with their exact fixes.

Codex review of `d1e4a606b5` found one further P1 in the still-runnable historical hardware procedure: its native LME command lacked the new explicit opt-in. That command now includes --full-research, is labeled an optional historical campaign instead of a merge blocker, and links to bounded acceptance. A documentation regression gate rejects runnable native dataset commands that omit explicit research opt-in.

Review of `35f760a663` added two P2 findings: native runner changes were absent from the implementation digest, and indented/prompt-prefixed command examples bypassed the docs guard. The next forward fix binds the native source SHA captured at import into the composite receipt identity, verifies it using two independently loaded source revisions, and covers indentation, common shell/PowerShell prompts and exact flag token boundaries in the docs gate.

Review of `c09f51b93b` identified missing imported outcome aggregates and shell-comment flag false positives (two P2 findings). The successor publishes macro means with explicit measured counts and null exclusion, retains task rows, and parses documented arguments with quoted paths and shell comments handled separately. Regression coverage verifies mixed available outcome scores and comment-only opt-in rejection.

Review of `363dded316` identified a P2 false rejection for unquoted filenames containing a hash. The docs command gate now recognizes comments only at unquoted, unescaped word boundaries and preserves embedded/escaped hashes. Regression cases retain legitimate opt-in arguments after these paths while rejecting flags that appear only in a following comment.

Review of `0b0fbfdb11` found a P2 false rejection for hash suffixes attached to command substitutions. The parser now tracks nested substitution depth and restores outer quote/word state when substitutions close. Tests cover nested, quoted and prefixed substitutions with legitimate flags and trailing comment-only flags.

Review of `d8fec3c8d0` found generator exhaustion in outcome imports and rejection of continued shell commands (two P2 findings). Outcome iterables are now materialized once before coverage, trace, aggregation and serialization passes. The docs gate assembles escaped Bash/PowerShell continuations before checking arguments. Tests compare generator/list receipts, reject mismatched traces from generators, and distinguish continued flags from comment-only flags.

Review of `44c8790040` found two P2 docs-gate issues: flags borrowed from a later chained command and continuations using the wrong fenced shell syntax. The gate now limits flags to the initial command outside quotes/substitutions and selects the continuation marker from the fence language. Tests cover separators/pipelines, quoted separators, valid shell-specific continuations and mismatched markers.

Review of `67bae298ea` found two P2 shell-context boundaries: PowerShell prompts without a shell-labelled fence and pipes nested in Bash process substitutions. The gate now derives PowerShell continuation syntax from recognized prompts when no explicit shell is declared and tracks nested process-substitution frames. Regressions cover prompt-only/text-fenced PowerShell and nested process substitutions without accepting flags in later commands.

Review of `15620e7cb9` identified a P2 for legacy Bash backtick substitutions. The scanner now retains shell context through argument checks, masks Bash backtick substitutions (including nested forms), and preserves PowerShell backtick escape behavior. Regressions reject inner-only flags and accept explicit outer flags while retaining PowerShell escaped hash paths.
