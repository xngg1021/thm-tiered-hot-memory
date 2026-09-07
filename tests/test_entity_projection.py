from pathlib import Path
import tempfile
import unittest
from thm.entities import reorder
from thm.retrieval import Document, SearchIndex


class EntityProjectionTests(unittest.TestCase):
    def test_default_off_and_projection_candidate_membership(self):
        with tempfile.TemporaryDirectory() as root:
            index = SearchIndex(Path(root)/'index')
            index.replace_scope('a', [Document(str(i), 'a', 'session', i,
                'Storage details', 'Ann' if i % 2 else 'Bob') for i in range(8)])
            index.replace_scope('b', [Document('secret', 'b', 's', 0, 'Storage details', 'Ann')])
            base = index.search('a', 'Ann Storage')
            off = index.search('a', 'Ann Storage', entity_projection=False)
            on = index.search('a', 'Ann Storage', entity_projection=True)
            self.assertEqual(base['context'], off['context'])
            self.assertEqual(set(base['ranked_ids']), set(on['ranked_ids']))
            self.assertNotIn('secret', on['ranked_ids'])
            for invalid in [1, 'true', None]:
                with self.assertRaises(ValueError): index.search('a', 'Storage', entity_projection=invalid)
            with self.assertRaises(ValueError): index.search('a', 'Storage', mode='literal', entity_projection=True)
            index.close()

    def test_no_signal_preserves_object_and_labels_not_inputs(self):
        rows = [{'rowid': i, 'speaker': speaker, 'text': text}
                for i, speaker, text in [(1, 'Bob', 'v1.4.0'), (2, 'Ann', 'v1.5.0')]]
        self.assertIs(reorder(rows, 'plain request'), rows)
        self.assertEqual(reorder(rows, 'v1.5.0')[0]['rowid'], 2)
        with_labels = [dict(r, gold=i == 0, answer='unused', category=2) for i,r in enumerate(rows)]
        self.assertEqual([r['rowid'] for r in reorder(rows, 'Ann')],
                         [r['rowid'] for r in reorder(with_labels, 'Ann')])

    def test_generic_literals_and_multilingual_exact_paths(self):
        rows = [{'rowid': 1, 'speaker': '李四', 'text': 'Python project'},
                {'rowid': 2, 'speaker': '张三', 'text': '资料/Version.md v1.5.0'}]
        self.assertIs(reorder(rows, '`Python`'), rows)
        self.assertIs(reorder(rows, '`project`'), rows)
        self.assertEqual(reorder(rows, '张三 version')[0]['rowid'], 2)
        self.assertEqual(reorder(rows, '`资料/Version.md`')[0]['rowid'], 2)
        self.assertIs(reorder(rows, '`资料/version.md`'), rows)


if __name__ == '__main__': unittest.main()
