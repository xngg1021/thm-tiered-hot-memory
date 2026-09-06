"""Deterministic locator-only T1 warm-directory projection for THM."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Mapping, Sequence

from ._residency_common import (
    VALID_COST_CLASS, VALID_TIERS, ResidencyError, _entry_current,
    _entry_locator, _entry_scope, _latest_entry_day, _nonempty, _sanitize_field,
)

def project_warm_directory(entries: Sequence[Mapping[str, Any]], *, now: date,
                           budget: int | None, count_units: Callable[[str], int]) -> dict[str, Any]:
    """Derive a compact T1 locator directory; never emit summaries as evidence."""
    if budget is not None and (type(budget) is not int or budget < 0):
        raise ResidencyError("budget: expected nonnegative integer or null")
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    unlocatable: list[str] = []; excluded: list[dict[str, str]] = []; seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, Mapping): raise ResidencyError("entry: expected object")
        item_id = _nonempty(raw.get("id"), "entry id")
        if item_id in seen: raise ResidencyError("duplicate entry id")
        seen.add(item_id)
        tier = raw.get("tier")
        if tier not in VALID_TIERS: raise ResidencyError("entry tier: unsupported")
        if tier != "T1": continue
        if not _entry_current(raw, now):
            excluded.append({"item_id": item_id, "reason": "status_or_validity"}); continue
        locator = _entry_locator(raw)
        if locator is None:
            unlocatable.append(item_id); continue
        topic = _sanitize_field(raw.get("key") or item_id, 80); scope = _entry_scope(raw)
        latest = _latest_entry_day(raw); key = (topic, scope, locator)
        row = groups.setdefault(key, {"topic": topic, "scope": scope, "locator": locator,
            "item_ids": [], "latest": latest, "pinned": False, "cost_priority": 0, "revision": "-"})
        row["item_ids"].append(item_id)
        if latest >= row["latest"]:
            row["latest"] = latest; source_hash = raw.get("source_hash")
            row["revision"] = source_hash[:12] if isinstance(source_hash, str) and source_hash else "-"
        pinned = raw.get("pinned", False)
        if type(pinned) is not bool: raise ResidencyError("pinned: expected boolean")
        row["pinned"] = row["pinned"] or pinned
        cost_class = raw.get("cost_class", "med")
        if cost_class not in VALID_COST_CLASS: raise ResidencyError("cost_class: unsupported")
        row["cost_priority"] = max(row["cost_priority"], {"low": 1, "med": 2, "high": 3}[cost_class])
    rows: list[dict[str, Any]] = []
    for row in groups.values():
        line = (f"{row['topic']} | {row['scope']} | {len(row['item_ids'])} current | "
                f"{row['latest'].isoformat()} | rev:{row['revision']} | {row['locator']}")
        units = count_units(line + "\n")
        if type(units) is not int or units < 0: raise ResidencyError("count_units: expected nonnegative integer")
        rows.append({"topic": row["topic"], "scope": row["scope"], "locator": row["locator"],
            "item_ids": sorted(row["item_ids"]), "current_items": len(row["item_ids"]),
            "latest": row["latest"].isoformat(), "revision": row["revision"], "line": line,
            "units": units, "pinned": row["pinned"], "cost_priority": row["cost_priority"]})
    rows.sort(key=lambda r: (-int(r["pinned"]), -r["cost_priority"], -r["current_items"], r["topic"], r["locator"]))
    selected: list[dict[str, Any]] = []; dropped: list[dict[str, Any]] = []; used = 0
    for row in rows:
        if budget is None or used + row["units"] <= budget:
            selected.append(row); used += row["units"]
        else:
            dropped.append({"topic": row["topic"], "scope": row["scope"], "locator": row["locator"],
                            "units": row["units"], "reason": "directory_budget"})
    return {"status": "OK", "tier": "T1", "projection": "locator_only",
        "lines": [r["line"] for r in selected], "selected": selected, "dropped": dropped,
        "unlocatable_item_ids": sorted(unlocatable), "excluded": sorted(excluded, key=lambda r: r["item_id"]),
        "budget": budget, "budget_used": used, "changes_applied": False}
