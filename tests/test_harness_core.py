from pathlib import Path
import tempfile
import unittest

from thm.harness import HarnessConfig, THMHarnessAdapter
from thm.retrieval import Document, SearchIndex


class HarnessCoreTests(unittest.TestCase):
    def make_db(self, root):
        path = Path(root) / "recall.sqlite3"
        index = SearchIndex(path)
        try:
            index.replace_scope("demo", [
                Document(
                    "port", "demo", "s1", 0,
                    "The integration database port is 5439.",
                    speaker="user", source="file:test", tier="T2",
                )
            ])
        finally:
            index.close()
        return path

    def test_harness_adapter_returns_budgeted_source_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.make_db(temp)
            adapter = THMHarnessAdapter(HarnessConfig(db=str(path), scope="demo", budget=600))
            try:
                out = adapter.recall("Which database port?")
            finally:
                adapter.close()
            self.assertIn("5439", out["context"])
            self.assertEqual(["port"], [row["id"] for row in out["sources"]])
            self.assertLessEqual(out["budget_used"], 600)
            self.assertEqual("unverified", out["usefulness"])
            self.assertFalse(out["answer_generated"])

    def test_dense_requires_explicit_model_identity(self):
        with self.assertRaises(ValueError):
            HarnessConfig(db="x", scope="demo", mode="dense").validate()

    def test_missing_database_fails_without_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.sqlite3"
            adapter = THMHarnessAdapter(HarnessConfig(db=str(path), scope="demo"))
            with self.assertRaises(ValueError):
                adapter.recall("test")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
