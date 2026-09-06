"""THM 1.4 Hermes provider with optional locator-only T1 directory injection.

The base retrieval/provider lifecycle remains in ``thm.hermes_plugin``. This
subclass adds only an opt-in, session-snapshot directory projection. It never
refreshes the current prompt after a native memory write; a later session
rebuild is required, matching Hermes' frozen system-prompt semantics.
"""
from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path

from scripts.thm import Engine

from .hermes_plugin import THMProvider as _BaseTHMProvider
from .residency import apply_catalog, load_catalog, project_warm_directory


_CATALOG_NAME = "residency-catalog.json"
_MAX_WARM_DIRECTORY_BUDGET = 4096


def _warm_budget(value) -> int:
    try:
        budget = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("warm_directory_budget must be an integer") from exc
    if not 0 <= budget <= _MAX_WARM_DIRECTORY_BUDGET:
        raise ValueError(
            f"warm_directory_budget must be between 0 and {_MAX_WARM_DIRECTORY_BUDGET}"
        )
    return budget


def _validate_selected_locators(mem_dir: Path, report: dict) -> None:
    """Ensure every injected locator resolves to an existing file inside memories/."""
    root = mem_dir.resolve()
    selected = report.get("selected", [])
    if not isinstance(selected, list):
        raise ValueError("THM warm directory selected rows are invalid")
    for row in selected:
        if not isinstance(row, dict) or not isinstance(row.get("locator"), str):
            raise ValueError("THM warm directory selected locator is invalid")
        locator = row["locator"]
        candidate = mem_dir / locator
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"THM warm locator target does not exist: {locator}") from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"THM warm locator escapes memories directory: {locator}") from exc
        if not resolved.is_file():
            raise ValueError(f"THM warm locator target is not a file: {locator}")


class THMProvider(_BaseTHMProvider):
    """Current THM provider; 1.4 warm-directory injection defaults to disabled."""

    def __init__(self, config=None):
        super().__init__(config=config)
        self._hermes_home: Path | None = None
        self._warm_directory_budget = 0
        self._warm_directory_block = ""
        self._warm_directory_report = None

    def _merged_config(self, hermes_home=None):
        merged = super()._merged_config(hermes_home)
        env = os.environ.get("THM_WARM_DIRECTORY_BUDGET")
        if env not in (None, ""):
            merged["warm_directory_budget"] = env
        return merged

    def _availability_error(self):
        error = super()._availability_error()
        if error:
            return error
        try:
            _warm_budget(self._merged_config().get("warm_directory_budget", 0))
            return ""
        except Exception as exc:
            return f"THM warm-directory configuration unavailable: {exc}"

    def get_config_schema(self):
        schema = list(super().get_config_schema())
        schema.append({
            "key": "warm_directory_budget",
            "description": "Optional T1 locator-only system-prompt directory budget; 0 disables it",
            "default": 0,
            "type": "integer",
            "minimum": 0,
            "maximum": _MAX_WARM_DIRECTORY_BUDGET,
        })
        return schema

    def save_config(self, values, hermes_home):
        if not isinstance(values, dict):
            raise ValueError("THM config must be a mapping")
        if "warm_directory_budget" in values:
            _warm_budget(values["warm_directory_budget"])
        super().save_config(values, hermes_home)

    def _refresh_warm_directory(self) -> None:
        self._warm_directory_block = ""
        self._warm_directory_report = None
        if self._warm_directory_budget <= 0 or self._hermes_home is None:
            return
        mem_dir = self._hermes_home / "memories"
        state_dir = mem_dir / ".thm"
        entries = Engine(mem_dir, state_dir).load().data["entries"]
        catalog_path = state_dir / _CATALOG_NAME
        catalog = load_catalog(catalog_path) if catalog_path.is_file() else {}
        entries = apply_catalog(entries, catalog)
        header = (
            "THM T1 warm locator directory. Locators are navigation hints only; "
            "retrieve source content before treating it as evidence."
        )
        header_units = self.counter(header + "\n")
        if header_units >= self._warm_directory_budget:
            self._warm_directory_report = {
                "status": "HEADER_EXCEEDS_BUDGET",
                "budget": self._warm_directory_budget,
                "budget_used": 0,
                "lines": [],
                "changes_applied": False,
            }
            return
        report = project_warm_directory(
            entries,
            now=date.today(),
            budget=self._warm_directory_budget - header_units,
            count_units=lambda text: self.counter("- " + text),
        )
        _validate_selected_locators(mem_dir, report)
        lines = report["lines"]
        if not lines:
            self._warm_directory_report = report
            return
        block = header + "\n" + "\n".join("- " + line for line in lines)
        total = self.counter(block)
        if total > self._warm_directory_budget:
            raise ValueError("THM warm directory exceeds its configured budget")
        report = dict(report)
        report["budget"] = self._warm_directory_budget
        report["budget_used"] = total
        report["locator_targets_verified"] = True
        self._warm_directory_report = report
        self._warm_directory_block = block

    def initialize(self, session_id, **kwargs):
        home = kwargs.get("hermes_home")
        super().initialize(session_id, **kwargs)
        with self._lock:
            self._hermes_home = Path(home).expanduser().resolve()
            cfg = self._merged_config(home)
            self._warm_directory_budget = _warm_budget(
                cfg.get("warm_directory_budget", 0)
            )
            self._refresh_warm_directory()

    def system_prompt_block(self):
        with self._lock:
            return self._warm_directory_block

    def on_session_switch(self, new_session_id, **kwargs):
        super().on_session_switch(new_session_id, **kwargs)
        with self._lock:
            # A new session can receive a newly derived frozen directory snapshot.
            self._refresh_warm_directory()

    def handle_tool_call(self, tool_name, args, **kwargs):
        raw = super().handle_tool_call(tool_name, args, **kwargs)
        if tool_name != "thm_recall_status":
            return raw
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw
        with self._lock:
            payload["warm_directory"] = {
                "enabled": self._warm_directory_budget > 0,
                "budget": self._warm_directory_budget,
                "budget_used": (
                    self._warm_directory_report.get("budget_used", 0)
                    if isinstance(self._warm_directory_report, dict)
                    else 0
                ),
                "lines": (
                    len(self._warm_directory_report.get("lines", []))
                    if isinstance(self._warm_directory_report, dict)
                    else 0
                ),
                "locator_targets_verified": (
                    self._warm_directory_report.get("locator_targets_verified", False)
                    if isinstance(self._warm_directory_report, dict)
                    else False
                ),
                "snapshot_refresh": "session_boundary_only",
            }
        return json.dumps(payload)

    def shutdown(self):
        with self._lock:
            self._warm_directory_block = ""
            self._warm_directory_report = None
            self._hermes_home = None
        super().shutdown()


def register(ctx):
    ctx.register_memory_provider(THMProvider())
