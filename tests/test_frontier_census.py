import unittest

from research.recall.frontier_census import census, run
from research.recall.benchmark import CATEGORY
from thm.retrieval import TokenCounter


class FrontierCensusTests(unittest.TestCase):
    def test_categories_and_denominator(self):
        self.assertEqual(CATEGORY[1], 'multi_hop')
        self.assertEqual(CATEGORY[4], 'single_hop')
        row = dict(category=1, fully_resolved=True, evidence_count=1,
                   hits=0, failure_bucket='candidate_miss', scope='a', question_index=0)
        result = census([row, dict(row, category=5), dict(row, fully_resolved=False)])
        self.assertEqual(result['all']['candidate_miss']['count'], 1)
        self.assertEqual(result['all']['candidate_miss']['denominator'], 1)

    def test_observer_and_oracle_do_not_change_search(self):
        data = [{'sample_id': 'a', 'conversation': {
            'session_1': [{'dia_id': 'D1:1', 'text': 'unique ' * 1000, 'speaker': 'A'}]},
            'qa': [{'category': 4, 'question': 'unique', 'evidence': ['D1:1']}]}]
        result = run(data, TokenCounter())
        self.assertEqual(result['generation_calls'], 0)
        for row in result['rows']:
            self.assertEqual(row['candidate_hits'], 1)
            self.assertEqual(row['hits'], 0)
            self.assertFalse(row['oracle_any_gold_feasible'])
            self.assertEqual(row['failure_bucket'], 'budget_impossible')
            self.assertLessEqual(row['budget_used'], 600)


if __name__ == '__main__':
    unittest.main()
