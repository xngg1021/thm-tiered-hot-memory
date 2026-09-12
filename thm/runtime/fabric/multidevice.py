"""Explicit sharded indexes with deterministic global ranking and atomic rebuild."""
from dataclasses import replace
import math
import threading


class MultiDeviceIndex:
    def __init__(self, providers, *, budgets):
        if not providers or len(providers) > 16 or len(providers) != len(budgets) or any(type(b) is not int or b <= 0 for b in budgets):
            raise ValueError('bounded provider/budget topology required')
        self.providers, self.budgets = tuple(providers), tuple(budgets)
        self.shards, self.ids, self.generation = [], (), None
        self.lock, self.closed = threading.RLock(), False

    def build(self, matrix, ids, identity):
        import numpy as np
        matrix = np.asarray(matrix, dtype=np.float32)
        if matrix.ndim != 2 or len(matrix) != len(ids) or len(set(ids)) != len(ids) or not len(ids) or not np.isfinite(matrix).all():
            raise ValueError('complete finite vector snapshot required')
        with self.lock:
            if self.closed:
                raise ValueError('multi-device index closed')
            new = []
            try:
                for i, (provider, budget) in enumerate(zip(self.providers, self.budgets)):
                    positions = list(range(i, len(ids), len(self.providers)))
                    if not positions:
                        continue
                    shard = matrix[positions]
                    if shard.nbytes > budget:
                        raise MemoryError('shard capacity exceeded')
                    ref = replace(identity, device=f'shard:{i}', index_config=identity.index_config+f'/shard/{i}')
                    handle = provider.build(shard, [ids[j] for j in positions], ref)
                    new.append((provider, handle))
                    if handle.bytes > budget:
                        raise MemoryError('native shard allocation exceeded capacity')
            except Exception:
                for _, handle in new:
                    handle.close()
                raise
            old, self.shards = self.shards, new
            self.ids, self.generation = tuple(ids), identity.generation
            for _, handle in old:
                handle.close()

    def search(self, queries, top_k, *, generation):
        with self.lock:
            if self.closed or not self.shards or self.generation != generation:
                raise ValueError('stale multi-device snapshot')
            if type(top_k) is not int or not 1 <= top_k <= len(self.ids):
                raise ValueError('invalid global top-k')
            results = [[] for _ in queries]
            receipts = []
            order = {identifier: i for i, identifier in enumerate(self.ids)}
            for provider, handle in self.shards:
                rows, receipt = provider.search(handle, queries, min(top_k, len(handle.ids)))
                if len(rows) != len(results):
                    raise ValueError('incomplete shard result')
                for merged, (ids, scores) in zip(results, rows):
                    if len(ids) != len(scores) or len(set(ids)) != len(ids) or any(i not in handle.ids for i in ids) or any(not math.isfinite(v) for v in scores):
                        raise ValueError('invalid shard result')
                    merged.extend(zip(ids, scores))
                receipts.append(receipt)
            output = []
            for rows in results:
                selected = sorted(rows, key=lambda row: (-row[1], order[row[0]]))[:top_k]
                if len(selected) != top_k:
                    raise ValueError('missing global top-k')
                output.append(([r[0] for r in selected], [r[1] for r in selected]))
            return output, {'shards': receipts, 'generation': generation, 'topology': 'explicit-shards',
                            'semantic_acceptance': 'requires-independent-reference-guard', 'hardware_accepted': False}

    def close(self):
        with self.lock:
            for _, handle in self.shards:
                handle.close()
            self.shards = []
            self.closed = True
