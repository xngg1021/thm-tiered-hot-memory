import tempfile
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from thm import __main__ as cli
from thm.retrieval import SearchIndex, Document


class ExtensionCLITests(unittest.TestCase):
    def test_index_delegates_original_options(self):
        target = types.SimpleNamespace(main=lambda args: args)
        with patch.object(cli, 'legacy_engine', return_value=target):
            self.assertEqual(cli.main(['index', '--mem-dir', 'test-profile', 'audit']),
                             ['--mem-dir', 'test-profile', 'audit'])

    def test_kind_sync_keeps_other_sources_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as root:
            index = SearchIndex(Path(root) / 'recall.sqlite')
            try:
                index.replace_scope('p', [Document('f','p','s',0,'note',source='file:note')])
                update = [Document('h','p','s2',0,'history',source='hermes-message:1')]
                index.sync_kind('p', update, 'hermes-message:')
                self.assertEqual(len(index.rows('p')), 2)
                self.assertFalse(index.sync_kind('p', update, 'hermes-message:')['changed'])
                self.assertFalse(index.db.in_transaction)
                index.sync_kind('p', [], 'file:')
                self.assertEqual([r['id'] for r in index.rows('p')], ['h'])
            finally:
                index.close()
