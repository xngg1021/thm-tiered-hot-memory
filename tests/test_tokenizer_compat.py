"""Public tiktoken compatibility; runs on every supported published release."""
import unittest
from unittest import mock
from thm.retrieval import TokenCounter


class TokenizerCompatibilityTests(unittest.TestCase):
    def test_exact_cache_hits_are_exercised_and_boundaries_are_not_additive(self):
        try:
            import tiktoken
        except ImportError:
            self.skipTest('tokenizer compatibility CI installs each supported release')
        ranks={bytes([i]):i for i in range(256)}
        ranks.update({b'ab':256,b'abc':257,b'  ':258})
        encoding=tiktoken.Encoding(name='thm-public-api-fixture',pat_str=r'\s+|[^\s]+',
                                  mergeable_ranks=ranks,special_tokens={})
        counter=TokenCounter(); counter.encode=mock.Mock(wraps=encoding.encode_ordinary)
        self.assertNotEqual(len(encoding.encode_ordinary('a'))+len(encoding.encode_ordinary('bc')),
                            len(encoding.encode_ordinary('abc')))
        for text in ('abc abc','a b c','中文 🔎 ab','line\n\nnext','  ab  '):
            for size in range(len(text)+1):
                prefix=text[:size]; expected=len(encoding.encode_ordinary(prefix))
                self.assertEqual(counter.count_prefix(prefix),expected)
                before=counter.encode.call_count
                self.assertEqual(counter.count_prefix(prefix),expected)
                self.assertEqual(counter.encode.call_count,before)
        self.assertGreater(counter.prefix_cache_hits,0)
        self.assertGreater(counter.prefix_cache_misses,0)
        for i in range(100):counter.count_prefix(str(i))
        self.assertLessEqual(len(counter._prefix_cache),64)
        counter.encode=lambda text:[1,2,3]
        self.assertEqual(counter.count_prefix('abc'),3)
