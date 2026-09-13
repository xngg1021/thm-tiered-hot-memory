#!/usr/bin/env python3
"""Compare a local encoder's CPU vs MPS embedding for numeric and retrieval parity.

Positive evidence requires every text's cosine distance (<= --parity-tol) plus an
identical top-k retrieval order, mirroring the CPU/GPU parity contract used by
research/recall/hardware_parity.py for full retrieval artifacts. Throughput and
device memory are recorded but are not pass/fail evidence.

Local encoder only: no network, no generation, no judge. Model bytes are read
from --model-path and must not change during loading.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import importlib.metadata
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.evidence_io import require_new_output, write_new_text
from thm.systems.artifacts import model_snapshot
from thm.runtime.identity import manifest


def parity_gate(cosines, max_abs_error, order_identical, *, cosine_tolerance=1e-4, absolute_tolerance=1e-4):
    if not 0 <= cosine_tolerance < 1 or not 0 <= absolute_tolerance < 1:
        raise ValueError('finite nonnegative parity tolerances below one required')
    if not cosines or any(not math.isfinite(x) or not -1.00001 <= x <= 1.00001 for x in cosines):
        return False
    return bool(math.isfinite(max_abs_error) and 0 <= max_abs_error <= absolute_tolerance and
                1.0-min(cosines) <= cosine_tolerance and order_identical)

DEFAULT_TEXTS = [
    "When is my meeting with Ashlee scheduled?",
    "The patent response deadline is next Friday at noon.",
    "我今天下午三点有一个面试,需要提前准备简历。",
    "Remember to buy milk, eggs and coffee on the way home.",
    "The quarterly report must be submitted before Monday.",
    "我们团队下周要完成项目的第三个里程碑。",
    "How many days are there between my meeting and the deadline?",
    "What did the client say about the budget in last week's call?",
    "请在明天之前把合同发给法务部门审核。",
    "The user asked me to summarize the previous conversation.",
]

DEFAULT_QUERY = "When is the deadline for the patent response?"


def load_encoder(path: Path, device: str):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(str(path), device='cpu', local_files_only=True,
                                trust_remote_code=False)
    return model.to(device)


def encode(model, texts, batch_size: int) -> np.ndarray:
    import torch
    model.eval()
    with torch.no_grad():
        return np.asarray(model.encode(list(texts), batch_size=batch_size,
                                       normalize_embeddings=True, show_progress_bar=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model-path', required=True)
    ap.add_argument('--model-id', default=None)
    ap.add_argument('--ref-device', default='cpu')
    ap.add_argument('--test-device', default='mps')
    ap.add_argument('--texts', default=None, help='optional newline-delimited text file')
    ap.add_argument('--query', default=DEFAULT_QUERY)
    ap.add_argument('--top-k', type=int, default=5)
    ap.add_argument('--batch-size', type=int, default=64)
    ap.add_argument('--bench-iterations', type=int, default=20)
    ap.add_argument('--parity-tol', type=float, default=1e-4)
    ap.add_argument('--absolute-tol', type=float, default=1e-4)
    ap.add_argument('--output', default=None, help='fresh JSON receipt path')
    args = ap.parse_args()
    if not 1 <= args.top_k <= 10000 or not 1 <= args.batch_size <= 256 or not 1 <= args.bench_iterations <= 100:
        ap.error('bounded top-k, batch size and iterations required')
    parity_gate([1.], 0., True, cosine_tolerance=args.parity_tol, absolute_tolerance=args.absolute_tol)

    path = Path(args.model_path).resolve()
    if not (path / 'model.safetensors').is_file() and not (path / 'pytorch_model.bin').is_file():
        print(f'model weights not found under {path}', file=sys.stderr)
        return 2

    import torch
    if args.test_device == 'mps' and not torch.backends.mps.is_available():
        print('MPS unavailable on this host; cannot run CPU-vs-MPS parity', file=sys.stderr)
        return 2

    if args.texts:
        texts = [line.rstrip('\n') for line in Path(args.texts).read_text(encoding='utf-8').splitlines() if line.strip()]
    else:
        texts = DEFAULT_TEXTS

    if not texts or len(texts) > 10000 or args.top_k > len(texts):
        ap.error('nonempty bounded texts and top-k <= corpus size required')
    with model_snapshot(path) as (snapshot, model_manifest):
        before_load_sha = manifest(snapshot)['sha256']
        ref_model = load_encoder(snapshot, args.ref_device)
        test_model = load_encoder(snapshot, args.test_device)
        after_load_sha = manifest(snapshot)['sha256']
        if before_load_sha != after_load_sha:
            raise ValueError('model bytes changed during load')

    ref_vecs = encode(ref_model, texts, args.batch_size)
    test_vecs = encode(test_model, texts, args.batch_size)

    cosines = [float(np.dot(ref_vecs[i], test_vecs[i])) for i in range(len(texts))]
    max_abs = float(np.abs(ref_vecs - test_vecs).max())
    mean_abs = float(np.abs(ref_vecs - test_vecs).mean())

    ref_q = encode(ref_model, [args.query], 1)[0]
    test_q = encode(test_model, [args.query], 1)[0]
    top_ref = np.argsort(-(ref_vecs @ ref_q))[: args.top_k].tolist()
    top_test = np.argsort(-(test_vecs @ test_q))[: args.top_k].tolist()

    # Throughput: 64-item batches for bench-iterations rounds, after warmup.
    batch = (texts * ((args.batch_size // len(texts)) + 1))[: args.batch_size]
    encode(ref_model, batch, args.batch_size)
    encode(test_model, batch, args.batch_size)

    def bench(model, n):
        samples = []
        for _ in range(n):
            t = time.perf_counter()
            encode(model, batch, args.batch_size)
            samples.append(time.perf_counter() - t)
        return float(np.mean(samples)), float(np.min(samples))

    ref_mean, ref_min = bench(ref_model, args.bench_iterations)
    test_mean, test_min = bench(test_model, args.bench_iterations)

    mps_bytes = None
    if args.test_device == 'mps' and hasattr(torch.mps, 'current_allocated_memory'):
        mps_bytes = int(torch.mps.current_allocated_memory())

    parity_ok = parity_gate(cosines, max_abs, top_ref == top_test,
                            cosine_tolerance=args.parity_tol, absolute_tolerance=args.absolute_tol)

    receipt = {
        'model_id': args.model_id,
        'model_path': str(path),
        'schema': 'thm-mps-parity/2',
        'model_sha': model_manifest['sha256'],
        'model_manifest_sha': model_manifest['sha256'],
        'model_manifest': model_manifest,
        'before_load_sha': before_load_sha,
        'after_load_sha': after_load_sha,
        'hardware_model': platform.uname().machine,
        'architecture': platform.machine(),
        'macOS_version': platform.mac_ver()[0],
        'torch_version': torch.__version__,
        'sentence_transformers_version': importlib.metadata.version('sentence-transformers'),
        'batch_size': args.batch_size,
        'platform': {'torch': torch.__version__, 'machine': sys.platform,
                     'mps_available': bool(torch.backends.mps.is_available())},
        'ref_device': args.ref_device,
        'test_device': args.test_device,
        'numeric_parity': {
            'per_text_cosine': cosines,
            'min_cosine': min(cosines),
            'max_abs_error': max_abs,
            'mean_abs_error': mean_abs,
            'parity_tol': args.parity_tol,
            'absolute_tolerance': args.absolute_tol,
            'parity_ok': parity_gate(cosines, max_abs, True, cosine_tolerance=args.parity_tol,
                                     absolute_tolerance=args.absolute_tol),
        },
        'retrieval_parity': {
            'query': args.query,
            f'top{args.top_k}_ref': top_ref,
            f'top{args.top_k}_test': top_test,
            'order_identical': top_ref == top_test,
        },
        'throughput': {
            f'{args.ref_device}_mean_ms': ref_mean * 1000,
            f'{args.ref_device}_min_ms': ref_min * 1000,
            f'{args.test_device}_mean_ms': test_mean * 1000,
            f'{args.test_device}_min_ms': test_min * 1000,
            'speedup_mean': ref_mean / test_mean if test_mean else None,
            'batch_size': args.batch_size,
            'iterations': args.bench_iterations,
        },
        'device_memory': {'mps_allocated_bytes': mps_bytes},
        'parity_ok': parity_ok,
        'generation_calls': 0,
        'judge_calls': 0,
    }

    if args.output:
        require_new_output(args.output)
        write_new_text(args.output, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if parity_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
