"""Explicit, shadow-only miss and prefetch telemetry for THM."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from ._residency_common import (
    PREFETCH_MODES, ResidencyError, _nonempty, _nonnegative_int,
    _nonnegative_number, _ratio, _unit_interval,
)

TELEMETRY_KINDS = {
    "resident_hit", "resident_miss", "hard_miss", "planned_retrieval",
    "prefetch", "stale_resident_failure",
}
DEMAND_KINDS = {"resident_hit", "resident_miss", "hard_miss"}
MISS_KINDS = {"resident_miss", "hard_miss"}

def validate_telemetry_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one explicit telemetry event without upgrading it to a hit."""
    if not isinstance(raw, Mapping):
        raise ResidencyError("event: expected object")
    event = dict(raw)
    event["event_id"] = _nonempty(event.get("event_id"), "event_id")
    event["task_id"] = _nonempty(event.get("task_id"), "task_id")
    event["kind"] = _nonempty(event.get("kind"), "kind")
    if event["kind"] not in TELEMETRY_KINDS:
        raise ResidencyError("kind: unsupported")
    item_id = event.get("item_id")
    if item_id is None and event["kind"] == "stale_resident_failure":
        event["item_id"] = None
    else:
        event["item_id"] = _nonempty(item_id, "item_id")
    event["extra_tokens"] = _nonnegative_int(event.get("extra_tokens", 0), "extra_tokens")
    event["extra_tool_calls"] = _nonnegative_int(event.get("extra_tool_calls", 0), "extra_tool_calls")
    event["extra_latency_ms"] = _nonnegative_number(event.get("extra_latency_ms", 0.0), "extra_latency_ms")
    event["extra_cost_usd"] = _nonnegative_number(event.get("extra_cost_usd", 0.0), "extra_cost_usd")
    avoidable = event.get("avoidable", False)
    if type(avoidable) is not bool:
        raise ResidencyError("avoidable: expected boolean")
    event["avoidable"] = avoidable
    if event["kind"] == "prefetch":
        used = event.get("used")
        if type(used) is not bool:
            raise ResidencyError("used: prefetch events require boolean")
        event["used"] = used
        mode = event.get("mode", "locator")
        if not isinstance(mode, str) or mode not in PREFETCH_MODES:
            raise ResidencyError("mode: prefetch must be locator or tiny_excerpt")
        event["mode"] = mode
        confidence = event.get("confidence")
        event["confidence"] = None if confidence is None else _unit_interval(confidence, "confidence")
        avoided = event.get("avoided_miss")
        if avoided is not None and type(avoided) is not bool:
            raise ResidencyError("avoided_miss: expected boolean when present")
        event["avoided_miss"] = avoided
        for field in ("avoided_extra_tokens", "avoided_extra_tool_calls"):
            event[field] = _nonnegative_int(event.get(field, 0), field)
        for field in ("avoided_extra_latency_ms", "avoided_extra_cost_usd"):
            event[field] = _nonnegative_number(event.get(field, 0.0), field)
    else:
        forbidden = {"used", "mode", "confidence", "avoided_miss", "avoided_extra_tokens", "avoided_extra_tool_calls", "avoided_extra_latency_ms", "avoided_extra_cost_usd"}
        bad = sorted(forbidden.intersection(event))
        if bad:
            raise ResidencyError(f"{bad[0]}: only valid for prefetch events")
    return event


def _blank_item(item_id: str) -> dict[str, Any]:
    return {
        "item_id": item_id, "task_ids": set(), "demand_task_ids": set(),
        "resident_hits": 0, "resident_misses": 0, "hard_misses": 0,
        "planned_retrievals": 0, "stale_resident_failures": 0,
        "miss_extra_tokens": 0, "miss_extra_tool_calls": 0,
        "miss_extra_latency_ms": 0.0, "miss_extra_cost_usd": 0.0,
        "prefetch_count": 0, "prefetch_used": 0,
        "prefetch_avoided_misses": 0, "prefetch_avoided_miss_known": 0,
        "prefetch_tokens": 0, "prefetch_cost_usd": 0.0,
        "prefetch_avoided_extra_tokens": 0, "prefetch_avoided_extra_tool_calls": 0,
        "prefetch_avoided_extra_latency_ms": 0.0, "prefetch_avoided_extra_cost_usd": 0.0,
    }


