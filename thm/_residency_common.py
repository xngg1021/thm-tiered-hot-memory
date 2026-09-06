"""Shared validation and canonical-overlay helpers for THM shadow residency."""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

VALID_TIERS = {"T0", "T1", "T2", "T3"}
VALID_STATUS = {"active", "invalid", "deleted", "unresolved_legacy"}
VALID_COST_CLASS = {"low", "med", "high"}
PREFETCH_MODES = {"locator", "tiny_excerpt"}


class ResidencyError(ValueError):
    """Structured input/measurement failure for shadow residency tools."""


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResidencyError(f"{field}: expected non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResidencyError(f"{field}: expected nonnegative integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ResidencyError(f"{field}: expected positive integer")
    return value


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResidencyError(f"{field}: expected number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ResidencyError(f"{field}: expected finite nonnegative number")
    return result


def _unit_interval(value: Any, field: str) -> float:
    result = _nonnegative_number(value, field)
    if result > 1:
        raise ResidencyError(f"{field}: expected value in [0, 1]")
    return result


def _ratio(num: int | float, den: int | float) -> float | None:
    return None if den == 0 else num / den


def load_catalog(path: str | Path | None) -> dict[str, dict[str, Any]]:
    """Load an optional non-authoritative metadata overlay keyed by item id."""
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "items" in raw:
        raw = raw["items"]
    if not isinstance(raw, dict):
        raise ResidencyError("catalog: expected object keyed by item id")
    out: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        item_id = _nonempty(key, "catalog item id")
        if not isinstance(value, dict):
            raise ResidencyError(f"catalog[{item_id}]: expected object")
        allowed = {
            "resident_units",
            "miss_penalty_tokens",
            "locator",
            "scope",
            "project",
            "profile",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ResidencyError(f"catalog[{item_id}]: unsupported field {unknown[0]}")
        row = dict(value)
        if "resident_units" in row:
            row["resident_units"] = _positive_int(row["resident_units"], "resident_units")
        if "miss_penalty_tokens" in row:
            row["miss_penalty_tokens"] = _nonnegative_number(
                row["miss_penalty_tokens"], "miss_penalty_tokens"
            )
        if "locator" in row:
            row["locator"] = _nonempty(row["locator"], "locator")
        for field in ("scope", "project", "profile"):
            if field in row:
                row[field] = _nonempty(row[field], field)
        out[item_id] = row
    return out


def apply_catalog(
    entries: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Apply a read-only overlay; stale/unknown catalog identities fail explicitly."""
    canonical: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise ResidencyError("entry: expected object")
        entry = dict(raw)
        item_id = _nonempty(entry.get("id"), "entry id")
        if item_id in ids:
            raise ResidencyError("duplicate entry id")
        ids.add(item_id)
        canonical.append(entry)
    unknown_ids = sorted(set(catalog) - ids)
    if unknown_ids:
        raise ResidencyError(f"catalog references unknown item id {unknown_ids[0]}")
    result: list[dict[str, Any]] = []
    allowed = {
        "resident_units",
        "miss_penalty_tokens",
        "locator",
        "scope",
        "project",
        "profile",
    }
    for entry in canonical:
        item_id = entry["id"]
        overlay = catalog.get(item_id, {})
        if not isinstance(overlay, Mapping):
            raise ResidencyError(f"catalog[{item_id}]: expected object")
        unknown = sorted(set(overlay) - allowed)
        if unknown:
            raise ResidencyError(f"catalog[{item_id}]: unsupported field {unknown[0]}")
        entry.update(dict(overlay))
        result.append(entry)
    return result


def _parse_day(value: Any, field: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ResidencyError(f"{field}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ResidencyError(f"{field}: invalid calendar date") from exc


def _entry_current(entry: Mapping[str, Any], now: date) -> bool:
    status = entry.get("status")
    if status not in VALID_STATUS:
        raise ResidencyError("entry status: unsupported")
    if status != "active":
        return False
    if entry.get("valid_from") and now < _parse_day(entry["valid_from"], "valid_from"):
        return False
    if entry.get("valid_until") and now >= _parse_day(entry["valid_until"], "valid_until"):
        return False
    if entry.get("valid_from") and entry.get("valid_until"):
        if _parse_day(entry["valid_from"], "valid_from") >= _parse_day(entry["valid_until"], "valid_until"):
            raise ResidencyError("invalid validity interval")
    return True


def _sanitize_field(value: Any, limit: int = 120) -> str:
    text = " ".join(str(value).replace("|", "/").split())
    return text[:limit]


def _safe_locator(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("\\", "/")
    if "\x00" in text or text.startswith("~") or re.match(r"^[A-Za-z]:[/\\]", value.strip()):
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or any(part in ("", ".") for part in path.parts):
        return None
    return text


def _entry_locator(entry: Mapping[str, Any]) -> str | None:
    if "locator" in entry:
        return _safe_locator(entry.get("locator"))
    store = entry.get("store")
    if store in ("MEMORY.md", "USER.md"):
        return None
    return _safe_locator(store)


def _entry_scope(entry: Mapping[str, Any]) -> str:
    for field in ("scope", "project", "profile"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return _sanitize_field(value, 80)
    return "profile-local"


def _latest_entry_day(entry: Mapping[str, Any]) -> date:
    values: list[date] = []
    if entry.get("created"):
        values.append(_parse_day(entry["created"], "created"))
    if entry.get("valid_from"):
        values.append(_parse_day(entry["valid_from"], "valid_from"))
    events = entry.get("events", [])
    if not isinstance(events, list):
        raise ResidencyError("events: expected list")
    for event in events:
        if not isinstance(event, Mapping):
            raise ResidencyError("event: expected object")
        if event.get("t"):
            values.append(_parse_day(event["t"], "event date"))
    if not values:
        raise ResidencyError("entry requires created or dated event")
    return max(values)
