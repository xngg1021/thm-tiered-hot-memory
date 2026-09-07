#!/usr/bin/env python3
"""Isolated build-resource census; no QA labels or query timing contamination."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.recall.benchmark import DATASET_SHA256
from thm.retrieval import SearchIndex, TokenCounter
from thm.sources import locomo_documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_SHA256:
        raise ValueError('pinned dataset required')
    counter = TokenCounter('cl100k_base')
    results = []
    with tempfile.TemporaryDirectory() as root:
        for number, sample in enumerate(json.loads(raw)):
            path = Path(root)/f'{number}.sqlite'
            index = SearchIndex(path, counter)
            docs = list(locomo_documents(sample))
            start = time.perf_counter()
            index.replace_scope(str(sample['sample_id']), docs)
            elapsed = time.perf_counter()-start
            index.close()
            results.append({'scope': str(sample['sample_id']), 'documents': len(docs),
                            'index_build_seconds': elapsed, 'database_bytes': path.stat().st_size})
    out = {'dataset_sha256': DATASET_SHA256, 'builds': results,
           'process_peak_rss_native_units': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
           'rss_unit': 'bytes' if sys.platform == 'darwin' else 'KiB',
           'platform': platform.platform(),
           'scope': 'Isolated index-build process including tokenizer; not query peak memory.',
           'new_persistent_projection_bytes': 0, 'generation_calls': 0, 'embedding_used': False}
    Path(args.output).write_text(json.dumps(out, indent=2)+'\n')


if __name__ == '__main__': main()
