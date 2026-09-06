# THM 1.4 shadow residency control plane

> Added 2026-09-07. Implementation: `thm/residency.py` and its split modules. The existing **T0–T3 tiers remain unchanged**. This is a THM-specific residency experiment; it does not rename the tiers or import another repository's layer model.

## Scope

1.4 closes the gap between “an item has an activity/decay score” and “there is evidence that keeping it resident is worthwhile.” It adds four read-only capabilities:

1. explicit miss/prefetch telemetry;
2. a compact T1 locator directory;
3. a token-denominated shadow T0 residency recommendation;
4. bounded shadow prefetch and resident-budget suggestions.

All commands are advisory. They do **not** modify `MEMORY.md`, `USER.md`, tier assignments, validity, pin state, activity events, warm files, Hermes configuration or provider budgets. The older `plan` command remains the activity/decay baseline; `residency-plan` is a separate experiment.

## 1. Telemetry vocabulary

| Event | Meaning | Demand | Miss |
| --- | --- | ---: | ---: |
| `resident_hit` | needed item was already resident | yes | no |
| `resident_miss` | needed item was not resident but recoverable | yes | yes |
| `hard_miss` | needed state required broader search/reconstruction | yes | yes |
| `planned_retrieval` | on-demand retrieval was intentional policy | no | no |
| `stale_resident_failure` | resident state was present but wrong/stale | no | no; correctness risk |
| `prefetch` | speculative locator/tiny-excerpt fetch | never trains demand | no |

Events may carry extra tokens, tool calls, latency and observed provider cost. THM never invents missing values. `prefetch` requires `used=true/false`; optional `avoided_miss` and avoided-cost fields remain caller-supplied counterfactual labels.

Example JSONL:

```jsonl
{"event_id":"run-1:a","task_id":"run-1","kind":"resident_miss","item_id":"db-port","avoidable":true,"extra_tokens":420,"extra_tool_calls":1,"extra_latency_ms":35}
{"event_id":"run-2:p","task_id":"run-2","kind":"prefetch","item_id":"db-port","used":true,"mode":"locator","extra_tokens":18,"confidence":0.8}
```

```bash
python -m thm residency-telemetry ./private/residency-events.jsonl
```

The report labels itself `explicit-shadow-telemetry-not-causal-usage-proof`.

### Anti-feedback rule

Per-item telemetry maintains both broad `task_ids` and strict `demand_task_ids`. Only `resident_hit`, `resident_miss` and `hard_miss` enter `demand_task_ids`. Residency and co-demand prefetch use the strict set, so a successful earlier prefetch cannot manufacture future evidence for itself.

## 2. Optional measurement catalog

The canonical THM index continues to own identity, tier, status, validity, pinning and source linkage. A separate local catalog may add only measurement/projection fields:

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

Allowed overlay fields are `resident_units`, `miss_penalty_tokens`, `locator`, `scope`, `project` and `profile`. Any attempt to override `tier`, `status`, validity, pin state, events or source identity fails. Keep private catalogs outside the public repository when their locators or scope names disclose private state.

## 3. T1 warm directory

```bash
python -m thm warm-directory \
  --mem-dir /path/to/memories \
  --date 2026-09-07 \
  --budget 300 \
  --counter cl100k_base \
  --catalog /private/thm-residency-catalog.json
```

The projection uses current T1 rows only. Each selected line contains:

```text
topic | scope | current-item-count | latest-date | revision-prefix | locator
```

It intentionally omits indexed summaries and source text. A locator says where a T1 subject lives; it is not evidence for the subject. Absolute paths, parent traversal, `~` and unsafe locator forms are rejected. Native `MEMORY.md`/`USER.md` are not guessed as T1 locators.

Directory packing is deterministic and budgeted. Pin/cost/count signals only decide which locator line fits; they do not prove semantic importance.

## 4. Shadow value-aware T0 recommendation

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

For measurable items the token-side comparison is:

