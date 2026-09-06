import datetime as dt
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts.thm import Engine


class HermesWarmDirectoryTests(unittest.TestCase):
    def provider_module(self):
        memory_provider = types.ModuleType("agent.memory_provider")
        memory_provider.MemoryProvider = object
        memory_provider.RecallStatus = lambda **kwargs: kwargs
        sys.modules.pop("thm.hermes_plugin", None)
        sys.modules.pop("thm.hermes_v14_plugin", None)
        patcher = patch.dict(sys.modules, {"agent.memory_provider": memory_provider})
        patcher.start()
        self.addCleanup(patcher.stop)
        module = importlib.import_module("thm.hermes_v14_plugin")
        self.addCleanup(sys.modules.pop, "thm.hermes_v14_plugin", None)
        self.addCleanup(sys.modules.pop, "thm.hermes_plugin", None)
        return module

    def make_profile(self, root):
        mem = Path(root) / "memories"
        state = mem / ".thm"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text(
            "hot setting\n§\nwarm database secret body", encoding="utf-8"
        )
        (mem / "USER.md").write_text("", encoding="utf-8")
        engine = Engine(mem, state, clock=lambda: dt.date(2026, 9, 6))
        engine.seed()
        rows = engine.load().data["entries"]
        warm = next(r for r in rows if r["key"].startswith("warm database"))

        def move(data):
            for row in data["entries"]:
                if row["id"] == warm["id"]:
                    row["tier"] = "T1"
            return None

        engine.update(move)
        catalog = state / "residency-catalog.json"
        catalog.write_text(
            json.dumps({"items": {warm["id"]: {"locator": "warm/database.md"}}}),
            encoding="utf-8",
        )
        return mem, state, warm, catalog

    def test_opt_in_directory_is_locator_only_and_session_frozen(self):
        provider_module = self.provider_module()
        with tempfile.TemporaryDirectory() as root:
            mem, state, warm, catalog = self.make_profile(root)
            before = {
                "index": (state / "index.json").read_bytes(),
                "memory": (mem / "MEMORY.md").read_bytes(),
                "user": (mem / "USER.md").read_bytes(),
            }
            provider = provider_module.THMProvider(
                {"scope": "scope", "warm_directory_budget": 400}
            )
            provider.initialize("s1", hermes_home=root)
            first = provider.system_prompt_block()
            self.assertIn("warm/database.md", first)
            self.assertIn("database", first)
            self.assertNotIn("warm database secret body", first)
            self.assertNotIn("warm database", first)
            self.assertLessEqual(provider.counter(first), 400)

            catalog.write_text(
                json.dumps({"items": {warm["id"]: {"locator": "warm/updated.md"}}}),
                encoding="utf-8",
            )
            provider.on_memory_write("update", "memory", "ignored")
            self.assertEqual(provider.system_prompt_block(), first)

            provider.on_session_switch("s2")
            second = provider.system_prompt_block()
            self.assertIn("warm/updated.md", second)
            self.assertNotEqual(second, first)
            status = json.loads(provider.handle_tool_call("thm_recall_status", {}))
            self.assertTrue(status["warm_directory"]["enabled"])
            self.assertEqual(status["warm_directory"]["snapshot_refresh"], "session_boundary_only")
            provider.shutdown()

            after = {
                "index": (state / "index.json").read_bytes(),
                "memory": (mem / "MEMORY.md").read_bytes(),
                "user": (mem / "USER.md").read_bytes(),
            }
            self.assertEqual(after, before)

    def test_directory_disabled_by_default(self):
        provider_module = self.provider_module()
        with tempfile.TemporaryDirectory() as root:
            self.make_profile(root)
            provider = provider_module.THMProvider({"scope": "scope"})
            provider.initialize("s", hermes_home=root)
            self.assertEqual(provider.system_prompt_block(), "")
            provider.shutdown()

    def test_stale_catalog_identity_fails_opt_in_initialization(self):
        provider_module = self.provider_module()
        with tempfile.TemporaryDirectory() as root:
            _mem, state, _warm, catalog = self.make_profile(root)
            catalog.write_text(
                json.dumps({"items": {"ghost": {"locator": "warm/ghost.md"}}}),
                encoding="utf-8",
            )
            provider = provider_module.THMProvider(
                {"scope": "scope", "warm_directory_budget": 400}
            )
            with self.assertRaisesRegex(ValueError, "unknown item id ghost"):
                provider.initialize("s", hermes_home=root)

    def test_warm_budget_validation(self):
        provider_module = self.provider_module()
        provider = provider_module.THMProvider(
            {"scope": "scope", "warm_directory_budget": 99999}
        )
        self.assertFalse(provider.is_available())
        self.assertIn("warm_directory_budget", provider.unavailable_reason())


if __name__ == "__main__":
    unittest.main()
