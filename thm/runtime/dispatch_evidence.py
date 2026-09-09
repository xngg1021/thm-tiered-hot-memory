"""Optional raw oneDNN execution evidence; capability banners never prove dispatch."""
import hashlib
import re
from pathlib import Path


def observe(path, *, backend, workload_sha256):
    if not re.fullmatch('[0-9a-f]{64}',workload_sha256):raise ValueError('exact workload hash required')
    raw=Path(path).read_bytes()
    if len(raw)>4*1024*1024:raise ValueError('dispatch log exceeds bounded input')
    # Match only execution records and return a closed vocabulary, never raw paths.
    observed=set()
    for line in raw.decode('utf-8',errors='replace').splitlines():
        if not re.match(r'^(?:onednn|dnnl)_verbose,(?:v\d+,)?(?:primitive,)?exec,cpu,',line):continue
        for token,label in (('avx512_core_vnni','AVX512-VNNI'),('avx512_core','AVX512'),('avx2','AVX2')):
            if token in line:observed.add(label);break
    return {'backend':backend,'workload_sha256':workload_sha256,
        'raw_evidence_sha256':hashlib.sha256(raw).hexdigest(),'dispatch_source':'oneDNN-verbose-exec',
        'observed_kernel_dispatch':sorted(observed) if observed else None,
        'status':'observed-in-supplied-log' if observed else 'unknown',
        'binding':'caller-supplied workload identity; collector must retain acquisition provenance',
        'private_details_redacted':True}
