"""Persistent owned process for explicitly configured storage transports."""
import base64
import json
import os
from pathlib import Path
import pickle
import signal
import subprocess
import sys
import tempfile
import time
from thm._bounded_files import read_regular


def encode(value):
    return {'binary':base64.b64encode(value).decode()} if isinstance(value,bytes) else {'json':value}


def decode(value):
    return base64.b64decode(value['binary'],validate=True) if 'binary' in value else value['json']


class BackendWorker:
    """Only trusted local factories/objects are serialized; RPC frames are JSON."""
    def __init__(self,config,definition):
        try:payload=pickle.dumps((config,definition))
        except (pickle.PicklingError,TypeError,AttributeError) as exc:
            raise ValueError('transport needs a pickleable object or top-level worker factory') from exc
        if len(payload)>8_000_000:raise ValueError('transport configuration exceeds 8 MB')
        self.timeout=config.timeout_seconds;self.maximum=2*config.max_object_bytes+65536
        self.directory=tempfile.TemporaryDirectory(prefix='thm-storage-');self.root=Path(self.directory.name)
        self.process=self.budget=None;self.sequence=0;self.receipt={};self.closed=False
        try:
            (self.root/'configuration.pickle').write_bytes(payload)
            env=dict(os.environ)
            env['PYTHONPATH']=os.pathsep.join(str(Path(p).resolve()) for p in sys.path if Path(p or '.').is_dir())
            self.process=subprocess.Popen([sys.executable,'-m','thm.physical.backend_worker',str(self.root)],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                start_new_session=os.name=='posix',env=env)
            if os.name=='nt':
                from thm.runtime.fabric.resources import ChildBudget
                self.budget=ChildBudget(self.process,memory=2*1024**3,cpu=300,io=2**40)
            self.process.stdin.write(b'go\n');self.process.stdin.flush()
            self._receive(self.root/'ready.json',time.monotonic())
        except Exception:
            self.terminate()
            raise

    def _receive(self,path,start):
        while not path.exists():
            if time.monotonic()-start>=self.timeout:
                self.terminate();raise TimeoutError('storage callback/process deadline')
            if self.process.poll() is not None:
                self.terminate();raise RuntimeError('storage worker exited')
            time.sleep(.005)
        result=json.loads(read_regular(path,maximum_bytes=self.maximum));path.unlink()
        if time.monotonic()-start>=self.timeout:
            self.terminate();raise TimeoutError('storage response deadline')
        if result.get('receipt'):self.receipt=result['receipt']
        if result.get('error'):
            category=result['error']
            error={'ValueError':ValueError,'FileNotFoundError':FileNotFoundError,'PermissionError':PermissionError,
                   'TimeoutError':TimeoutError,'MemoryError':MemoryError,'OSError':OSError,'KeyError':KeyError}.get(category,RuntimeError)
            raise error('storage worker: '+category)
        return decode(result['value'])

    def call(self,operation,*args,**kwargs):
        if self.closed:raise ValueError('storage worker closed')
        self.sequence+=1;name=str(self.sequence)
        start=time.monotonic()
        payload={'operation':operation,'args':[encode(x) for x in args],'kwargs':kwargs}
        raw=json.dumps(payload,allow_nan=False).encode()
        if len(raw)>self.maximum:raise ValueError('storage request frame bound')
        request=self.root/(name+'.request');request.write_bytes(raw)
        try:
            self.process.stdin.write((name+'\n').encode());self.process.stdin.flush()
            return self._receive(self.root/(name+'.response'),start)
        finally:
            request.unlink(missing_ok=True)

    def terminate(self):
        if self.closed:return
        self.closed=True
        try:
            if self.process is not None:
                if os.name=='posix':
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                elif self.budget is not None:self.budget.close()
                elif self.process.poll() is None:
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,timeout=5)
                if self.process.poll() is None:self.process.kill()
                self.process.wait(timeout=5)
                if self.process.stdin:self.process.stdin.close()
        finally:self.directory.cleanup()

    def close(self):
        if not self.closed:
            try:self.call('close')
            finally:self.terminate()


def publish(path,result):
    pending=path.with_suffix('.pending')
    with pending.open('x',encoding='utf-8') as stream:json.dump(result,stream,allow_nan=False)
    os.replace(pending,path)


def main():
    if sys.stdin.buffer.readline(4)!=b'go\n':return 2
    root=Path(sys.argv[1]);backend=None
    try:
        config,definition=pickle.loads(read_regular(root/'configuration.pickle',maximum_bytes=8_000_000))
        from .backends import StorageBackend
        transport=definition() if callable(definition) else definition
        backend=StorageBackend(config,transport,_worker=True)
        publish(root/'ready.json',{'value':encode(None),'receipt':backend.receipt()})
    except Exception as exc:
        publish(root/'ready.json',{'error':type(exc).__name__});return 1
    try:
        for line in sys.stdin.buffer:
            name=line.decode().strip()
            if not name.isdigit() or len(name)>12:return 2
            request=json.loads(read_regular(root/(name+'.request'),maximum_bytes=2*config.max_object_bytes+65536))
            try:
                op=request['operation']
                if op not in ('write','read','verify','recover','receipt','close'):raise ValueError('unknown storage operation')
                args=[decode(v) for v in request['args']]
                if op=='read':
                    from .contracts import TransferExtent
                    args[0]=TransferExtent(**args[0])
                value=getattr(backend,op)(*args,**request['kwargs'])
                response={'value':encode(value),'receipt':backend.receipt()}
            except Exception as exc:response={'error':type(exc).__name__,'receipt':backend.receipt()}
            publish(root/(name+'.response'),response)
            if request['operation']=='close':return 0
    finally:
        if backend.state!='closed':backend.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
