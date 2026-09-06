# THM 1.4 shadow residency control plane

> Added 2026-09-07. Implementation: `thm/residency.py` and its split modules. This layer keeps the existing **T0–T3 tiers** unchanged. It is a THM-specific residency experiment, not a rename of the tiers and not an implementation of another repository's layer model.

## Scope

The 1.4 control plane closes the gap between “an item has a decay/activity score” and “we have evidence that keeping it resident is worthwhile.” It adds four read-only capabilities:

1. explicit miss/prefetch telemetry;
2. a compact **T1 locator directory**;
3. a token-denominated **shadow T0 residency recommendation**;
4. bounded **shadow prefetch and resident-budget suggestions**.

Every command in this document is advisory. The implementation does **not** modify `MEMORY.md`, `USER.md`, `index.json` tier assignments, validity, pin state, activity events, warm files, Hermes configuration or provider budgets.

The existing `plan` command remains the activity/decay baseline. The new `residency-plan` is a separate experiment and does not silently replace it.

## 1. Telemetry vocabulary

The telemetry schema deliberately separates access modes that older hit-only accounting could blur:

| Event | Meaning | Counts as demand? | Counts as a miss? |
| --- | --- | ---: | ---: |
| `resident_hit` | needed item was already resident | yes | no |
| `resident_miss` | needed item was not resident but was recoverable | yes | yes |
| `hard_miss` | needed state required broader search/reconstruction | yes | yes |
| `planned_retrieval` | on-demand retrieval was intentional policy, not a failure | no | no |
| `stale_resident_failure` | resident state was present but wrong/stale for the task | no | no; tracked as correctness risk |
| `prefetch` | speculative locator/tiny-excerpt fetch | never used to train demand | no |

A telemetry event may record extra tokens, tool calls, latency and observed provider cost. These are measurements supplied by the caller; THM does not invent missing values.

`prefetch` additionally requires `used=true/false`. Optional `avoided_miss` and avoided-cost fields are explicit labels, not inferred counterfactual truth.

Example JSONL:

```json
{"event_id":"run-1:a","task_id":"run-1","kind":"resident_miss","item_id":"db-port","avoidable":true,"extra_tokens":420,"extra_tool_calls":1,"extra_latency_ms":35}
{"event_id":"run-2:p","task_id":"run-2","kind":"prefetch","item_id":"db-port","used":true,"mode":"locator","extra_tokens":18,"confidence":0.8}
```

Aggregate it with:

```bash
python -m thm residency-telemetry ./private/residency-events.jsonl
```

The report states `explicit-shadow-telemetry-not-causal-usage-proof`. A retrieved or mentioned item is not automatically credited with causing task success.

### Anti-feedback rule

Per-item telemetry keeps two task sets:

- `task_ids`: broad observed interaction, including a prefetch that was later used;
- `demand_task_ids`: only `resident_hit`, `resident_miss`, and `hard_miss`.

Residency and co-demand prefetch recommendations use **`demand_task_ids` only**. A successful prefetch therefore cannot manufacture future evidence for itself.

## 2. Optional metadata catalog

The canonical THM index remains authoritative for identity, tier, status, validity, pinning and source linkage. A separate local catalog can supply measurement-only fields that the historical index schema does not own:

```json
{
  "items": {
    "entry-id": {
      "resident_units": 74,
      "miss_penalty_tokens": 900,
      "locator": "warm/database.md",
      "scope": "profile-main"
    }
  }
}
```

Allowed overlay fields are exactly:

- `resident_units`;
- `miss_penalty_tokens`;
- `locator`;
- `scope`;
- `project`;
- `profile`.

The overlay cannot change `tier`, `status`, `pinned`, validity, source hashes or events. Unsupported fields fail explicitly.

Keep private catalogs outside the public repository when their locators or scope names disclose personal state.

## 3. T1 warm directory

`warm-directory` derives a deterministic, budgeted directory from **current T1 rows only**:

```bash
python -m thm warm-directory \
  --mem-dir /path/to/memories \
  --date 2026-09-07 \
  --budget 300 \
  --counter cl100k_base \
  --catalog /private/thm-residency-catalog.json
```

Each selected line contains only:

```text
topic | scope | current-item-count | latest-date | revision-prefix | locator
```

It intentionally does **not** put the indexed summary or source text into the directory. A locator tells the agent where a T1 subject lives; it is not evidence for the subject itself.

Absolute paths, parent traversal, `~` and other unsafe locator forms are rejected. `MEMORY.md` and `USER.md` are native T0 stores, so they are not guessed as T1 locators.

Directory ranking is deterministic: explicit pin protection, cost class, number of current items, then stable lexical order. Those signals only decide which locator line fits the directory budget; they do not prove semantic importance.

## 4. Shadow value-aware T0 recommendation

`residency-plan` evaluates current T0 rows plus explicitly selected candidate tiers. The default candidate tier is T1.

```bash
python -m thm residency-plan \
  --mem-dir /path/to/memories \
  --date 2026-09-07 \
  --budget 1200 \
  --telemetry /private/residency-events.jsonl \
  --catalog /private/thm-residency-catalog.json \
  --counter cl100k_base \
  --horizon-tasks 20 \
  --min-tasks 20
```

