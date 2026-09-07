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

class IsolationTests(unittest.TestCase):
    def test_association_scope_caps_and_no_recursive_expansion(self):
        from research.recall.frontier_association import expand
        from thm.retrieval import Document
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'index'
            ix = SearchIndex(path)
            ix.replace_scope('a', [Document(str(i), 'a', 'session', i, 'text') for i in range(20)])
            ix.replace_scope('b', [Document(str(i), 'b', 'session', i, 'secret') for i in range(20)])
            rows = ix.rows('a')
            result = expand(ix, 'a', [rows[5]])
            self.assertEqual({r['ord'] for r in result}, {4,5,6})
            self.assertEqual({r['scope'] for r in result}, {'a'})
            self.assertEqual(expand(ix, 'a', []), [])
            self.assertEqual(ix.rows('a'), rows)
            ix.close()

    def test_readonly_seeded_budgets_and_native_bytes(self):
        import random
        from thm.retrieval import Document
        from research.recall.frontier_ablation import EntityIndex, SegmentIndex, AssociationIndex
        rng = random.Random(31)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            native = root/'MEMORY.md';native.write_bytes(b'authoritative\n')
            path = root/'index'
            ix = SearchIndex(path)
            ix.replace_scope('a', [Document(str(i), 'a', 'session', i,
                 'Storage details ' + 'x' * rng.randrange(80, 700), 'Ann' if i % 2 else 'Bob') for i in range(15)])
            ix.close()
            original = path.read_bytes()
            for cls in [EntityIndex, SegmentIndex, AssociationIndex]:
                ix = cls(path, readonly=True)
                for budget in [0,128,256,600,1200]:
                    out = ix.search('a', 'Ann Storage', budget=budget)
                    self.assertLessEqual(out['budget_used'], budget)
                    self.assertEqual(len(out['ranked_ids']),len(set(out['ranked_ids'])))
                    again = ix.search('a', 'Ann Storage', budget=budget)
                    self.assertEqual(out['context'],again['context'])
                ix.close()
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(native.read_bytes(),b'authoritative\n')
