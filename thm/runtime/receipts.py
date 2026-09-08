"""Exclusive receipts. Public payloads use hashes and logical names, never paths."""
import json
from pathlib import Path


def write_receipt(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    return payload


def import_dispatch(path, profile_id):
    import hashlib
    raw = Path(path).read_bytes(); data = json.loads(raw)
    if data.get('embedding_profile_id') != profile_id or not data.get('profiler') or not data.get('observed_kernel_dispatch'):
        raise ValueError('profiler receipt requires exact profile and observed dispatch evidence')
    return {'embedding_profile_id':profile_id,'profiler':data['profiler'],
            'observed_kernel_dispatch':data['observed_kernel_dispatch'], 'raw_evidence_sha256':hashlib.sha256(raw).hexdigest()}
