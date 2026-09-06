import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "miss_telemetry", ROOT / "research" / "residency" / "miss_telemetry.py"
)
mt = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mt)


class MissTelemetryTests(unittest.TestCase):
    def test_aggregate_separates_miss_penalty_and_prefetch_waste(self):
        events = [
            {"event_id":"1","task_id":"t1","kind":"resident_hit","item_id":"a"},
            {"event_id":"2","task_id":"t1","kind":"resident_miss","item_id":"b",
             "avoidable":True,"extra_tokens":100,"extra_tool_calls":1,
             "extra_latency_ms":20,"extra_cost_usd":0.01},
            {"event_id":"3","task_id":"t2","kind":"hard_miss","item_id":"c",
             "extra_tokens":50,"extra_latency_ms":30,"extra_cost_usd":0.02},
            {"event_id":"4","task_id":"t2","kind":"prefetch","item_id":"d",
             "used":False,"extra_tokens":40,"extra_cost_usd":0.004},
            {"event_id":"5","task_id":"t3","kind":"prefetch","item_id":"e",
             "used":True,"extra_tokens":20,"extra_cost_usd":0.002},
        ]
        report = mt.aggregate(events)
        self.assertAlmostEqual(report["resident_miss_rate"], 2/3)
        self.assertAlmostEqual(report["hard_miss_rate"], 1/3)
        self.assertAlmostEqual(report["avoidable_miss_rate"], 1/3)
        self.assertEqual(report["miss_penalty"]["extra_tokens"], 150)
        self.assertEqual(report["miss_penalty"]["extra_tool_calls"], 1)
        self.assertAlmostEqual(report["miss_penalty"]["extra_latency_ms"], 50)
        self.assertAlmostEqual(report["miss_penalty"]["extra_cost_usd"], 0.03)
        self.assertAlmostEqual(report["prefetch"]["accuracy"], 0.5)
        self.assertEqual(report["prefetch"]["unused_injected_tokens"], 40)

    def test_no_demand_reports_none_not_zero(self):
        report = mt.aggregate([
            {"event_id":"1","task_id":"t1","kind":"prefetch","item_id":"a",
             "used":False}
        ])
        self.assertIsNone(report["resident_miss_rate"])
        self.assertIsNone(report["hard_miss_rate"])

    def test_duplicate_event_id_rejected(self):
        with self.assertRaisesRegex(mt.TelemetryError, "duplicate event_id"):
            mt.aggregate([
                {"event_id":"x","task_id":"t1","kind":"resident_hit","item_id":"a"},
                {"event_id":"x","task_id":"t2","kind":"resident_hit","item_id":"b"},
            ])

    def test_negative_penalty_rejected(self):
        with self.assertRaisesRegex(mt.TelemetryError, "extra_tokens"):
            mt.validate_event({
                "event_id":"1","task_id":"t","kind":"resident_miss","item_id":"a",
                "extra_tokens":-1
            })

    def test_prefetch_requires_explicit_used_label(self):
        with self.assertRaisesRegex(mt.TelemetryError, "used"):
            mt.validate_event({
                "event_id":"1","task_id":"t","kind":"prefetch","item_id":"a"
            })


if __name__ == "__main__":
    unittest.main()
