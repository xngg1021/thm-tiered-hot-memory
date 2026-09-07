# THM 1.4 Hermes opt-in T1 warm-directory snapshot

<!-- current-v1.4-status:start -->
> **Release status — accepted/stable opt-in runtime surface.** The implementation described here is part of THM 1.4.0 frozen at `e6e4dda5835e3cb345207457d5491131c6959b2c` with recovery pointer `archive/v1.4.0-stable`. It is disabled by default, session-frozen when enabled, and remains independent of the shadow residency/prefetch/budget recommender.
<!-- current-v1.4-status:end -->

> Runtime surface added 2026-09-07. The **T0–T3 tier model is unchanged**. This feature only exposes a compact T1 locator projection to Hermes at a session boundary; it does not enable the shadow residency/prefetch/budget controller and does not perform a tier move.

## 1. Default behavior

The feature is disabled by default:

```text
warm_directory_budget = 0
```

When disabled, the 1.4 provider behaves like the prior THM Hermes provider for system-prompt injection: `system_prompt_block()` returns no T1 directory block.

The package entry point is:

```text
thm.hermes_v14_plugin:THMProvider
```

The existing retrieval/provider lifecycle remains implemented by `thm.hermes_plugin.THMProvider`; the 1.4 provider subclasses it and adds only this opt-in directory snapshot.

## 2. Enabling the snapshot

The provider accepts `warm_directory_budget` through the normal provider configuration. `THM_WARM_DIRECTORY_BUDGET` is the environment override. The accepted range is `0..4096`; invalid values make provider availability fail explicitly.

A local measurement/projection catalog, when needed, is read from:

```text
<hermes_home>/memories/.thm/residency-catalog.json
```

The catalog remains non-authoritative. It cannot override canonical tier, status, validity, pinning, events or source identity. Unknown/stale item IDs fail instead of silently disappearing.

## 3. What is injected

When the budget is positive, THM derives the T1 directory described in [the 1.4 control-plane document](14-residency-control-plane.md). The block contains a short warning followed by budgeted locator rows.

A row is derived from:

```text
safe locator stem | scope | current item count | latest date | revision prefix | locator
```

The block does **not** use the historical index `key`, `summary` or source body as its display topic. This is important because historical keys may be prefixes of private source text.

Every selected locator is verified before injection:

1. the locator string must already pass THM's relative-path checks;
2. the target must exist;
3. resolving symlinks must still remain inside the current profile's `memories/` directory;
4. the resolved target must be a file.

A missing or escaping selected target fails the opt-in snapshot instead of injecting a dangling or cross-profile locator.

The directory header explicitly says that locators are navigation hints and that source content must be retrieved before being treated as evidence.

## 4. Frozen-session semantics

The runtime follows Hermes' frozen session-prompt behavior:

```text
session start/switch
    -> derive current T1 locator snapshot
    -> inject frozen directory block

native memory write during that session
    -> persistent files/index may change through their own owner
    -> current T1 directory block does not refresh

next session switch/start
    -> derive a new directory snapshot
```

`on_memory_write` therefore does not mutate the current session prompt. `on_session_switch` rebuilds the locator projection from current canonical state.

This preserves the correctness boundary established by the current Hermes memory model: a mid-session persistent-memory write is not automatically reinterpreted as an immediate prompt rebuild.

## 5. Budget accounting

The configured budget covers the serialized THM directory block, including its warning header and list markers. THM counts with the provider's configured counter.

If the header alone consumes the configured budget, the report returns `HEADER_EXCEEDS_BUDGET` and injects no rows. Selected rows are packed deterministically within the remaining budget. A post-build check rejects any block that exceeds the configured total.

This is a **directory budget**, not a new T0 memory budget and not a global context-window budget.

## 6. Status observability

`thm_recall_status` adds a `warm_directory` object when the 1.4 provider is installed:

```json
{
  "enabled": true,
  "budget": 400,
  "budget_used": 126,
  "lines": 2,
  "locator_targets_verified": true,
  "snapshot_refresh": "session_boundary_only"
}
```

These fields report what the provider injected. They do not prove that the model used a locator or that the corresponding source improved the task.

## 7. Mutation boundary

The runtime directory path is intentionally read-only with respect to THM memory state. Tests exercise a real temporary `MEMORY.md`, `USER.md`, `.thm/index.json`, catalog and directory files, then byte-compare the canonical index and native memory files before and after the 1.4 CLI/provider operations.

The opt-in directory does not:

- create `hit` or `confirm` events;
- promote a T1 item to T0;
- extend validity;
- rewrite warm files;
- change the residency catalog;
- change Hermes' native memory files;
- turn a locator into evidence;
- activate shadow automatic tier or budget mutation.

## 8. Evidence boundary

The provider lifecycle and prompt-block invariants can be tested against pinned/current Hermes upstream revisions. That verifies integration behavior and read-only/frozen-snapshot contracts.

It does **not** establish that enabling the directory improves real task success, latency or total cost. That requires held-out runtime A/B tasks with the directory disabled/enabled and explicit accounting for locator-token carry, retrieval calls, miss avoidance and generated-answer/task quality.

## Unreleased retrieval successor

The opt-in Python entity projection and its Protocol 2 evidence are documented in [the zero-LLM frontier](16-zero-llm-retrieval-frontier.md). It does not enable a harness option, change residency/activity/validity semantics, or move the 1.4 stable pointer.