For an item with measurable need and miss cost, the token-side comparison is:

```text
expected_saved_tokens(H)
  = expected_misses_over_H * miss_penalty_tokens

resident_carry_tokens(H)
  = resident_units * H

net_token_value(H)
  = expected_saved_tokens(H) - resident_carry_tokens(H)
```

This is deliberately a **token objective**, not a claim that latency, correctness, dollar cost and task value are interchangeable scalars. Activity is used only as a deterministic tie-break after a candidate has positive token value.

### Conservative unknown handling

A missing measurement is not silently converted to zero:

- current T0 without a measurable resident cost returns `UNCOSTED_CURRENT_RESIDENT` and suppresses placement changes;
- current T0 with incomplete counterfactual miss evidence is retained as protected/uncertain;
- if total task coverage is below `--min-tasks`, actual `admit`/`evict` arrays stay empty and only `provisional_*` fields are emitted;
- invalid/out-of-validity rows are excluded before ranking;
- an item with a recorded `stale_resident_failure` is blocked by default and sent to review even if it was frequently used;
- pinning protects capacity placement but does not override stale/correctness review.

`--complete-coverage` should only be used when the supplied trace really covers the evaluation opportunity set. It allows an observed zero to carry more meaning; it is not an accuracy switch.

T2/T3 can be considered only when the caller explicitly adds `--candidate-tier T2` or `T3` and provides a resident-cost estimate. THM does not guess the cost of promoting cold/external material from a summary length.

## 5. Bounded speculative prefetch

`prefetch-plan` is a deterministic first-order **co-demand** heuristic. It is intentionally narrower than a learned predictor.

```bash
python -m thm prefetch-plan \
  --mem-dir /path/to/memories \
  --date 2026-09-07 \
  --telemetry /private/residency-events.jsonl \
  --catalog /private/thm-residency-catalog.json \
  --active current-item-id \
  --max-candidates 3 \
  --min-support 2 \
  --min-confidence 0.5 \
  --mode locator
```

For a seed item `A` and candidate `B`:

```text
support(A,B) = number of explicit-demand tasks containing both A and B
confidence(A→B) = support(A,B) / explicit-demand tasks containing A
```

Only actual demand events train this relation. Earlier `prefetch` events are excluded even when `used=true`, preventing a self-reinforcing predictor.

The candidate must be current, come from an explicitly allowed non-T0 tier and expose a safe locator. The planner returns at most `max_candidates`. Supported modes are only `locator` and `tiny_excerpt`; there is no “prefetch the whole file” mode.

A recommendation is still a correlation, not proof that B will be needed next. Runtime evaluation should record prefetch accuracy, observed miss coverage, injected-token waste and net observed cost.

## 6. Shadow resident-budget feedback

`residency-budget` emits at most one bounded step:

```bash
python -m thm residency-budget ./private/residency-events.jsonl \
  --current-budget 600 \
  --context-pressure 0.84 \
  --min-budget 300 \
  --max-budget 1200 \
  --step 100
```

The controller compares three families of signals:

- resident miss rate above a configured target pushes toward a larger budget;
- context pressure above target pushes toward a smaller budget;
- prefetch pollution and stale-resident failures add shrink/risk pressure.

A hysteresis band prevents small noise from toggling directions. Insufficient demand holds the current budget. The result always contains `changes_applied:false`; 1.4 has no automatic budget mutation.

This is a feedback-controller experiment, not TCP AIMD and not a learned policy.

## 7. What 1.4 still refuses to do

The control plane does not:

- auto-promote or auto-demote T0–T3;
- turn `mention_observed`, display, retrieval or prefetch into a `hit`;
- infer a memory's truth from frequency;
- rewrite a stale fact;
- treat a warm-directory line as source evidence;
- infer complete telemetry from a partial trace;
- make a model/provider call;
- install cron/background jobs;
- claim a global optimum for decay, residency budget or prefetch thresholds.

These boundaries preserve the existing distinction between **observation**, **activity**, **validity**, **residency**, and **task outcome**.

## 8. Acceptance gate before any automatic controller

Automatic tier or budget changes should remain out of scope until an exact implementation revision has runtime evidence showing, on held-out tasks:

1. lower miss/reacquisition cost at the same or better task quality;
2. no increase in stale-state mistakes or scope/profile leakage;
3. prefetch has positive net value after unused injection is charged;
4. decisions remain stable under incomplete/empty telemetry and process restart;
5. a simple baseline (fixed budget plus current decay/activity policy) is reported alongside the adaptive policy;
6. results distinguish retrieval coverage from generated-answer/task success.

Until then, THM should expose recommendations and receipts rather than hide policy changes behind an opaque score.

## Implementation map

- public facade: `thm/residency.py`
- validation/catalog helpers: `thm/_residency_common.py`
- telemetry: `thm/residency_telemetry.py`
- T1 locator projection: `thm/residency_directory.py`
- shadow residency/prefetch/budget control: `thm/residency_control.py`
- compatibility research CLI: `research/residency/miss_telemetry.py`
- regression tests: `tests/test_residency_control.py`, `tests/test_miss_telemetry.py`

The earlier hardware-analogy audit and its evidence boundaries remain in [the preceding design note](13-hardware-inspired-adaptive-residency.md).
