import unittest

from thm.rerank import RerankConfig, lexical_features, pack_rows, rerank_rows, source_block
from thm.retrieval import TokenCounter


class RerankTests(unittest.TestCase):
    def rows(self):
        return [
            {"id": "a", "text": "The garden contains trees.", "speaker": "Alice", "timestamp": "", "hash": "a", "source": "s:a"},
            {"id": "b", "text": "The PostgreSQL service listens on port 5432.", "speaker": "Bob", "timestamp": "2026-09-07", "hash": "b", "source": "s:b"},
            {"id": "c", "text": "Database maintenance happens weekly.", "speaker": "Bob", "timestamp": "", "hash": "c", "source": "s:c"},
        ]

    def test_reranker_uses_only_query_and_candidate_rows(self):
        out = rerank_rows("PostgreSQL port 5432", self.rows(), RerankConfig(coverage_weight=1.0))
        self.assertEqual(out[0]["id"], "b")
        self.assertNotIn("answer", out[0])
        self.assertNotIn("evidence", out[0])

    def test_zero_bonus_preserves_base_order(self):
        cfg = RerankConfig(coverage_weight=0, all_focus_bonus=0, exact_bonus=0)
        self.assertEqual([row["id"] for row in rerank_rows("PostgreSQL", self.rows(), cfg)], ["a", "b", "c"])

    def test_metadata_factor_is_explicit(self):
        row = {"id": "a", "text": "The service is healthy.", "speaker": "Caroline", "timestamp": "2026-09-07"}
        features = lexical_features("Caroline service", row)
        self.assertGreater(features["meta_coverage"], 0)
        low = rerank_rows("Caroline service", [row], RerankConfig(metadata_match_factor=0))[0]
        high = rerank_rows("Caroline service", [row], RerankConfig(metadata_match_factor=1))[0]
        self.assertGreater(high["_thm_rerank_score"], low["_thm_rerank_score"])

    def test_numeric_identifier_has_specificity(self):
        exact = lexical_features("port 5432", self.rows()[1])
        generic = lexical_features("port 9999", self.rows()[1])
        self.assertGreater(exact["body_coverage"], generic["body_coverage"])

    def test_compact_header_preserves_fields_and_is_shorter(self):
        row = self.rows()[1]
        compact = source_block(row, compact=True)
        baseline = source_block(row, compact=False)
        self.assertIn('"id":"b"', compact)
        self.assertIn('"speaker":"Bob"', compact)
        self.assertIn('"date":"2026-09-07"', compact)
        self.assertLess(len(compact.encode()), len(baseline.encode()))

    def test_exact_budget_and_whole_sources(self):
        counter = TokenCounter()
        packed = pack_rows(self.rows(), budget=170, counter=counter, compact_headers=True)
        self.assertLessEqual(packed["budget_used"], 170)
        self.assertEqual(packed["budget_used"], len(packed["context"].encode()))
        self.assertTrue(all(row["complete"] for row in packed["selected"]))
        self.assertTrue(all(row["text"] in packed["context"] for row in packed["selected"]))

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            rerank_rows("q", self.rows(), RerankConfig(coverage_weight=-1))
        with self.assertRaises(ValueError):
            rerank_rows("q", self.rows(), RerankConfig(metadata_match_factor=2))


if __name__ == "__main__":
    unittest.main()
