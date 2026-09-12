# THM implementation validation contract

## Provider Fabric acceptance contract

The [provider matrix](provider-matrix.md) separates documented, discoverable, preparable, executable, receipt-complete and hardware-accepted levels. [Optimizer evidence](22-runtime-optimizer.md) separately records structural/numeric parity, material gain, resource tradeoffs and workload scope. Every paired replay must pass; unknown constrained resources cannot become free. No new hardware speed or agent-quality claim follows from SDK fixtures, smoke or CI. Exact-head review and normal expected-head merge remain required.

## Evaluation Fabric contract

The [Evaluation Fabric](18-evaluation-fabric.md) defines schema thm-evaluation/1 and separates memory-dataplane, systems-runtime and LLM-agent-outcome. No-gold, unresolved and diagnostic tasks are excluded from main recall denominators. Missing native locators produce null recall. Fixture success, live retrieval, hardware performance and agent outcome must never be substituted for one another. A failed/timeout run cannot publish passed acceptance; source/implementation SHA, scope and truncation remain explicit.

<!-- current-v1.4-status:start -->
> **THM 1.5.0 implementation surface.** Current code, configured extension contracts and evidence boundaries are described in [1.5 implementation surface](24-full-power-implementation.md). Historical results below retain their original protocol and source identity. The immutable 1.4.0 archive remains unchanged.
<!-- current-v1.4-status:end -->

This contract retains T0–T3 and the historical policy described in [the architecture](02-架构设计.md). It specifies observable behavior for an implementation; it does not establish that the original engine implements it. Historical arithmetic remains tested by [the numeric audit](../scripts/thm_numeric_audit.py).

| Evidence stage | Required observation | What it does not establish |
| --- | --- | --- |
| Historical design | Versioned document and preserved old-formula tests | Executed engine behavior |
| Implemented code | Identified callable functions and reviewed changes | Deployment or real-data compatibility |
| Synthetic test | Fixed inputs, clock, expected outcome and actual execution | Model effectiveness |
| Stored | Source bytes and index version can be read | Retrieval for this task |
| Retrieved | Relevant bounded records with scope and source metadata | Inclusion in a model request |
| Constructed context | Inspect the complete output including wrappers against the budget | Successful host transport |
| Hermes integration | Observe the actual request boundary with an isolated test profile | User deployment |
| Deployed | Explicit installation and verification on the intended host | General performance superiority |

## Four bounded behavior chains

1. **Record and score correctness.** Stable identity survives relocation. Revisions preserve history and validity intervals; a later revision must not extend an already expired predecessor. Date-only input retains day precision. Events distinguish display, retrieval, use, evidence-backed confirmation and relocation, with deterministic deduplication and explicit time-window endpoints. Activity does not certify truth or renew validity.
2. **Task retrieval.** Apply explicit profile, project, subject, environment, temporal and status filters before relevance ranking. Preserve proposals, quotations and unresolved conflicts as labelled data. No match is a valid outcome. Unavailable sources and permission failures must remain distinguishable from an empty corpus or an unsuccessful query.
3. **Bounded context.** Measure the entire model-facing output, including source metadata and wrappers. Keep characters separate from tokens; label estimates when the target tokenizer is absent. Reserve space for the rest of the host request and response. Omit a complete entry rather than truncate its negation, unit, validity or scope qualifiers. A diagnostic log containing an unbounded second copy is outside the budget and must not be used as the tool result.
4. **Residency and movement.** Cost priority and explicit pinning are separate. Validate eligibility before admission, calculate actual capacity, and select only permitted replacements. Save and verify targets before committing index changes, then conditionally remove sources. Single-writer locking, version checks, interrupted retries and deletion tombstones need executable tests. File replacement alone is not proof of a multi-file transaction or power-loss durability.

Migration must preview changes and verify a backup before execution. Preserve unknown legacy fields and ambiguous high-priority protection until their meaning is explicitly resolved. A quarantine record is not a successful active-data migration. Logical deletion does not imply physical erasure from backups or independently managed transcripts.

## Hermes integration boundary

Checked against public upstream commit `245e48008fa814b3251f50755eb656bd9fb86cb1` on 2026-09-06:

- [Memory documentation](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/website/docs/user-guide/features/memory.md) and [MemoryStore source](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/tools/memory_tool_store.py) distinguish the frozen load-time system snapshot from live store state. Changing a file does not prove mid-session visibility.
- [Profiles](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/website/docs/user-guide/profiles.md) separate Hermes state directories. They do not by themselves prevent local terminal access to other filesystem locations.
- [The memory tool](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/tools/memory_tool.py) routes mutations through its configured write gate. A staged result is not an applied write. Integrations must use the native channel and verify the result, including pending or blocked outcomes.
- [Custom tool guidance](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/website/docs/developer-guide/adding-tools.md) recommends plugins for custom tools without core changes. The [memory-provider interface](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/agent/memory_provider.py) supports `prefetch(query, session_id=...)`; a supported hook is not evidence that a particular installation has enabled it.

No live Hermes integration or model-effectiveness result is asserted by this document. A source-level interface review and an isolated test of a substitute are separate evidence categories.

## Minimum comparison protocol

Use the same synthetic records, explicit scope, fixed clock and complete-context budget for a simple recency/frequency baseline, warm-tier retrieval and the candidate policy. Clearly name common validity filters. Keep development and held-out queries distinct; report failures without changing the questions after seeing the results. Report retrieval hits, correct empty outcomes, expired and wrong-subject selections, context sizes, local retrieval calls and latency separately. Offline lookup timing excludes model and network latency. Any model experiment requires its own inputs, authorization, budget and observed request evidence.


## Post-local corrective evidence

See the [current corrective contract and short retest](19-post-local-corrective.md). Z6 CPU/CUDA/auto-throughput and local NTFS/NVMe are machine-observed at b1f8119. Aggregate parity, strict parity, calibrated policy and post-fix acceptance remain separate claims. Auto-safe now allows a measured reference fallback; lack of acceleration does not itself fail correctness. No version/stable promotion or full-dataset acceptance is implied.

## 1.5 implementation and evidence contract

[1.5 implementation surface](24-full-power-implementation.md) defines the executable configured provider/storage lifecycle, allocation and joint-planning APIs, explicit actuator, five benchmark/environment/outcome interfaces, independent CE bridge, and LangGraph/Deep Agents lifecycle. Automatic memory mutation remains false and rejected features remain default-off. Hardware, full-research and real task evidence are separately recorded in the [completion ledger](../reports/2026-09-12-thm-full-power-completion.md).
