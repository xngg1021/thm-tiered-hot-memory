import unittest
from research.recall.frontier_report import paired


class PairedReportTests(unittest.TestCase):
    def row(self, index, hits):
        return dict(scope='a', question_index=index, hits=hits, budget=600,
                    category=4, fully_resolved=True, evidence_count=1, split='held_out')

    def test_cluster_bootstrap_is_deterministic_and_paired(self):
        a = [self.row(0, 0), self.row(1, 1)]
        b = [self.row(0, 1), self.row(1, 0)]
        out = paired(a, b)
        self.assertEqual((out['wins'], out['losses'], out['ties']), (1, 1, 0))
        self.assertEqual(out['cluster_bootstrap_95ci_pp'], [0, 0])
        self.assertEqual(out, paired(a, b))

    def test_duplicate_and_unmatched_questions_fail(self):
        row = self.row(0, 1)
        with self.assertRaises(ValueError): paired([row, row], [row])
        with self.assertRaises(ValueError): paired([row], [self.row(1, 1)])

    def test_empty_split_is_not_zero_uncertainty(self):
        out = paired([], [])
        self.assertEqual(out['denominator'], 0)
        self.assertEqual(out['cluster_bootstrap_95ci_pp'], [None, None])
        self.assertIsNone(out['delta_pp'])
