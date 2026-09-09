"""Small read-only replay worker; its output contains hashes, never source text."""
import json
import os
import sys
import time


def signature(result):
    from .contracts import identity
    return {'generation': result['generation'], 'ranked_ids': result['ranked_ids'],
            'budget': result['budget'], 'budget_used': result['budget_used'],
            'complete_evidence_ids': result.get('complete_evidence_ids'),
            'context': identity(result['context']),
            'dense_scores': (result.get('runtime_diagnostics') or {}).get('scores'),
            'selected': [{k: r[k] for k in ('id', 'hash', 'source', 'complete')} for r in result['selected']]}


def replay(task):
    from thm.retrieval import SearchIndex, TokenCounter
    from thm.runtime.identity import EmbeddingProfile
    from .service import ResidentExecutor
    from .registry import builtin_registry
    class ReplayEncoder:
        model_id = task['model_id']
        profile = EmbeddingProfile(**task['embedding_profile'])
        def __call__(self, texts):
            if any(text != task['query'] for text in texts):
                raise ValueError('shadow query identity mismatch')
            return [task['query_vector'] for text in texts]
    registry = builtin_registry(extensions=False)
    encoder = ReplayEncoder()
    baseline = SearchIndex(task['db'], TokenCounter(task['counter']), readonly=True)
    candidate = SearchIndex(task['db'], TokenCounter(task['counter']), readonly=True)
    executor = ResidentExecutor(registry, task['provider'], task['device'], task['memory_budget'])
    candidate._vector_executor = executor
    samples = {'baseline': [], 'candidate': []}; refs = []
    try:
        for repeat in range(min(9, task.get('repeats', 5)) + 1):
            outputs = []
            for label, reader in [('baseline', baseline), ('candidate', candidate)]:
                reader._results.clear()
                started = time.perf_counter()
                result = reader.search(task['scope'], task['query'], encoder=encoder, model_id=encoder.model_id, diagnostics=True, **task['settings'])
                if result['generation'] != task['generation']:
                    raise ValueError('shadow source generation changed')
                elapsed = (time.perf_counter()-started)*1000
                if repeat:
                    samples[label].append(elapsed)
                outputs.append(signature(result))
            refs = outputs
        return {**samples, 'reference': refs[0], 'result': refs[1], 'generation': task['generation'],
                'candidate_id': task['candidate_id'], 'key': task['key'], 'provider': task['provider'],
                'memory_bytes': executor.manager.usage(task['device']), 'sample_kind': 'read-only-request-replay'}
    finally:
        baseline.close(); candidate.close(); executor.close(); registry.close()


def main():
    envelope = json.loads(sys.stdin.read(2*1024*1024)); limits = envelope['limits']; task = envelope['task']
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(limits['cpu'])), max(1, int(limits['cpu']))))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits['io'], limits['io']))
        # Native libraries reserve substantial virtual address space. Bound resident
        # allocation in the handle manager; explicit AS ceiling includes interpreter.
        if sys.platform.startswith('linux'):
            resource.setrlimit(resource.RLIMIT_AS, (limits['memory']+512*1024**2, limits['memory']+512*1024**2))
    if task.get('operation') == 'probe':
        from .registry import builtin_registry
        registry = builtin_registry(extensions=False)
        result = registry.get(task['provider']).probe()
    elif task.get('operation') == 'replay':
        result = replay(task)
    else:
        raise ValueError('unknown bounded shadow operation')
    print('THM_RESULT:' + json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
