#!/usr/bin/env python3
"""Shadow-only THM miss/prefetch telemetry.

This module does not mutate THM residency, activity, validity, or native memory
files.  It aggregates externally observed demand/miss/prefetch events so a
future residency controller can be evaluated before it is allowed to steer
memory placement.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable, Mapping, Any

KINDS = {
    "resident_hit",
    "resident_miss",
    "hard_miss",
    "prefetch",
    "stale_resident_failure",
}
DEMAND_KINDS = {"resident_hit", "resident_miss", "hard_miss"}
MISS_KINDS = {"resident_miss", "hard_miss"}


class TelemetryError(ValueError):
    pass


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryError(f"{field}: expected number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise TelemetryError(f"{field}: expected finite nonnegative number")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryError(f"{field}: expected nonnegative integer")
    return value


def validate_event(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TelemetryError("event: expected object")
    event = dict(raw)
    for field in ("event_id", "task_id", "kind"):
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TelemetryError(f"{field}: expected non-empty string")
    if event["kind"] not in KINDS:
        raise TelemetryError("kind: unsupported")

    item_id = event.get("item_id")
    if event["kind"] != "stale_resident_failure":
        if not isinstance(item_id, str) or not item_id.strip():
            raise TelemetryError("item_id: expected non-empty string")
    elif item_id is not None and (not isinstance(item_id, str) or not item_id.strip()):
        raise TelemetryError("item_id: expected non-empty string when present")

    event["extra_tokens"] = _nonnegative_int(event.get("extra_tokens", 0), "extra_tokens")
    event["extra_tool_calls"] = _nonnegative_int(
        event.get("extra_tool_calls", 0), "extra_tool_calls"
    )
    event["extra_latency_ms"] = _nonnegative_number(
        event.get("extra_latency_ms", 0.0), "extra_latency_ms"
    )
    event["extra_cost_usd"] = _nonnegative_number(
        event.get("extra_cost_usd", 0.0), "extra_cost_usd"
    )

    avoidable = event.get("avoidable", False)
    if type(avoidable) is not bool:
        raise TelemetryError("avoidable: expected boolean")
    event["avoidable"] = avoidable

    if event["kind"] == "prefetch":
        used = event.get("used")
        if type(used) is not bool:
            raise TelemetryError("used: prefetch events require boolean")
    elif "used" in event:
        raise TelemetryError("used: only valid for prefetch events")

    return event


def aggregate(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = []
    seen = set()
    for raw in events:
        event = validate_event(raw)
        if event["event_id"] in seen:
            raise TelemetryError("duplicate event_id")
        seen.add(event["event_id"])
        normalized.append(event)

    by_kind = {kind: 0 for kind in sorted(KINDS)}
    for event in normalized:
        by_kind[event["kind"]] += 1

    demand_count = sum(by_kind[kind] for kind in DEMAND_KINDS)
    miss_count = sum(by_kind[kind] for kind in MISS_KINDS)
    hard_miss_count = by_kind["hard_miss"]
    avoidable_misses = sum(
        1 for event in normalized
        if event["kind"] in MISS_KINDS and event["avoidable"]
    )

    miss_events = [event for event in normalized if event["kind"] in MISS_KINDS]
    prefetches = [event for event in normalized if event["kind"] == "prefetch"]
    used_prefetches = [event for event in prefetches if event["used"]]
    unused_prefetches = [event for event in prefetches if not event["used"]]

    def ratio(num: int, den: int):
        return None if den == 0 else num / den

    return {
        "events": len(normalized),
        "by_kind": by_kind,
        "demand_count": demand_count,
        "resident_miss_rate": ratio(miss_count, demand_count),
        "hard_miss_rate": ratio(hard_miss_count, demand_count),
        "avoidable_miss_rate": ratio(avoidable_misses, demand_count),
        "miss_penalty": {
            "extra_tokens": sum(e["extra_tokens"] for e in miss_events),
            "extra_tool_calls": sum(e["extra_tool_calls"] for e in miss_events),
            "extra_latency_ms": sum(e["extra_latency_ms"] for e in miss_events),
            "extra_cost_usd": sum(e["extra_cost_usd"] for e in miss_events),
        },
        "prefetch": {
            "count": len(prefetches),
            "used": len(used_prefetches),
            "accuracy": ratio(len(used_prefetches), len(prefetches)),
            "unused_injected_tokens": sum(e["extra_tokens"] for e in unused_prefetches),
            "unused_cost_usd": sum(e["extra_cost_usd"] for e in unused_prefetches),
        },
        "stale_resident_failures": by_kind["stale_resident_failure"],
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TelemetryError(f"line {line_no}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise TelemetryError(f"line {line_no}: expected object")
            events.append(value)
    return events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSONL telemetry trace")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    report = aggregate(load_jsonl(args.trace))
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None,
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
