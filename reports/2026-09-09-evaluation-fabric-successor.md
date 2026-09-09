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
