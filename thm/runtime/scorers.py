"""Scoring placement is independent of embedding placement; stable row-order ties."""
import time


def score(documents,queries,name='numpy_reference'):
    import numpy as np
    d=np.asarray(documents,dtype=np.float32);q=np.asarray(queries,dtype=np.float32)
    if d.ndim!=2 or q.ndim!=2 or d.shape[1]!=q.shape[1] or not np.isfinite(d).all() or not np.isfinite(q).all(): raise ValueError('invalid scoring matrices')
    start=time.perf_counter();transfer=0.0
    if name=='numpy_reference': values=d @ q.T
    elif name in ('torch_cpu','torch_cuda'):
        import torch
        device='cuda' if name=='torch_cuda' else 'cpu'
        left=torch.from_numpy(d).to(device);right=torch.from_numpy(q).to(device)
        if device=='cuda': torch.cuda.synchronize()
        transfer=(time.perf_counter()-start)*1000
        values=(left @ right.T).cpu().numpy()
    else: raise ValueError('unsupported dense scorer')
    if not np.isfinite(values).all(): raise ValueError('nonfinite dense scores')
    return values,{'dense_scoring':(time.perf_counter()-start)*1000,'transfer':transfer,'scorer':name,'operation':'GEMM' if len(q)>1 else 'GEMV'}
