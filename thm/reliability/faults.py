"""Deterministic faults against real publication, identity and worker lifecycles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from thm.systems.contracts import atomic_json
from thm.runtime.fabric.resources import ChildBudget, stop_owned_process_tree


def publication_fault(fault):
    if fault not in ('short-write','disk-full'):
        raise ValueError('unknown publication fault')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'profile.json'
        atomic_json(path,{'generation':1})
        original=path.read_bytes()
        fdopen=os.fdopen
        class FailingWriter:
            def __init__(self,stream): self.stream=stream
            def __enter__(self): self.stream.__enter__(); return self
            def __exit__(self,*args): return self.stream.__exit__(*args)
            def write(self,data):
                if fault=='disk-full': raise OSError(28,'injected disk full')
                self.stream.write(data[:1]); return 1
        rejected=False
        with patch('thm.systems.contracts.os.fdopen',side_effect=lambda *args,**kwargs:FailingWriter(fdopen(*args,**kwargs))):
            try: atomic_json(path,{'generation':2})
            except OSError: rejected=True
        return {'recovered':rejected and path.read_bytes()==original,
                'mechanism':fault,'atomic_old_generation_preserved':path.read_bytes()==original}


def worker_fault(fault,timeout=.1):
    if fault not in ('provider-crash','worker-hang'):
        raise ValueError('unknown worker fault')
    process=subprocess.Popen([sys.executable,'-m','thm.reliability.faults',fault],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix')
    budget=None
    observed=False
    try:
        budget=ChildBudget(process,memory=128*1024**2,cpu=1,io=1048576)
        try:
            process.communicate(b'go\n',timeout=timeout)
            observed=process.returncode!=0
        except subprocess.TimeoutExpired:
            observed=True
    finally:
        stop_owned_process_tree(process,budget)
        if budget is not None: budget.close()
        if process.stdout: process.stdout.close()
    return {'recovered':observed and process.poll() is not None,'mechanism':fault,
            'worker_reaped':process.poll() is not None}


def byte_identity_fault(fault):
    from thm.systems.syscore import SysCore
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'source'
        original=b'authoritative source'
        path.write_bytes(original)
        sha=hashlib.sha256(original).hexdigest()
        if fault=='storage-disappearance': path.unlink()
        else: path.write_bytes(b'corrupt or replaced source')
        rejected=False
        try: SysCore().read_verified(path,sha)
        except (OSError,ValueError): rejected=True
        path.write_bytes(original)
        return {'recovered':rejected and SysCore().read_verified(path,sha)==original,
                'mechanism':fault,'source_identity_verified':True}


def main():
    if sys.stdin.buffer.readline(4)!=b'go\n': return 2
    from thm._process_containment import install_descendant_containment
    install_descendant_containment()
    if sys.argv[1]=='provider-crash': return 9
    import time
    time.sleep(30)
    return 0


if __name__=='__main__':raise SystemExit(main())
