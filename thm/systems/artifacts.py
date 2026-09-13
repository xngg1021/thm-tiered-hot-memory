"""Owned model snapshots: the native runtime consumes the bytes we validated."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
from thm._bounded_files import validated_descriptor
from thm.runtime.identity import manifest


@contextmanager
def model_snapshot(root, *, max_bytes=32*1024**3, max_files=10000):
    root = Path(root)
    expected = manifest(root)
    if len(expected['files']) > max_files or sum(row['bytes'] for row in expected['files']) > max_bytes:
        raise ValueError('model snapshot bound')
    with tempfile.TemporaryDirectory(prefix='thm-model-snapshot-') as directory:
        target = Path(directory)
        for row in expected['files']:
            source, destination = root/row['name'], target/row['name']
            destination.parent.mkdir(parents=True, exist_ok=True)
            hasher, length = hashlib.sha256(), 0
            with validated_descriptor(source) as (fd, info), destination.open('xb') as stream:
                if info.st_size != row['bytes']:
                    raise ValueError('model changed before copy')
                while True:
                    block = os.read(fd, min(1048576, row['bytes']-length+1))
                    if not block:
                        break
                    length += len(block)
                    if length > row['bytes']:
                        raise ValueError('model grew during copy')
                    hasher.update(block)
                    if stream.write(block) != len(block):
                        raise OSError('short model snapshot write')
            if length != row['bytes'] or hasher.hexdigest() != row['sha256']:
                raise ValueError('model consumed bytes changed')
        observed = manifest(target)
        if observed != expected:
            raise ValueError('snapshot manifest mismatch')
        yield target, observed
        if manifest(target) != observed:
            raise ValueError('runtime mutated its model snapshot')
