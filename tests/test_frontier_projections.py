from datetime import date
import tempfile
from pathlib import Path
import unittest
from research.recall.frontier_temporal import parse, source_date, reorder
from research.recall.frontier_entity import reorder as entities
from research.recall.frontier_segments import spans, pack
from thm.retrieval import SearchIndex, TokenCounter


class ProjectionTests(unittest.TestCase):
    def test_temporal_explicit_and_fail_soft(self):
        for query in ['2026-05', '2026年5月', 'May 2026']:
            self.assertEqual((parse(query).year, parse(query).month), (2026, 5))
        self.assertEqual(parse('五月').month, 5)
        self.assertEqual(parse('May 3').day, 3)
        self.assertTrue(parse('yesterday').relative_unresolved)
        self.assertEqual(parse('昨天', date(2024, 3, 1)).day, 29)
        self.assertIsNone(parse('2025-02-29').month)
        self.assertIsNone(parse('before 2025').year)
        self.assertEqual(source_date('1:56 pm on 8 May, 2023'), date(2023, 5, 8))
        self.assertIsNone(source_date('invalid'))

    def test_no_signal_identity_and_unknown_date(self):
        rows = [{'rowid': 1, 'timestamp': '', 'speaker': 'A', 'text': 'text'}]
        self.assertIs(reorder(rows, 'storage settings'), rows)
        self.assertIs(reorder(rows, 'May 2025'), rows)
        self.assertIs(entities(rows, 'storage settings'), rows)

    def test_exact_speaker_collision_and_identifiers(self):
        rows = [{'rowid': i, 'timestamp': '', 'speaker': s, 'text': text}
                for i, s, text in [(1, 'Annette', 'project'), (2, 'Ann', 'fix BUG-42')]]
        self.assertEqual(entities(rows, 'Ann BUG-42')[0]['rowid'], 2)
        self.assertIs(entities(rows, 'anne bug-42'), rows)

    def test_segments_exact_bounded_and_code(self):
        text = ('你好世界。' * 20 + '\n\n') * 8
        pieces = spans(text)
        self.assertLessEqual(len(pieces), 4)
        self.assertTrue(all(b - a >= 80 for a, b in pieces))
        self.assertEqual(spans('```\n' + text + '\n```'), [])
        self.assertEqual(spans('tiny'), [])

    def test_fragment_has_no_complete_gold_credit_and_budget(self):
        with tempfile.TemporaryDirectory() as root:
            ix = SearchIndex(Path(root)/'index', TokenCounter())
            text = 'Storage ' + 'x' * 120 + '.\n\n' + 'y' * 1000
            row = dict(id='a', rowid=1, speaker='A', timestamp='', text=text, hash='h', source='s')
            context, selected, used = pack(ix, [row], 350, 'Storage')
            self.assertLessEqual(used, 350)
            self.assertEqual(len(selected), 1)
            self.assertFalse(selected[0]['complete'])
            a, b = selected[0]['span']
            self.assertEqual(text[a:b], selected[0]['text'])
            ix.close()


if __name__ == '__main__': unittest.main()