def aggregate_telemetry(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate global and per-item telemetry without inferring causality."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set(); task_ids: set[str] = set(); per_item: dict[str, dict[str, Any]] = {}
    for raw in events:
        event = validate_telemetry_event(raw)
        if event["event_id"] in seen:
            raise ResidencyError("duplicate event_id")
        seen.add(event["event_id"]); normalized.append(event); task_ids.add(event["task_id"])
        item_id = event.get("item_id")
        if item_id is None:
            continue
        row = per_item.setdefault(item_id, _blank_item(item_id)); kind = event["kind"]
        if kind in DEMAND_KINDS:
            row["demand_task_ids"].add(event["task_id"]); row["task_ids"].add(event["task_id"])
        elif kind == "prefetch" and event["used"]:
            row["task_ids"].add(event["task_id"])
        if kind == "resident_hit": row["resident_hits"] += 1
        elif kind == "resident_miss": row["resident_misses"] += 1
        elif kind == "hard_miss": row["hard_misses"] += 1
        elif kind == "planned_retrieval": row["planned_retrievals"] += 1
        elif kind == "stale_resident_failure": row["stale_resident_failures"] += 1
        elif kind == "prefetch":
            row["prefetch_count"] += 1; row["prefetch_used"] += int(event["used"])
            row["prefetch_tokens"] += event["extra_tokens"]; row["prefetch_cost_usd"] += event["extra_cost_usd"]
            if event["avoided_miss"] is not None:
                row["prefetch_avoided_miss_known"] += 1; row["prefetch_avoided_misses"] += int(event["avoided_miss"])
            row["prefetch_avoided_extra_tokens"] += event["avoided_extra_tokens"]
            row["prefetch_avoided_extra_tool_calls"] += event["avoided_extra_tool_calls"]
            row["prefetch_avoided_extra_latency_ms"] += event["avoided_extra_latency_ms"]
            row["prefetch_avoided_extra_cost_usd"] += event["avoided_extra_cost_usd"]
        if kind in MISS_KINDS:
            row["miss_extra_tokens"] += event["extra_tokens"]; row["miss_extra_tool_calls"] += event["extra_tool_calls"]
            row["miss_extra_latency_ms"] += event["extra_latency_ms"]; row["miss_extra_cost_usd"] += event["extra_cost_usd"]
    by_kind = {kind: 0 for kind in sorted(TELEMETRY_KINDS)}
    for event in normalized: by_kind[event["kind"]] += 1
    demand_count = sum(by_kind[k] for k in DEMAND_KINDS); miss_count = sum(by_kind[k] for k in MISS_KINDS)
    hard_miss_count = by_kind["hard_miss"]
    avoidable_misses = sum(1 for e in normalized if e["kind"] in MISS_KINDS and e["avoidable"])
    miss_events = [e for e in normalized if e["kind"] in MISS_KINDS]
    prefetches = [e for e in normalized if e["kind"] == "prefetch"]
    used_prefetches = [e for e in prefetches if e["used"]]; unused_prefetches = [e for e in prefetches if not e["used"]]
    known_avoided = [e for e in prefetches if e["avoided_miss"] is not None]; avoided_count = sum(1 for e in known_avoided if e["avoided_miss"])
    item_rows: dict[str, dict[str, Any]] = {}
    for item_id in sorted(per_item):
        row = dict(per_item[item_id]); row["task_ids"] = sorted(row["task_ids"]); row["demand_task_ids"] = sorted(row["demand_task_ids"])
        needs = row["resident_hits"] + row["resident_misses"] + row["hard_misses"]
        misses = row["resident_misses"] + row["hard_misses"]
        row["observed_need_events"] = needs; row["observed_miss_events"] = misses
        row["miss_rate"] = _ratio(misses, needs); row["need_task_rate"] = _ratio(len(row["task_ids"]), len(task_ids))
        row["avg_miss_extra_tokens"] = _ratio(row["miss_extra_tokens"], misses)
        row["prefetch_accuracy"] = _ratio(row["prefetch_used"], row["prefetch_count"])
        row["prefetch_coverage_observed"] = _ratio(row["prefetch_avoided_misses"], misses + row["prefetch_avoided_misses"])
        row["prefetch_net_tokens_observed"] = row["prefetch_avoided_extra_tokens"] - row["prefetch_tokens"]
        row["prefetch_net_cost_usd_observed"] = row["prefetch_avoided_extra_cost_usd"] - row["prefetch_cost_usd"]
        item_rows[item_id] = row
    return {
        "events": len(normalized), "tasks": len(task_ids), "by_kind": by_kind, "demand_count": demand_count,
        "resident_miss_rate": _ratio(miss_count, demand_count), "hard_miss_rate": _ratio(hard_miss_count, demand_count),
        "avoidable_miss_rate": _ratio(avoidable_misses, demand_count),
        "miss_penalty": {
            "extra_tokens": sum(e["extra_tokens"] for e in miss_events),
            "extra_tool_calls": sum(e["extra_tool_calls"] for e in miss_events),
            "extra_latency_ms": sum(e["extra_latency_ms"] for e in miss_events),
            "extra_cost_usd": sum(e["extra_cost_usd"] for e in miss_events),
        },
        "planned_retrievals": by_kind["planned_retrieval"],
        "prefetch": {
            "count": len(prefetches), "used": len(used_prefetches), "accuracy": _ratio(len(used_prefetches), len(prefetches)),
            "known_avoided_miss_labels": len(known_avoided), "avoided_misses": avoided_count,
            "coverage_observed": _ratio(avoided_count, miss_count + avoided_count),
            "unused_injected_tokens": sum(e["extra_tokens"] for e in unused_prefetches),
            "unused_cost_usd": sum(e["extra_cost_usd"] for e in unused_prefetches),
            "all_injected_tokens": sum(e["extra_tokens"] for e in prefetches), "all_cost_usd": sum(e["extra_cost_usd"] for e in prefetches),
            "avoided_extra_tokens": sum(e["avoided_extra_tokens"] for e in prefetches),
            "avoided_extra_cost_usd": sum(e["avoided_extra_cost_usd"] for e in prefetches),
            "net_tokens_observed": sum(e["avoided_extra_tokens"] for e in prefetches) - sum(e["extra_tokens"] for e in prefetches),
            "net_cost_usd_observed": sum(e["avoided_extra_cost_usd"] for e in prefetches) - sum(e["extra_cost_usd"] for e in prefetches),
        },
        "stale_resident_failures": by_kind["stale_resident_failure"], "items": item_rows,
        "interpretation": "explicit-shadow-telemetry-not-causal-usage-proof",
    }


def load_telemetry_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path); events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line: continue
            try: value = json.loads(line)
            except json.JSONDecodeError as exc: raise ResidencyError(f"line {line_no}: invalid JSON") from exc
            if not isinstance(value, dict): raise ResidencyError(f"line {line_no}: expected object")
            events.append(value)
    return events
