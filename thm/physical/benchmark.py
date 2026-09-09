"""THM access costs on bounded scratch; no cache, power or device mutation."""
from concurrent.futures import ThreadPoolExecutor
import math
import mmap
import os
from pathlib import Path
import random
import tempfile
import time
from .contracts import StorageProfile


def benchmark(target, *, scratch_bytes=8*1024*1024, seconds=5., concurrency=1):
    if type(scratch_bytes) is not int or not 1024*1024<=scratch_bytes<=128*1024*1024:
        raise ValueError('scratch bound is 1–128 MiB')
    if not math.isfinite(seconds) or not 0<seconds<=60 or concurrency not in (1,2,4):raise ValueError('invalid time/concurrency bound')
    if target.adapter!='local-filesystem' or target.readonly is not False:raise ValueError('verified writable local adapter required')
    root=Path(target.root)
    if root.is_symlink() or not root.is_dir():raise ValueError('invalid root')
    deadline=time.monotonic()+seconds;start=time.perf_counter();costs=[]
    fd,name=tempfile.mkstemp(prefix='.thm-bench-',dir=root)
    try:
        block=bytes((i%251 for i in range(1024*1024)))
        with os.fdopen(fd,'wb') as f:
            for offset in range(0,scratch_bytes,len(block)):
                if time.monotonic()>=deadline:raise TimeoutError('scratch preparation exceeded budget')
                f.write(block[:min(len(block),scratch_bytes-offset)])
            f.flush();os.fsync(f.fileno())
        def access(offset,size,mode):
            t=time.perf_counter()
            with open(name,'rb') as f:
                if mode=='mmap':
                    with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapped:data=mapped[offset:offset+size]
                else:f.seek(offset);data=f.read(size)
            if len(data)!=size:raise ValueError('short benchmark read')
            return (time.perf_counter()-t)*1000
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for size in (4096,16384,65536,262144,1048576):
                for operation in ('buffered-random','buffered-sequential','mmap'):
                    latencies=[];rng=random.Random(0);t=time.perf_counter()
                    for batch in range(8):
                        if time.monotonic()>=deadline:break
                        offsets=[(rng.randrange(max(1,scratch_bytes//size)) if operation!='buffered-sequential' else (batch*concurrency+i)%(scratch_bytes//size))*size for i in range(concurrency)]
                        futures=[pool.submit(access,offset,size,operation) for offset in offsets]
                        latencies.extend(f.result() for f in futures)
                    elapsed=time.perf_counter()-t
                    if latencies:costs.append({'operation':operation,'size':size,'concurrency':concurrency,
                        'samples':len(latencies),'p95_ms':sorted(latencies)[math.ceil(.95*len(latencies))-1],
                        'bytes_per_second':len(latencies)*size/elapsed,'write_amplification':None})
        return StorageProfile(target.fingerprint,tuple(costs),scratch_bytes,time.perf_counter()-start)
    finally:Path(name).unlink(missing_ok=True)
