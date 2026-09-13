#!/usr/bin/env python3
"""Drive the BEAM harness across all four chat sizes, merge results."""
import json, os, sys, statistics, time
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, '/tmp')
from beam_harness import run_conversation, load_sample, summarize, BEAM

SIZES = ['100K', '500K', '1M', '10M']

def main(workers, out):
    adapter = BEAM()
    all_results = []
    for size in SIZES:
        base = f'/tmp/beam-repo/chats/{size}'
        convs = sorted([d for d in os.listdir(base) if d.isdigit()], key=int)
        print(f'=== {size}: {len(convs)} conversations ===', flush=True)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_conversation, size, c, adapter): (size, c) for c in convs}
            for f in as_completed(futs):
                r = f.result()
                for x in r:
                    x['size'] = size
                all_results += r
                # 定期落盘,防止中断丢失
                json.dump(all_results, open(out, 'w'), ensure_ascii=False, indent=2)
        print(f'=== {size} 完成,累计 {len(all_results)} 题 ===', flush=True)
    json.dump(all_results, open(out, 'w'), ensure_ascii=False, indent=2)
    print('\n===== 全量汇总 =====')
    # 按 chat_size 和 category 双重汇总
    by_size = {}
    for r in all_results:
        by_size.setdefault(r.get('size', '?'), []).append(r['score'])
    for sz in SIZES:
        if sz in by_size:
            v = by_size[sz]
            print(f'{sz:5s} 平均 {statistics.mean(v)*100:5.1f}%  (n={len(v)})')
    summarize(all_results)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--out', default='/tmp/beam_all_results.json')
    args = ap.parse_args()
    main(args.workers, args.out)
