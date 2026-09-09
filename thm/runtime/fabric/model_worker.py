"""Private local-model preparation, paired retrieval gate, and warm serving RPC.

The worker owns a disposable database copy and its own embedding profile. It
never publishes vectors into the source index or invents tensor preprocessing.
"""
import json
import os
from pathlib import Path
import sys
import time


def prepare_encoder(task, root):
    from .registry import builtin_registry
    from .inference import TorchInference
    from ..identity import EmbeddingProfile, manifest, validate_vectors
    registry = builtin_registry(extensions=False)
    provider = registry.get(task['inference_provider'])
    source = Path(task['model_source'])
    expected = task['reference_profile']
    contents = manifest(source)
    if sum(f['bytes'] for f in contents['files'])*2 > task.get('memory_budget',256*1024**2):
        raise MemoryError('two model copies exceed preparation memory budget')
    if contents['sha256'] != expected['source_manifest_sha256']:
        raise ValueError('local model source identity changed')
    if isinstance(provider, TorchInference):
        artifact = provider.prepare(source, precision='fp32')
        provider.load(artifact)
        device = provider.options.get('device', 'cpu')
        profile = EmbeddingProfile(artifact.source_sha, task['inference_provider'], artifact.provider_version,
                                   'fp32', expected['dimension'], device=device,
                                   normalization=expected['normalization'], encoder_input=expected['encoder_input'])
        class Encoder:
            model_id = task['model_id']
            document_batch_size = 8
            query_batch_size = 1
            def __call__(self, texts):
                return validate_vectors(provider.encode_many(texts), self.profile, len(texts))
            def close(self):
                registry.close()
        encoder = Encoder(); encoder.profile = profile
        return encoder
    # SentenceTransformer's own exporter/pooling/tokenizer contract bridges
    # supported tensor runtimes. Arbitrary raw ONNX/CoreML inputs remain explicit.
    from ..prepare import convert
    from ..backends import create
    options = dict(provider.spec.options)
    family = 'openvino_fp32' if task['inference_provider'].startswith('intel.openvino') else 'onnxruntime_fp32'
    if provider.__class__.__name__ not in ('OrtInference', 'OpenVINOInference'):
        registry.close(); raise ValueError('provider has no automatic text-model bridge')
    derived = root/'compiled-model'
    receipt = convert({'model_path': str(source), 'source_manifest_sha256': expected['source_manifest_sha256'],
                       'backend': family, 'staging': str(derived)})
    registry.close()
    if receipt.get('status') != 'prepared':
        raise ValueError('bounded local text-model export unavailable')
    device = options.get('device', 'AUTO') if family.startswith('openvino') else options['ep']
    return create(derived, task['model_id'], backend=family, device=device, threads=1,
                  document_batch_size=8, query_batch_size=1, isolated=True)


def run(task, wire):
    from thm.retrieval import SearchIndex, TokenCounter
    from ..backends import create
    from .shadow_worker import signature
    from ..identity import manifest
    root = Path(task['workspace'])
    source = SearchIndex(task['db'], TokenCounter(task['counter']), readonly=True)
    replica = SearchIndex(root/'index.sqlite', TokenCounter(task['counter']))
    baseline = candidate = None
    try:
        source.db.backup(replica.db, pages=32, sleep=0)
        generation = source.db.execute('SELECT generation FROM scopes WHERE scope=?', (task['scope'],)).fetchone()[0]
        if generation != task['generation']:
            raise ValueError('source snapshot changed')
        started = time.perf_counter()
        baseline = create(task['model_source'], task['model_id'], backend='torch_fp32',
                          device=task['reference_profile']['device'], threads=task.get('reference_threads',1),
                          document_batch_size=8, query_batch_size=1, isolated=True)
        if baseline.profile.identity() != {**task['reference_profile'], 'embedding_profile_id': baseline.profile.id}:
            raise ValueError('reference encoder contract changed')
        candidate = prepare_encoder(task, root)
        replica.embed(task['scope'], candidate, task['model_id'], vector_storage='blob')
        startup = (time.perf_counter()-started)*1000
        times = {'baseline': [], 'candidate': []}; cpus = {'baseline': [], 'candidate': []}; signatures = {}; consistent = True
        for repeat in range(6):
            pair = [('baseline', source, baseline), ('candidate', replica, candidate)]
            for label, index, encoder in pair if repeat % 2 == 0 else reversed(pair):
                import torch
                torch.set_num_threads(task.get('reference_threads',1) if label == 'baseline' else 1)
                index._cache.clear(); index._results.clear()
                begin = time.perf_counter(); cpu = time.process_time()
                result = index.search(task['scope'], task['query'], encoder=encoder, model_id=task['model_id'],
                                      diagnostics=True, **task['settings'])
                if repeat:
                    times[label].append((time.perf_counter()-begin)*1000)
                    cpus[label].append(time.process_time()-cpu)
                signatures[label] = signature(result)
            from .optimizer import SemanticGuard
            consistent = consistent and SemanticGuard.compare(signatures['baseline'],signatures['candidate'],
                dimension=candidate.profile.dimension)['semantic_admission']
        if manifest(task['model_source'])['sha256'] != task['reference_profile']['source_manifest_sha256']:
            raise ValueError('model changed during preparation')
        import torch
        torch.set_num_threads(1)
        baseline.close(); baseline = None
        device = candidate.profile.device.split(':')[0]
        api = getattr(torch,device,None)
        vram = 0 if device in ('cpu','CPU','CPUExecutionProvider') else None
        if api and hasattr(api,'max_memory_allocated'):
            vram = api.max_memory_allocated()
        elif device == 'mps' and hasattr(torch.mps,'current_allocated_memory'):
            vram = torch.mps.current_allocated_memory()
        wire({'status': 'ready', 'vram_bytes':vram, 'all_repeats_consistent':consistent, **times, 'cpu_samples': cpus, 'startup_ms': startup,
              'reference': signatures['baseline'], 'result': signatures['candidate'],
              'embedding_profile': candidate.profile.identity(), 'sample_kind': 'observed-end-to-end',
              'generation': generation, 'generation_calls': 0, 'authority_mutations': 0})
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('close'):
                break
            if len(request['queries']) > 32 or request['generation'] != generation:
                raise ValueError('model RPC request outside admitted snapshot')
            current = source.db.execute('SELECT generation FROM scopes WHERE scope=?', (task['scope'],)).fetchone()
            if not current or current[0] != generation:
                raise ValueError('source generation changed')
            begin = time.perf_counter(); cpu = time.process_time()
            results = replica.search_many(task['scope'], request['queries'], encoder=candidate,
                model_id=task['model_id'], query_batch_size=1, semantic_guard=True, **task['settings'])
            wire({'results': results, 'cpu_seconds': time.process_time()-cpu,
                  'wall_ms': (time.perf_counter()-begin)*1000, 'embedding_profile': candidate.profile.identity()})
    finally:
        if baseline:
            baseline.close()
        if candidate:
            candidate.close()
        source.close(); replica.close()


def main():
    # Native libraries writing directly to stdout cannot corrupt the private RPC.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    def wire(value):
        protocol.write(json.dumps(value, allow_nan=False, ensure_ascii=True)+'\n'); protocol.flush()
    try:
        task = json.loads(sys.stdin.readline(2*1024*1024))
        from ..worker import configure
        configure({'threads': 1})
        run(task, wire)
    except Exception as exc:
        wire({'status': 'failed', 'error': type(exc).__name__})
    finally:
        protocol.close()


if __name__ == '__main__':
    main()
