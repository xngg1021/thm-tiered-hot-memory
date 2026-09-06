"""Isolated document checker tests; the separate CLI checks the real repository."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('document_check', Path(__file__).resolve().parents[1]/'scripts/check_docs.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        for name in checker.REQUIRED:
            self.write(name, '# Synthetic document\n')
        history = b'Synthetic preserved historical text.\n'
        expected = hashlib.sha1(b'blob '+str(len(history)).encode()+b'\0'+history).hexdigest()
        self.patch = patch.object(checker, 'ORIGINAL_BLOB', expected)
        self.patch.start()
        self.write(checker.REPORT, checker.START+history.decode()+checker.END+'\n')
        self.write('docs/related-work-sources.json', json.dumps({'systems': [{'id': 'one', 'sources': [{'url':'https://example.org/source'}]}]})+'\n')
        self.write('scripts/example.py', 'x = 1\n')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def write(self, name, text):
        p=self.root/name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8', newline='\n')
        return p

    def test_baseline(self):
        self.assertEqual(checker.check(self.root)['status'], 'PASS')

    def test_missing_history_is_structured_failure(self):
        (self.root/checker.REPORT).unlink()
        out=checker.check(self.root)
        self.assertEqual(out['status'],'FAIL')
        self.assertFalse(out['historical_report_preserved'])

    def test_invalid_history_encoding(self):
        (self.root/checker.REPORT).write_bytes(b'\xff\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_missing_architecture_is_structured_failure(self):
        (self.root/'docs/02-架构设计.md').unlink()
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_historical_edit_rejected(self):
        p=self.root/checker.REPORT
        p.write_text(p.read_text(encoding='utf-8').replace('Synthetic','Mutated'), encoding='utf-8')
        self.assertFalse(checker.check(self.root)['historical_report_preserved'])

    def test_bad_relative_link_rejected(self):
        self.write('README.md','[Missing](missing.md)\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_missing_related_work_is_structured_failure(self):
        (self.root/'docs/04-related-work.md').unlink()
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_related_work_links_are_checked(self):
        self.write('docs/04-related-work.md','[Missing source](missing-source.json)\n')
        self.assertTrue(any('missing-source.json' in error for error in checker.check(self.root)['errors']))

    def test_corrupt_source_manifest_rejected(self):
        self.write('docs/related-work-sources.json','{\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_duplicate_source_ids_rejected(self):
        self.write('docs/related-work-sources.json','{"systems":[{"id":"x"},{"id":"x"}]}\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_invalid_python_encoding_structured(self):
        (self.root/'scripts/example.py').write_bytes(b'\xff\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_read_error_structured(self):
        original=Path.read_bytes
        failures=[]
        def fail_one(p):
            if p.resolve() == (self.root/'README.md').resolve():
                failures.append(p)
                raise PermissionError('synthetic')
            return original(p)
        with patch.object(Path, 'read_bytes', fail_one):
            self.assertEqual(checker.check(self.root)['status'],'FAIL')
        self.assertEqual(len(failures), 1, 'the injected read failure must actually execute')

    def test_new_document_allowed_and_checked(self):
        self.write('docs/extra.md','# Extra\n[Read](../README.md)\n')
        self.assertEqual(checker.check(self.root)['status'],'PASS')
        self.write('docs/extra.md','[Missing](nowhere)\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_outside_link_rejected(self):
        self.write('README.md','[Outside](../outside.md)\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_json_fence_rejected(self):
        self.write('README.md','```json\n{\n```\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')

    def test_crlf_rejected(self):
        (self.root/'README.md').write_bytes(b'# Test\r\n')
        self.assertEqual(checker.check(self.root)['status'],'FAIL')


if __name__=='__main__':
    unittest.main(verbosity=2)
