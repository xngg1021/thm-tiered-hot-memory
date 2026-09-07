# THM implementation validation contract

<!-- current-v1.4-status:start -->
> **Current release status — THM 1.4.0 accepted/stable implementation milestone.** Stable code/content milestone: `e6e4dda5835e3cb345207457d5491131c6959b2c`; immutable recovery pointer: `archive/v1.4.0-stable`. This document retains its original research/design/1.2/1.3 scope as historical foundation rather than rewriting old evidence as a new result. Current implementation state is tracked in [07-implementation-status.md](07-implementation-status.md), the 1.4 shadow control plane in [14-residency-control-plane.md](14-residency-control-plane.md), the opt-in Hermes T1 surface in [15-hermes-warm-directory.md](15-hermes-warm-directory.md), and the exact acceptance record in [the 1.4 closeout](../reports/2026-09-07-v1.4-closeout.md).
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