```text
expected_saved_tokens(H) = expected_misses_over_H * miss_penalty_tokens
resident_carry_tokens(H) = resident_units * H
net_token_value(H) = expected_saved_tokens(H) - resident_carry_tokens(H)
```

This is deliberately a token objective. It does not pretend that latency, correctness, dollars and task value are one scalar. Activity is only a deterministic tie-break after positive token value is established.

### Conservative unknown handling

- current T0 without measurable resident cost returns `UNCOSTED_CURRENT_RESIDENT` and suppresses placement changes;
- current T0 with incomplete counterfactual miss evidence stays protected/uncertain;
- if task coverage is below `--min-tasks`, real `admit`/`evict` arrays stay empty and only `provisional_*` fields are emitted;
- invalid or out-of-validity rows are excluded before ranking;
- `stale_resident_failure` blocks the item by default and sends it to review even if frequently used;
- pinning protects capacity placement but never turns stale content into valid content.

`--complete-coverage` is only valid when the trace really covers the evaluation opportunity set. T2/T3 candidates require explicit `--candidate-tier` plus an explicit resident-cost estimate; THM does not infer promotion cost from summary length.

## 5. Bounded speculative prefetch

`prefetch-plan` is a deterministic first-order co-demand heuristic, not a learned branch predictor.

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

For seed A and candidate B:

```text
support(A,B) = explicit-demand tasks containing both A and B
confidence(A→B) = support(A,B) / explicit-demand tasks containing A
```

Only explicit demand trains the relation. Earlier `prefetch` events are excluded even if later used. Candidates must be current, from explicitly allowed non-T0 tiers, and expose safe locators. The only modes are `locator` and `tiny_excerpt`; there is no whole-file speculative injection.

Runtime evaluation should record prefetch accuracy, observed miss coverage, injected-token waste and net observed cost. Correlation is not a causal utility claim.

## 6. Shadow resident-budget feedback

```bash
python -m thm residency-budget ./private/residency-events.jsonl \
  --current-budget 600 \
  --context-pressure 0.84 \
  --min-budget 300 \
  --max-budget 1200 \
  --step 100
```

The controller uses resident miss excess as grow pressure, context pressure as shrink pressure, and prefetch pollution/stale-resident failures as additional risk pressure. Hysteresis prevents small noise from oscillating the budget. Insufficient demand holds the current value. The result always reports `changes_applied:false`.

This is a bounded feedback experiment, not TCP AIMD and not a learned policy.

## 7. Explicit non-capabilities

1.4 does not auto-promote/demote T0–T3, convert `mention_observed`/display/retrieval/prefetch into `hit`, infer truth from frequency, rewrite stale facts, treat locator lines as evidence, infer full telemetry from partial traces, call a model/provider, install cron, or claim a global optimum for decay/residency/prefetch thresholds.

These boundaries preserve the distinction between **observation**, **activity**, **validity**, **residency**, and **task outcome**.

## 8. Acceptance gate before automatic control

Automatic tier or budget mutation remains out of scope until an exact revision has held-out runtime evidence showing all of the following:

1. lower miss/reacquisition cost at the same or better task quality;
2. no increase in stale-state mistakes or scope/profile leakage;
3. positive prefetch net value after unused injection is charged;
4. stable decisions under incomplete/empty telemetry and restart;
5. comparison against a simple fixed-budget + existing activity/decay baseline;
6. retrieval coverage reported separately from generated-answer/task success.

Until then THM exposes recommendations and receipts instead of hidden policy changes.

## Implementation map

- facade: `thm/residency.py`
- validation/catalog: `thm/_residency_common.py`
- telemetry: `thm/residency_telemetry.py`
- T1 locator projection: `thm/residency_directory.py`
- shadow residency/prefetch/budget control: `thm/residency_control.py`
- compatibility research CLI: `research/residency/miss_telemetry.py`
- tests: `tests/test_residency_control.py`, `tests/test_miss_telemetry.py`

The earlier hardware-analogy audit and its evidence boundaries remain in [the preceding design note](13-hardware-inspired-adaptive-residency.md).
