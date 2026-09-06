"""Public shadow-residency API for THM.

All functions are read-only recommendations/measurement. They do not mutate
T0/T1/T2/T3 placement, activity, validity, or native memory files.
"""
from ._residency_common import ResidencyError, apply_catalog, load_catalog
from .residency_telemetry import (
    aggregate_telemetry, load_telemetry_jsonl, validate_telemetry_event,
)
from .residency_directory import project_warm_directory
from .residency_control import (
    BudgetControllerConfig, ShadowPlanConfig, shadow_prefetch_plan,
    shadow_residency_plan, suggest_resident_budget,
)

__all__ = [
    "ResidencyError", "apply_catalog", "load_catalog",
    "aggregate_telemetry", "load_telemetry_jsonl", "validate_telemetry_event",
    "project_warm_directory", "BudgetControllerConfig", "ShadowPlanConfig",
    "shadow_prefetch_plan", "shadow_residency_plan", "suggest_resident_budget",
]
