"""Offline bounded acceptance; full datasets require explicit full-research."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from .adapters import ADAPTERS
from .contracts import digest
from .fixtures import FIXTURES
from .runner import run, storage_probe


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('smoke', 'acceptance', 'full-research'), default='acceptance')
    p.add_argument('--full-research', action='store_true')
    p.add_argument('--benchmark', choices=tuple(ADAPTERS))
    p.add_argument('--dataset', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--wall-seconds', type=int, default=3300)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if (args.mode == 'full-research') != args.full_research:
        p.error('full campaign requires --mode full-research --full-research')
    if not 1 <= args.wall_seconds <= (86400 if args.full_research else 3300):
        p.error('bounded acceptance allows 1–3300 seconds')
    if args.dataset and not args.benchmark:
        p.error('--dataset requires --benchmark')
    if args.full_research and not args.dataset:
        p.error('full-research requires an explicit external dataset')
    if args.output.exists():
        p.error('output exists; use a new receipt directory')
    if not args.worker:
        from .bounds import bounded_process
        command = [sys.executable, '-m', 'thm.evaluation', *sys.argv[1:], '--worker']
        raise SystemExit(bounded_process(command, args.wall_seconds, args.output))
    args.output.mkdir(parents=True)
    started = time.monotonic()
    try:
        receipts = []
        for name in ([args.benchmark] if args.benchmark else ADAPTERS):
            if args.dataset:
                if not args.full_research and args.dataset.stat().st_size > 4_000_000:
                    raise ValueError('bounded input exceeds 4 MB; explicit full-research required')
                raw = args.dataset.read_bytes()
                source = json.loads(raw)
            else:
                source = FIXTURES[name]
            receipt = run(ADAPTERS[name], source, args.output / name, mode=args.mode,
                          provenance='external-dataset' if args.dataset else 'deterministic-fixture',
                          full_research=args.full_research)
            receipts.append(receipt)
        physical = storage_probe(args.output / 'physical-scratch')
        for receipt in receipts:
            receipt['layers']['systems-runtime']['physical_probe'] = physical
            receipt.pop('receipt_sha256')
            receipt['receipt_sha256'] = digest(receipt)
            (args.output / (receipt['benchmark'] + '.json')).write_text(
                json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
        # The acceptance entrypoint also verifies real memory interfaces with tiny inputs.
        from .memory import AgentMemory, V2Memory
        v2 = V2Memory(args.output / 'v2-interface.sqlite', 'fixture')
        arena = AgentMemory(args.output / 'arena-interface.sqlite', 'fixture')
        try:
            v2.insert(FIXTURES['longmemeval-v2'][0]['trajectories'][0])
            if 'cobalt' not in str(v2.query('observatory access code')):
                raise ValueError('V2 interface fixture failed')
            arena.add('The observatory access code is cobalt.')
            if 'cobalt' not in arena.wrap_user_prompt('observatory access code'):
                raise ValueError('MemoryArena cross-session fixture failed')
        finally:
            v2.close()
            arena.close()
        result = {'status': 'passed', 'mode': args.mode, 'wall_seconds': time.monotonic()-started,
                  'full_dataset_acceptance': False, 'benchmark_receipts': [r['receipt_sha256'] for r in receipts],
                  'interface_evidence': 'deterministic fixtures; no live agent outcome',
                  'generation_calls': 0, 'judge_calls': 0}
        (args.output / 'acceptance.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    except Exception as exc:
        (args.output / 'failed.json').write_text(json.dumps({'status': 'failed', 'error': str(exc),
            'full_dataset_acceptance': False}) + '\n', encoding='utf-8', newline='\n')
        raise
    print(json.dumps(result))


if __name__ == '__main__':
    main()
