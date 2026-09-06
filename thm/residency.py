"""Public shadow-residency API for THM.

All functions are read-only recommendations/measurement. They do not mutate
T0/T1/T2/T3 placement, activity, validity, or native memory files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._residency_common import (
    ResidencyError,
    apply_catalog,
    load_catalog as _load_catalog,
)
from .residency_telemetry import (
    aggregate_telemetry,
    load_telemetry_jsonl,
    validate_telemetry_event,
)
from .residency_directory import project_warm_directory
from .residency_control import (
    BudgetControllerConfig,
    ShadowPlanConfig,
    shadow_prefetch_plan,
    shadow_residency_plan as _shadow_residency_plan,
    suggest_resident_budget,
)

_MAX_EXACT_BUDGET_UNITS = 100_000
_MAX_EXACT_PLAN_ITEMS = 1_024


def load_catalog(path: str | Path | None):
    """Load a strict catalog; wrapper metadata must not be silently ignored."""
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "items" in raw:
        unknown = sorted(set(raw) - {"items"})
        if unknown:
            raise ResidencyError(f"catalog: unsupported top-level field {unknown[0]}")
    return _load_catalog(path)


def _threshold_item_evidence(
    entries: Sequence[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    config: ShadowPlanConfig,
):
    """Suppress sub-threshold per-item evidence without treating it as zero truth."""
    item_stats = telemetry.get("items", {})
    if not isinstance(item_stats, Mapping):
        raise ResidencyError("telemetry.items: expected object")
    adjusted_stats: dict[str, Any] = {}
    low_support: set[str] = set()
    for item_id, raw in item_stats.items():
        if not isinstance(item_id, str) or not item_id:
            raise ResidencyError("telemetry item id: expected non-empty string")
        if not isinstance(raw, Mapping):
            raise ResidencyError(f"telemetry.items[{item_id}]: expected object")
        stats = dict(raw)
        demand = stats.get("observed_need_events", 0)
        if isinstance(demand, bool) or not isinstance(demand, int) or demand < 0:
            raise ResidencyError("observed_need_events: expected nonnegative integer")
        if 0 < demand < config.min_item_demands:
            low_support.add(item_id)
            stats["demand_task_ids"] = []
            stats["observed_need_events"] = 0
            stats["observed_miss_events"] = 0
            stats["avoidable_miss_events"] = 0
            stats["miss_extra_tokens"] = 0
            stats["miss_extra_tool_calls"] = 0
            stats["miss_extra_latency_ms"] = 0.0
            stats["miss_extra_cost_usd"] = 0.0
            stats["avoidable_miss_extra_tokens"] = 0
            stats["avoidable_miss_extra_tool_calls"] = 0
            stats["avoidable_miss_extra_latency_ms"] = 0.0
            stats["avoidable_miss_extra_cost_usd"] = 0.0
        adjusted_stats[item_id] = stats

    adjusted_entries = []
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise ResidencyError("entry: expected object")
        entry = dict(raw)
        item_id = entry.get("id")
        if item_id in low_support and entry.get("tier") == "T0":
            # A caller-supplied counterfactual penalty is not enough to infer
            # frequency from fewer observations than the configured gate.
            entry.pop("miss_penalty_tokens", None)
        adjusted_entries.append(entry)
    return adjusted_entries, adjusted_stats, sorted(low_support)


def shadow_residency_plan(
    entries: Sequence[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    *,
    now,
    budget: int,
    unit_cost,
    config: ShadowPlanConfig = ShadowPlanConfig(),
    activity_fn=None,
):
    """Guard and run the exact shadow plan using demand-task opportunity counts."""
    if type(budget) is not int or budget < 0:
        raise ResidencyError("budget: expected nonnegative integer")
    if budget > _MAX_EXACT_BUDGET_UNITS:
        raise ResidencyError(
            f"budget exceeds exact shadow-plan limit {_MAX_EXACT_BUDGET_UNITS}"
        )
    if len(entries) > _MAX_EXACT_PLAN_ITEMS:
        raise ResidencyError(
            f"entry count exceeds exact shadow-plan limit {_MAX_EXACT_PLAN_ITEMS}"
        )
    if not isinstance(telemetry, Mapping):
        raise ResidencyError("telemetry: expected aggregate object")

    demand_tasks = telemetry.get("demand_tasks", telemetry.get("tasks"))
    if isinstance(demand_tasks, bool) or not isinstance(demand_tasks, int) or demand_tasks < 0:
        raise ResidencyError("telemetry.demand_tasks: expected nonnegative integer")
    guarded_telemetry = dict(telemetry)
    # Internal policy code historically consumed `tasks`; for residency
    # opportunity rates this must be explicit-demand tasks, never prefetch-only
    # or planned-retrieval-only tasks.
    guarded_telemetry["tasks"] = demand_tasks
    adjusted_entries, adjusted_stats, low_support = _threshold_item_evidence(
        entries, guarded_telemetry, config
    )
    guarded_telemetry["items"] = adjusted_stats

    report = _shadow_residency_plan(
        adjusted_entries,
        guarded_telemetry,
        now=now,
        budget=budget,
        unit_cost=unit_cost,
        config=config,
        activity_fn=activity_fn,
    )
    report = dict(report)
    report["all_tasks_observed"] = telemetry.get("tasks", demand_tasks)
    report["demand_tasks_observed"] = demand_tasks
    report["min_item_demands_applied"] = config.min_item_demands
    report["low_support_item_ids"] = low_support
    report["exact_limits"] = {
        "budget_units": _MAX_EXACT_BUDGET_UNITS,
        "items": _MAX_EXACT_PLAN_ITEMS,
    }
    return report


__all__ = [
    "ResidencyError",
    "apply_catalog",
    "load_catalog",
    "aggregate_telemetry",
    "load_telemetry_jsonl",
    "validate_telemetry_event",
    "project_warm_directory",
    "BudgetControllerConfig",
    "ShadowPlanConfig",
    "shadow_prefetch_plan",
    "shadow_residency_plan",
    "suggest_resident_budget",
]
