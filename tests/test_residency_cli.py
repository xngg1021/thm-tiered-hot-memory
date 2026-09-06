import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

from thm import __main__ as cli


class ResidencyCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.mem = self.root / "profile" / "memories"
        self.state = self.mem / ".thm"
        self.mem.mkdir(parents=True)
        (self.mem / "MEMORY.md").write_text("hot setting\n§\nwarm database note", encoding="utf-8")
        (self.mem / "USER.md").write_text("", encoding="utf-8")
        legacy = cli.legacy_engine()
        self.engine = legacy.Engine(self.mem, self.state, clock=lambda: dt.date(2026, 9, 6))
        self.engine.seed()
        rows = self.engine.load().data["entries"]
        self.hot = next(r for r in rows if r["key"].startswith("hot setting"))
        self.warm = next(r for r in rows if r["key"].startswith("warm database"))

        def move_warm(data):
            for row in data["entries"]:
                if row["id"] == self.warm["id"]:
                    row["tier"] = "T1"
            return None
        self.engine.update(move_warm)

        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({
            "items": {
                self.warm["id"]: {
                    "resident_units": 12,
                    "miss_penalty_tokens": 500,
                    "locator": "warm/database.md",
                    "scope": "test-profile"
                }
            }
        }), encoding="utf-8")
        self.trace = self.root / "events.jsonl"
        events = []
        for idx in (1, 2):
            task = f"t{idx}"
            events.append({"event_id": f"h{idx}", "task_id": task,
                           "kind": "resident_hit", "item_id": self.hot["id"]})
            events.append({"event_id": f"m{idx}", "task_id": task,
                           "kind": "resident_miss", "item_id": self.warm["id"],
                           "avoidable": True, "extra_tokens": 500,
                           "extra_tool_calls": 1, "extra_latency_ms": 20})
        self.trace.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(args)
        return rc, out.getvalue(), err.getvalue()

    def identity(self):
        return {
            "index": self.engine.index.read_bytes(),
            "memory": (self.mem / "MEMORY.md").read_bytes(),
            "user": (self.mem / "USER.md").read_bytes(),
        }

    def test_all_residency_cli_paths_are_read_only(self):
        before = self.identity()
        common = ["--mem-dir", str(self.mem), "--state-dir", str(self.state),
                  "--date", "2026-09-07"]

        rc, out, err = self.run_cli([
            "warm-directory", *common, "--budget", "1000", "--catalog", str(self.catalog)
        ])
        self.assertEqual((rc, err), (0, ""))
        directory = json.loads(out)
        self.assertEqual(directory["tier"], "T1")
        self.assertEqual(directory["selected"][0]["item_ids"], [self.warm["id"]])
        self.assertNotIn("warm database note", "\n".join(directory["lines"]))

        rc, out, err = self.run_cli([
            "residency-plan", *common, "--budget", "1000",
            "--telemetry", str(self.trace), "--catalog", str(self.catalog),
            "--min-tasks", "1", "--horizon-tasks", "5"
        ])
        self.assertEqual((rc, err), (0, ""))
        plan = json.loads(out)
        self.assertIn(self.warm["id"], plan["admit"])
        self.assertFalse(plan["changes_applied"])

        rc, out, err = self.run_cli([
            "prefetch-plan", *common, "--telemetry", str(self.trace),
            "--catalog", str(self.catalog), "--active", self.hot["id"],
            "--min-support", "2", "--min-confidence", "0.5"
        ])
        self.assertEqual((rc, err), (0, ""))
        prefetch = json.loads(out)
        self.assertEqual(prefetch["candidates"][0]["item_id"], self.warm["id"])
        self.assertFalse(prefetch["prefetch_events_used_for_training"])

        rc, out, err = self.run_cli(["residency-telemetry", str(self.trace)])
        self.assertEqual((rc, err), (0, ""))
        report = json.loads(out)
        self.assertEqual(report["demand_count"], 4)

        rc, out, err = self.run_cli([
            "residency-budget", str(self.trace), "--current-budget", "600",
            "--context-pressure", "0.3", "--min-budget", "300",
            "--max-budget", "1200", "--step", "100", "--min-demands", "1"
        ])
        self.assertEqual((rc, err), (0, ""))
        budget = json.loads(out)
        self.assertEqual(budget["direction"], "grow")
        self.assertFalse(budget["changes_applied"])

        self.assertEqual(self.identity(), before)

    def test_bad_catalog_is_structured_error_without_write(self):
        before = self.identity()
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"items": {self.warm["id"]: {"tier": "T0"}}}), encoding="utf-8")
        rc, out, err = self.run_cli([
            "warm-directory", "--mem-dir", str(self.mem), "--state-dir", str(self.state),
            "--date", "2026-09-07", "--catalog", str(bad)
        ])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        payload = json.loads(err)
        self.assertEqual(payload["status"], "ERROR")
        self.assertIn("unsupported field tier", payload["error"])
        self.assertEqual(self.identity(), before)


if __name__ == "__main__":
    unittest.main()
