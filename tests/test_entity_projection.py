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

    def test_compound_identifier_boundaries(self):
        from thm.entities import present
        for value, text in [('Ann','Ann-Marie'), ('Ann','X/Ann'),
                            ('src/model.py','src/model.py.old'),
                            ('v1.5.0','v1.5.0.1'),
                            ('https://a.test','https://a.test/path'),
                            ('src/model.py','src/model.py?revision=2')]:
            self.assertFalse(present(value,text), (value,text))
        self.assertTrue(present('Ann', "Ann's notes"))
        self.assertTrue(present('Ann', 'Ann.'))
        self.assertTrue(present('src/model.py', 'see src/model.py.'))

    def test_identifier_flood_fails_soft_without_compilation(self):
        from unittest.mock import patch
        import thm.entities as module
        query = ' '.join(f'`id{i}`' for i in range(1200))
        self.assertLess(len(query),16000)
        rows = [{'rowid': i, 'speaker': '', 'text': 'unrelated'} for i in range(1000)]
        with patch.object(module.re, 'compile', wraps=module.re.compile) as compile_pattern:
            self.assertIs(reorder(rows,query), rows)
            self.assertEqual(compile_pattern.call_count,0)
        self.assertIs(reorder(rows, '`'+'x'*257+'`'), rows)

    def test_patterns_compile_once_and_oversized_body_fails_soft(self):
        from unittest.mock import patch
        import thm.entities as module
        rows = [{'rowid': i, 'speaker': 'Ann', 'text': 'unrelated'} for i in range(1000)]
        with patch.object(module.re, 'compile', wraps=module.re.compile) as compile_pattern:
            reorder(rows,' '.join(f'`id{i}`' for i in range(16)))
            self.assertLessEqual(compile_pattern.call_count,2)
        long_rows = [{'rowid': 1, 'speaker': '', 'text': 'x'*9000+' BUG-42'}]
        self.assertIs(reorder(long_rows,'BUG-42'),long_rows)

    def test_longest_known_full_speaker_wins_over_prefix(self):
        rows = [{'rowid': 1, 'speaker': 'Ann', 'text': 'text'},
                {'rowid': 2, 'speaker': 'Ann Marie', 'text': 'text'}]
        self.assertEqual(reorder(rows, 'Ann Marie visited')[0]['rowid'], 2)

    def test_extraction_never_admits_truncated_identifiers(self):
        rows = [{'rowid': 1, 'speaker': '', 'text': 'v1.5.0 BUG-42 https://a.test'},
                {'rowid': 2, 'speaker': '', 'text': 'v1.5.0.1'}]
        self.assertEqual(reorder(rows,'v1.5.0.1')[0]['rowid'],2)
        for query in ['v1.5.0-rc1', 'v1.5.0+build1', 'BUG-42-extra',
                      'src/BUG-42', 'xhttps://a.test']:
            self.assertIs(reorder(rows,query),rows,query)

    def test_url_prose_wrappers_and_balanced_path_parentheses(self):
        rows = [{'rowid': 1, 'speaker': '', 'text': 'unrelated'},
                {'rowid': 2, 'speaker': '', 'text': 'https://a.test'}]
        for query in ['See https://a.test.', '(https://a.test)',
                      '[https://a.test]', '"https://a.test"',
                      'See (https://a.test).', 'See https://a.test!']:
            self.assertEqual(reorder(rows,query)[0]['rowid'],2,query)
        path_rows = [rows[0], dict(rows[1],text='https://a.test/page_(one)')]
        self.assertEqual(reorder(path_rows,'See (https://a.test/page_(one)).')[0]['rowid'],2)
        self.assertIs(reorder(rows,'https://a.test/path.'),rows)
        self.assertIs(reorder(rows,'https://a.test?revision=2.'),rows)
        self.assertIs(reorder(rows,'`https://a.test.`'),rows)

    def test_url_unicode_punctuation_and_wrappers(self):
        rows = [{'rowid': 1, 'speaker': '', 'text': 'unrelated'},
                {'rowid': 2, 'speaker': '', 'text': 'https://a.test'}]
        for query in ['See https://a.test。', '“https://a.test”',
                      '（https://a.test）', '《https://a.test》',
                      '「https://a.test」', 'See https://a.test！',
                      'See https://a.test…', 'See https://a.test،']:
            self.assertEqual(reorder(rows,query)[0]['rowid'],2,query)
        path_rows = [rows[0], dict(rows[1],text='https://a.test/页（甲）')]
        self.assertEqual(reorder(path_rows,'（https://a.test/页（甲））。')[0]['rowid'],2)
        self.assertIs(reorder(rows,'`https://a.test。`'),rows)

    def test_known_cjk_speakers_in_unspaced_prose(self):
        for name, query in [('张三', '请问张三讨论了什么？'),
                            ('田中', '田中さんは何を話しましたか？'),
                            ('민수', '민수는무엇을말했나요?')]:
            rows = [{'rowid': 1, 'speaker': 'Other', 'text': 'text'},
                    {'rowid': 2, 'speaker': name, 'text': 'text'}]
            self.assertEqual(reorder(rows,query)[0]['rowid'],2,query)
            self.assertIs(reorder(rows,'prefix/'+name),rows)
            self.assertIs(reorder(rows,name+'-suffix'),rows)
        rows = [{'rowid': 1, 'speaker': '张三', 'text': 'text'},
                {'rowid': 2, 'speaker': '张三丰', 'text': 'text'}]
        self.assertEqual(reorder(rows,'请问张三丰说了什么？')[0]['rowid'],2)
        from thm.entities import present
        self.assertFalse(present('资料/版本.md','资料/版本.md副本'))

    def test_rejected_longer_speaker_never_falls_back_to_prefix(self):
        for short, long in [('张三', '张三丰'), ('Ann', 'Ann Marie')]:
            rows = [{'rowid': 1, 'speaker': 'Other', 'text': 'text'},
                    {'rowid': 2, 'speaker': short, 'text': 'text'},
                    {'rowid': 3, 'speaker': long, 'text': 'text'}]
            self.assertEqual(reorder(rows,long)[0]['rowid'],3)
            self.assertEqual(reorder(rows,short)[0]['rowid'],2)
            for suffix in ['-suffix', '/suffix', '.suffix']:
                self.assertIs(reorder(rows,long+suffix),rows,long+suffix)


if __name__ == '__main__': unittest.main()
