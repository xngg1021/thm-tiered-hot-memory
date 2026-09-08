"""Persistent local encoder worker; shutdown/timeout never leaves a child running."""
import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from .identity import EmbeddingProfile, bounded_int


class IsolatedEncoder:
    def __init__(self,config,timeout=120):
        self.timeout=timeout;self.config=dict(config);self.model_id=config['model_id']
        self.document_batch_size=bounded_int(config.get('document_batch_size',64),'document batch',256)
        self.query_batch_size=bounded_int(config.get('query_batch_size',32),'query batch',256)
        self.batch_size=self.document_batch_size;self.device=config['device'];self.lock=threading.RLock()
        self.temp=tempfile.TemporaryDirectory();path=Path(self.temp.name)/'config.json';path.write_text(json.dumps(config))
        self.process=subprocess.Popen([sys.executable,'-m','thm.runtime.worker','serve',str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.queue=queue.Queue();self.worker_wall_ms=0.0;self.worker_cpu_ms=0.0
        self.reader=threading.Thread(target=self._read,name='thm-worker-reader',daemon=True);self.reader.start()
        try:
            handshake=self._receive();identity=handshake['identity'];self._identity=identity
            self._runtime_execution=handshake['runtime_execution']
            fields={k:v for k,v in identity.items() if k in EmbeddingProfile.__dataclass_fields__}
            self.profile=EmbeddingProfile(**fields)
            if self.profile.id!=identity['embedding_profile_id']:raise ValueError('worker identity mismatch')
        except Exception:self.close();raise
    def _read(self):
        try:
            for line in self.process.stdout:self.queue.put(line)
        finally:self.queue.put(None)
    def _receive(self):
        try:line=self.queue.get(timeout=self.timeout)
        except queue.Empty:self.close();raise TimeoutError('encoder worker timed out')
        if line is None:raise RuntimeError('encoder worker exited')
        return json.loads(line)
    def identity(self):return self._identity
    def runtime_identity(self):return dict(self._runtime_execution)
    def capabilities(self):return {'isolated':True,'encode_many':True,'observed_kernel_dispatch':None}
    def encode_many(self,texts):
        with self.lock:
            if self.process.poll() is not None:raise RuntimeError('encoder closed')
            self.process.stdin.write(json.dumps({'texts':list(texts)},ensure_ascii=True)+'\n');self.process.stdin.flush()
            result=self._receive();self.worker_wall_ms+=result.get('worker_wall_ms',0);self.worker_cpu_ms+=result.get('worker_cpu_ms',0)
            return result['vectors']
    def encode_one(self,text):return self.encode_many([text])[0]
    def __call__(self,texts):return self.encode_many(texts)
    def close(self):
        with self.lock:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            if threading.current_thread()!=self.reader:self.reader.join(timeout=5)
            for stream in (self.process.stdin,self.process.stdout):
                if stream:stream.close()
            self.temp.cleanup()
