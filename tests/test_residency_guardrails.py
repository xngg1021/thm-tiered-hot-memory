from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from thm.residency import (
    ResidencyError,
    ShadowPlanConfig,
    aggregate_telemetry,
    load_catalog,
    shadow_residency_plan,
    validate_telemetry_event,
)


def item(item_id, tier, *, units=5, penalty=None):
    row = {
        "id": item_id,
        "tier": tier,
        "store": "MEMORY.md" if tier == "T0" else f"warm/{item_id}.md",
        "key": item_id,
        "summary": item_id,
        "created": "2026-09-01",
        "events": [
            {"event_id": f"create:{item_id}", "type": "create", "t": "2026-09-01"}
        ],
        "cost_class": "med",
        "pinned": False,
        "status": "active",
        "resident_units": units,
    }
    if penalty is not None:
        row["miss_penalty_tokens"] = penalty
    return row


class ResidencyGuardrailTests(unittest.TestCase):
    def test_unknown_telemetry_field_fails_fast(self):
        with self.assertRaisesRegex(ResidencyError, "unsupported field avoidble"):
            validate_telemetry_event(
                {
                    "event_id": "e",
                    "task_id": "t",
                    "kind": "resident_miss",
                    "item_id": "a",
                    "avoidble": True,
                }
            )

    def test_prefetch_only_tasks_do_not_dilute_residency_need_rate(self):
        events = [
            {
                "event_id": "m",
                "task_id": "demand",
                "kind": "resident_miss",
                "item_id": "warm",
                "avoidable": True,
                "extra_tokens": 100,
            }
        ]
        events.extend(
            {
                "event_id": f"p{i}",
                "task_id": f"prefetch-only-{i}",
                "kind": "prefetch",
                "item_id": "other",
                "used": False,
            }
            for i in range(20)
        )
        telemetry = aggregate_telemetry(events)
        self.assertEqual(telemetry["tasks"], 21)
        self.assertEqual(telemetry["demand_tasks"], 1)
        self.assertEqual(telemetry["items"]["warm"]["need_task_rate"], 1.0)
        report = shadow_residency_plan(
            [item("warm", "T1", units=5, penalty=100)],
            telemetry,
            now=date(2026, 9, 7),
            budget=10,
            unit_cost=lambda _: None,
            config=ShadowPlanConfig(
                horizon_tasks=1,
                min_tasks=1,
                min_item_demands=1,
                complete_coverage=True,
            ),
        )
        self.assertEqual(report["demand_tasks_observed"], 1)
        self.assertEqual(report["all_tasks_observed"], 21)
        self.assertEqual(report["rows"][0]["need_task_rate"], 1.0)
        self.assertEqual(report["admit"], ["warm"])

    def test_min_item_demands_is_an_actual_admission_gate(self):
        telemetry = aggregate_telemetry(
            [
                {
                    "event_id": "m",
                    "task_id": "t",
                    "kind": "resident_miss",
                    "item_id": "warm",
                    "avoidable": True,
                    "extra_tokens": 1000,
                }
            ]
        )
        report = shadow_residency_plan(
            [item("warm", "T1", units=1, penalty=1000)],
            telemetry,
            now=date(2026, 9, 7),
            budget=10,
            unit_cost=lambda _: None,
            config=ShadowPlanConfig(
                horizon_tasks=10,
                min_tasks=1,
                min_item_demands=2,
                complete_coverage=True,
            ),
        )
        self.assertEqual(report["admit"], [])
        self.assertEqual(report["low_support_item_ids"], ["warm"])
        self.assertEqual(report["rows"][0]["observed_need_events"], 0)

    def test_low_support_current_t0_is_protected_not_false_zero(self):
        telemetry = aggregate_telemetry(
            [
                {
                    "event_id": "h",
                    "task_id": "t",
                    "kind": "resident_hit",
                    "item_id": "hot",
                }
            ]
        )
        report = shadow_residency_plan(
            [item("hot", "T0", units=5, penalty=1000)],
            telemetry,
            now=date(2026, 9, 7),
            budget=10,
            unit_cost=lambda _: None,
            config=ShadowPlanConfig(
                horizon_tasks=10,
                min_tasks=1,
                min_item_demands=2,
                complete_coverage=True,
            ),
        )
        self.assertEqual(report["retain"], ["hot"])
        self.assertEqual(report["evict"], [])
        self.assertIn(
            {"item_id": "hot", "reason": "counterfactual_miss_cost_unknown"},
            report["review_required"],
        )

    def test_exact_plan_has_explicit_resource_guard(self):
        with self.assertRaisesRegex(ResidencyError, "exact shadow-plan limit"):
            shadow_residency_plan(
                [item("a", "T1")],
                aggregate_telemetry([]),
                now=date(2026, 9, 7),
                budget=100_001,
                unit_cost=lambda _: None,
            )

    def test_catalog_wrapper_rejects_ignored_top_level_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "catalog.json"
            path.write_text(
                json.dumps({"items": {}, "unexpected": "ignored-before"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ResidencyError, "top-level field unexpected"):
                load_catalog(path)


if __name__ == "__main__":
    unittest.main()
