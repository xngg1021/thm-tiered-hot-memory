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

    def test_documented_research_commands_require_opt_in(self):
        self.write('docs/campaign.md', '```powershell\npython research/recall/lme_retrieval.py --dataset example.json\n```\n')
        self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']))
        self.write('docs/campaign.md', '```powershell\npython research/recall/lme_retrieval.py --full-research --dataset example.json\n```\n')
        self.assertEqual(checker.check(self.root)['status'], 'PASS')

    def test_research_opt_in_ignores_comments_and_respects_quotes(self):
        command = 'python research/recall/benchmark.py --dataset '
        for suffix in ('input.json # add --full-research', '"path # hash.json" # --full-research', '"text --full-research"'):
            self.write('docs/campaign.md', '```shell\n' + command + suffix + '\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), suffix)
        for suffix in ('"path # hash.json" --full-research # optional note', "'path # hash.json' '--full-research'", '"C:\\data\\input.json" --full-research'):
            self.write('docs/campaign.md', '```shell\n' + command + suffix + '\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', suffix)

    def test_research_commands_preserve_embedded_and_escaped_hashes(self):
        for path in ('path#hash.json', r'path\#hash.json', r'\#hash.json', 'path`#hash.json'):
            fence = 'powershell' if '`' in path else 'bash'
            command = 'python research/recall/benchmark.py --dataset ' + path
            self.write('docs/campaign.md', '```' + fence + '\n' + command + ' --full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', path)
            self.write('docs/campaign.md', '```' + fence + '\n' + command + ' # --full-research\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), path)

    def test_research_commands_keep_substitution_suffix_in_same_word(self):
        for path in ('$(printf path)#hash.json', '$(printf $(printf path))#hash.json',
                     '$(printf "path")#hash.json', 'prefix$(printf path)#hash.json'):
            command = 'python research/recall/benchmark.py --dataset ' + path
            self.write('docs/campaign.md', '```shell\n' + command + ' --full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', path)
            self.write('docs/campaign.md', '```shell\n' + command + ' # --full-research\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), path)

    def test_research_opt_in_on_continued_command_lines(self):
        for shell, marker in (('bash', '\\'), ('powershell', '`')):
            command = 'python research/recall/benchmark.py ' + marker + '\n  --dataset input.json ' + marker + '\n  '
            self.write('docs/campaign.md', '```' + shell + '\n' + command + '--full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', marker)
            self.write('docs/campaign.md', '```' + shell + '\n' + command + '# --full-research\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), marker)
        self.write('docs/campaign.md', '```shell\npython research/recall/benchmark.py --dataset input.json # \\\n --full-research\n```\n')
        self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']))

    def test_research_command_cannot_borrow_opt_in_from_later_command(self):
        for separator in (';', '&&', '||', '|', '&'):
            command = 'python research/recall/benchmark.py --dataset input.json'
            self.write('docs/campaign.md', '```bash\n' + command + separator + ' echo --full-research\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), separator)
            self.write('docs/campaign.md', '```bash\n' + command + ' --full-research' + separator + ' echo done\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', separator)
        self.write('docs/campaign.md', '```bash\npython research/recall/benchmark.py --dataset "path;with|symbols.json" --full-research\n```\n')
        self.assertEqual(checker.check(self.root)['status'], 'PASS')

    def test_research_continuation_must_match_declared_shell(self):
        for shell, marker in (('bash', '`'), ('powershell', '\\')):
            command = 'python research/recall/benchmark.py --dataset input.json ' + marker + '\n  --full-research'
            self.write('docs/campaign.md', '```' + shell + '\n' + command + '\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), shell)

    def test_research_process_substitution_keeps_inner_separators(self):
        for path in ('<(producer | filter)', '>(producer; filter)', '<(producer <(nested | filter) | filter)'):
            command = 'python research/recall/benchmark.py --dataset ' + path
            self.write('docs/campaign.md', '```bash\n' + command + ' --full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', path)
            self.write('docs/campaign.md', '```bash\n' + command + '; echo --full-research\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), path)
        for path in ('<(producer --full-research | filter)', '$(producer --full-research | filter)'):
            self.write('docs/campaign.md', '```bash\npython research/recall/benchmark.py --dataset ' + path + '\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), path)

    def test_research_prompt_selects_powershell_without_shell_fence(self):
        for opening, closing in (('', ''), ('```text\n', '```\n')):
            for prompt in ('PS> ', 'PS C:\\work> '):
                command = prompt + 'python research/recall/benchmark.py --dataset input.json '
                self.write('docs/campaign.md', opening + command + '`\n --full-research\n' + closing)
                self.assertEqual(checker.check(self.root)['status'], 'PASS', prompt)
                self.write('docs/campaign.md', opening + command + '\\\n --full-research\n' + closing)
                self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), prompt)

    def test_research_backtick_substitutions_do_not_supply_outer_flags(self):
        for path in ('`producer --full-research value`', 'prefix`producer --full-research value`#hash.json',
                     '$(producer `nested --full-research value`)'):
            command = 'python research/recall/benchmark.py --dataset ' + path
            self.write('docs/campaign.md', '```bash\n' + command + '\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), path)
            self.write('docs/campaign.md', '```bash\n' + command + ' --full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', path)
        self.write('docs/campaign.md', '```powershell\npython research/recall/benchmark.py --dataset path`#hash.json --full-research\n```\n')
        self.assertEqual(checker.check(self.root)['status'], 'PASS')

    def test_indented_and_prompt_prefixed_research_commands_require_opt_in(self):
        for prefix in ('    ', '\t', '$ ', '  $ ', '> ', 'PS> ', 'PS C:\\work> '):
            command = prefix + 'python research/recall/benchmark.py --dataset input.json'
            self.write('docs/campaign.md', '```shell\n' + command + '\n```\n')
            self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']), prefix)
            self.write('docs/campaign.md', '```shell\n' + command + ' --full-research\n```\n')
            self.assertEqual(checker.check(self.root)['status'], 'PASS', prefix)
        self.write('docs/campaign.md', '```shell\npython research/recall/benchmark.py --dataset fake--full-research.json\n```\n')
        self.assertTrue(any('requires explicit --full-research' in e for e in checker.check(self.root)['errors']))


if __name__=='__main__':
    unittest.main(verbosity=2)
