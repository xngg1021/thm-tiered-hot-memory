"""Synthetic mutations of the public documentation checker."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('document_check',ROOT/'scripts/check_docs.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
PUBLIC_FILES=('README.md','docs/01-研究综述.md','docs/02-架构设计.md','docs/03-validation-contract.md',
 'docs/04-related-work.md','docs/05-hermes-upstream.md','docs/related-work-sources.json',
 'reports/2026-09-06-学术工具复审.md','reports/2026-09-06-文档勘误验证.json','scripts/check_docs.py','scripts/thm_numeric_audit.py','scripts/thm.py')
class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for name in PUBLIC_FILES:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    def tearDown(self):self.temp.cleanup()
    def test_baseline(self):self.assertEqual(checker.check(self.root)['status'],'PASS')
    def test_missing_history_is_structured_failure(self):
        (self.root/checker.REPORT).unlink();out=checker.check(self.root);self.assertEqual(out['status'],'FAIL');self.assertFalse(out['historical_report_preserved'])
    def test_invalid_history_encoding(self):
        (self.root/checker.REPORT).write_bytes(b'\xff\n');self.assertEqual(checker.check(self.root)['status'],'FAIL')
    def test_missing_architecture_is_structured_failure(self):
        (self.root/'docs/02-架构设计.md').unlink();self.assertEqual(checker.check(self.root)['status'],'FAIL')
    def test_historical_edit_rejected(self):
        p=self.root/checker.REPORT;p.write_text(p.read_text().replace(checker.START,checker.START+'Synthetic mutation\n'));self.assertFalse(checker.check(self.root)['historical_report_preserved'])
    def test_bad_relative_link_rejected(self):
        p=self.root/'README.md';p.write_text(p.read_text()+'\n[Missing](missing.md)\n');self.assertEqual(checker.check(self.root)['status'],'FAIL')
    def test_missing_related_work_is_structured_failure(self):
        (self.root/'docs/04-related-work.md').unlink()
        out=checker.check(self.root)
        self.assertEqual(out['status'],'FAIL')
        self.assertIn('Expected the seven scoped Markdown documents',out['errors'])
    def test_related_work_links_are_checked(self):
        p=self.root/'docs/04-related-work.md'
        p.write_text(p.read_text()+'\n[Missing source](missing-source.json)\n')
        out=checker.check(self.root)
        self.assertEqual(out['status'],'FAIL')
        self.assertTrue(any('missing-source.json' in error for error in out['errors']))
if __name__=='__main__':unittest.main(verbosity=2)
