# THM — Tiered Hot Memory

Author: Junfu Shi (SJF, xngg1021). License: [MIT](LICENSE).

THM preserves a four-tier design for Hermes Agent. The public `scripts/thm.py` is now a **1.1 index-maintenance and residency-proposal CLI**, with direct implementation tests. It does not implement automatic memory paging, a MemoryProvider, general semantic search or a model benchmark. Personal memory and deployed instances are not part of this repository.

## Four tiers

T0 is the small native MEMORY.md / USER.md snapshot; T1 is on-demand thematic material; T2 is historical sessions and archives; T3 contains external source locations. In the pinned Hermes implementation, a write to the memory files does not itself refresh an existing session's frozen system snapshot. T3's name does not guarantee immutable external content. See the [historical architecture](docs/02-架构设计.md) and [current implementation status](docs/07-implementation-status.md).

The activity formula remains a heuristic: `sum(weight * (age_days + 1)**-0.5)`. It is not a truth, relevance or optimality score. The 1.1 script no longer rewards relocation; new high-cost entries are not automatically pinned. Explicit migration preserves legacy protection pending review.

## Run and test

Python 3.10+; standard library only. No model, network service or installation is needed for the CLI.

```bash
python scripts/thm.py --help
python scripts/thm.py --mem-dir /path/to/test-profile/memories seed
python scripts/thm.py --mem-dir /path/to/test-profile/memories audit
python -m unittest discover -s tests -v
python scripts/thm_numeric_audit.py
python scripts/check_docs.py
```

Use a test directory containing MEMORY.md and USER.md initially. Global path options precede the command. The script never writes either source file. It writes its own index, lock and previous-index backup under the configured state directory. Default state is `<resolved-memory-directory>/.thm`; it is not the repository root. An existing v1 index requires the [explicit preview/apply migration](docs/06-engine-guide.md).

`hit` accepts exact entry IDs or unique selectors and deduplicates retries. `confirm` requires an explicit evidence reference and advances review at most once per day. `pin` and `unpin` control residency protection without asserting validity. See the [complete CLI guide](docs/06-engine-guide.md).

## Project documents and evidence

The [complete document index](docs/README.md) links research, architecture, validation contracts, competitor sources, upstream findings, engine use, migration, status, tests and historical audit evidence. All publishable documents in this delivery live in the repository; no full mixed-project conversation is required to operate it.

The original academic audit remains preserved verbatim behind its errata. The original ten numeric tests intentionally include counterexamples to the old policy. They do not certify the engine. The new implementation tests exercise the public script directly; the separate private reference implementation's previously reported tests are not reused as evidence for this version.

The [repair record](reports/2026-09-06-engine-hardening.md) and [machine-readable test record](reports/2026-09-06-engine-hardening.json) specify actual local execution and limits. CI, when available, runs the repository checks separately on Linux, Windows and macOS; its result must be read from the exact commit, not inferred from workflow presence.

## Remaining boundaries

This release proposes T0 changes for the native Hermes memory tool; it never applies them automatically. It has no complete-request tokenizer budget, multi-file tier-move transaction, T1/T2/T3 retrieval adapter, automatic source reconciliation or deployed host integration. Index locks coordinate cooperating local processes, not hostile filesystem users or all network filesystems. Linux tests do not establish power-loss safety or native Windows/macOS execution. Details are recorded in the implementation-status document.

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills). Its presence is not evidence that THM's theories or effects have been validated.
