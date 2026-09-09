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
    samples = {'baseline': [], 'candidate': []}; cpus = {'baseline': [], 'candidate': []}; refs = []
    cold_ms = None
    try:
        for repeat in range(min(9, task.get('repeats', 5)) + 1):
            outputs = {}
            pair = [('baseline', baseline), ('candidate', candidate)]
            for label, reader in pair if repeat % 2 == 0 else reversed(pair):
                reader._results.clear()
                started = time.perf_counter(); cpu_started = time.process_time()
                result = reader.search(task['scope'], task['query'], encoder=encoder, model_id=encoder.model_id, diagnostics=True, **task['settings'])
                if result['generation'] != task['generation']:
                    raise ValueError('shadow source generation changed')
                elapsed = (time.perf_counter()-started)*1000
                if label == 'candidate' and not repeat:
                    cold_ms = executor.last.get('load_ms')
                if repeat:
                    samples[label].append(elapsed + task.get('observed_encode_floor_ms', 0))
                    cpus[label].append(time.process_time()-cpu_started)
                outputs[label] = signature(result)
            refs = outputs
        return {**samples, 'reference': refs['baseline'], 'result': refs['candidate'], 'generation': task['generation'],
                'candidate_id': task['candidate_id'], 'key': task['key'], 'provider': task['provider'],
                'memory_bytes': executor.manager.usage(task['device']), 'cpu_samples': cpus,
                'startup_ms': cold_ms, 'host_device_bytes': executor.last.get('host_device_bytes'),
                'observed_encode_floor_ms': task.get('observed_encode_floor_ms', 0),
                'sample_kind': 'cached-embedding-replay-plus-observed-encode-floor'}
    finally:
        baseline.close(); candidate.close(); executor.close(); registry.close()


def main():
    envelope = json.loads(sys.stdin.read(2*1024*1024)); limits = envelope['limits']; task = envelope['task']
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(limits['cpu'])), max(1, int(limits['cpu']))))
        resource.setrlimit(resource.RLIMIT_FSIZE, (limits['io'], limits['io']))
        # Parent public process accounting bounds physical RSS. RLIMIT_DATA
        # rejects Darwin allocator arenas even when the actual RSS is small.
    if task.get('operation') == 'probe-spec':
        from .registry import ProviderRegistry
        from .contracts import ProviderSpec
        spec = ProviderSpec(**task['spec']); registry = ProviderRegistry(); registry.register(spec)
        result = registry.get(spec.provider_id).probe()
    elif task.get('operation') == 'probe':
        from .registry import builtin_registry
        registry = builtin_registry(extensions=False)
        result = registry.get(task['provider']).probe()
    elif task.get('operation') == 'discover':
        from .registry import builtin_registry
        registry = builtin_registry(extensions=False)
        descriptions = [r for r in registry.list(operation='vector-search')
                        if r['provider_id'] != 'host.exact' and r['availability'] == 'unprobed' and r['maturity'] >= 3]
        cursor = task.get('cursor', 0); rows = []
        for description in descriptions[cursor:cursor+1]:
            name = description['provider_id']
            try:
                row = registry.get(name).probe()
            except Exception as exc:
                row = {'availability': 'probe-failed', 'error': type(exc).__name__}
            rows.append({'provider': name, **row})
        result = {'providers': rows, 'next_cursor': cursor+1, 'done': cursor+1 >= len(descriptions)}
    elif task.get('operation') == 'replay':
        result = replay(task)
    else:
        raise ValueError('unknown bounded shadow operation')
    print('THM_RESULT:' + json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('THM_ERROR:' + json.dumps({'stage': 'setup-or-operation', 'error': type(exc).__name__}))
        raise SystemExit(1)
