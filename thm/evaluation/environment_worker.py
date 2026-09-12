"""Internal worker for explicitly trusted environment callbacks; never unpickle uploads."""
import base64
import json
import pickle
from pathlib import Path
import sys
from .environment import execute_environment


def main():
    # Parent attaches the Windows job before any supplied callback is deserialized.
    if sys.stdin.buffer.readline(4) != b'go\n':return 2
    source,output=map(Path,sys.argv[1:])
    try:
        from thm._process_containment import install_descendant_containment
        containment = install_descendant_containment()
        if source.stat().st_size>8_000_000:raise ValueError('configuration bound')
        with source.open('rb') as stream:args=pickle.load(stream)
        receipt,trace=execute_environment(*args)
        from .contracts import digest
        receipt.pop('receipt_sha256')
        receipt['descendant_containment'] = containment
        receipt['receipt_sha256'] = digest(receipt)
        result={'receipt':receipt,'trace':base64.b64encode(trace).decode()}
        code=0
    except Exception as exc:
        result={'error':type(exc).__name__};code=1
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)
    return code


if __name__=='__main__':raise SystemExit(main())
