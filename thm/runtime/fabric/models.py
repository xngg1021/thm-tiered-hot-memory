"""Bounded background model preparation with a retained isolated warm worker."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from .contracts import identity
from .explorer import BoundedShadowExplorer
from .optimizer import Candidate, MaterialGainGate, SemanticGuard, percentile
from .resources import ChildBudget


class WarmModelWorker:
    def __init__(self, task, *, memory, cpu, io, wall):
        self.task = dict(task); self.memory = memory; self.cpu = cpu; self.io = io; self.wall = wall
        self.process = None; self.budget = None; self.reader = None; self.closed = False; self.preempted = False
        self.responses = queue.Queue(maxsize=2); self.lock = threading.RLock()
        self.workspace = tempfile.TemporaryDirectory(prefix='thm-model-')
        self.task['workspace'] = self.workspace.name
        self.task['memory_budget'] = memory

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(4*1024*1024+1)
                if not line:
                    break
                if len(line) > 4*1024*1024 or not line.endswith('\n'):
                    raise ValueError('bounded model response exceeded')
                self.responses.put_nowait(json.loads(line))
        except Exception:
            pass
        finally:
            try:
                self.responses.put_nowait({'status':'failed','error':'worker-exited'})
            except queue.Full:
                pass

    def _receive(self, wall):
        started = time.monotonic()
        while not self.closed and time.monotonic()-started < wall:
            self.budget.check()
            try:
                result = self.responses.get(timeout=min(.05, wall))
            except queue.Empty:
                continue
            if result.get('status') == 'failed':
                raise RuntimeError('model worker failed: '+result['error'])
            return result
        raise TimeoutError('bounded model operation deferred')

    def _send(self, value):
        data = json.dumps(value, ensure_ascii=True, allow_nan=False)+'\n'
        if len(data) > 2*1024*1024:
            raise ValueError('bounded model input exceeded')
        self.process.stdin.write(data); self.process.stdin.flush()

    def prepare(self):
        env = dict(os.environ)
        env.update(OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
        with self.lock:
            if self.closed:
                raise RuntimeError('model worker closed')
            self.process = subprocess.Popen([sys.executable,'-m','thm.runtime.fabric.model_worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', env=env, start_new_session=os.name == 'posix')
            self.budget = ChildBudget(self.process, memory=self.memory, cpu=self.cpu, io=self.io)
            self.reader = threading.Thread(target=self._read, name='thm-model-reader', daemon=True)
            self.reader.start(); self._send(self.task)
        return self._receive(self.wall)

    def search(self, queries, generation):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError('prepared model unavailable')
            self.budget.renew(cpu=5, io=self.io)
            self._send({'queries':queries,'generation':generation})
            return self._receive(10)

    def close(self):
        with self.lock:
            self.closed = True
            if self.process:
                # The same process-tree lifecycle is used for discovery and serving.
                BoundedShadowExplorer._kill(self, self.process)
                self.process.wait(timeout=5)
            if self.budget:
                self.budget.close(); self.budget = None
        if self.reader and threading.current_thread() != self.reader:
            self.reader.join(timeout=5)
        if self.process:
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        self.workspace.cleanup()


class ModelPortfolio:
    def __init__(self, service):
        self.service = service; self.providers = {}; self.ready = None; self.active = None
        self.preparing = None; self.thread = None; self.closed = False; self.lock = threading.RLock()
        self.last = {'status':'reference'}; self.cursor = 0

    def add(self, name, description, observed):
        if (name != 'cpu.inference' and observed.get('availability') == 'available'
                and description['factory'].endswith(('inference:TorchInference','inference:OrtInference','inference:OpenVINOInference'))):
            self.providers[name] = description

    def source(self):
        encoder = self.service.encoder
        return getattr(encoder, 'local_model_source', None) or getattr(encoder, 'config', {}).get('model_path')

    def maybe_start(self, key, task):
        service = self.service; source = self.source(); profile = getattr(service.encoder, 'profile', None)
        if not source or not profile or profile.backend != 'torch_fp32' or not self.providers:
            return False
        stale = None
        with self.lock:
            if self.ready and self.ready[1].task.get('scope') == task.get('scope') and self.ready[0] != key.id:
                stale = self.ready[1]; self.ready = None; self.active = None
        if stale:
            stale.close()
        with self.lock:
            if self.closed or self.preparing or self.ready or not service.explorer.eligible():
                return False
            names = sorted(self.providers); name = names[self.cursor % len(names)]; self.cursor += 1
            if service.store.quarantined(key, name):
                return False
            service.explorer.last_started = service.explorer.clock()
            options = dict(self.providers[name]['options'])
            device = 'cpu' if options.get('ep') == 'CPUExecutionProvider' else options.get('device', 'provider-managed').lower()
            candidate = Candidate('host.exact', inference_provider=name, workload=key.workload,
                device=device,
                parameters=(('model-source',profile.source_manifest_sha256),))
            native = sys.modules.get('torch')
            reference_threads = getattr(service.encoder, 'threads', None)
            if reference_threads is None and native and hasattr(native, 'get_num_threads'):
                reference_threads = native.get_num_threads()
            task = {**task, 'model_source':source, 'model_id':service.model_id,
                    'inference_provider':name, 'reference_profile':asdict(profile),
                    'reference_threads':max(1,min(256,reference_threads or 1))}
            worker = WarmModelWorker(task, memory=service.memory_budget+128*1024**2,
                cpu=service.explorer.cpu, io=service.explorer.io, wall=service.explorer.wall)
            self.preparing = worker
            self.thread = threading.Thread(target=self._prepare, args=(worker,key,candidate),
                                           name='thm-model-prepare', daemon=True)
            self.thread.start()
            return True

    def _prepare(self, worker, key, candidate):
        keep = False
        try:
            result = worker.prepare()
            if result.get('generation') != worker.task['generation']:
                raise ValueError('model snapshot changed')
            semantic = SemanticGuard.compare(result['reference'],result['result'],dimension=key.dimension)['semantic_admission'] and result.get('all_repeats_consistent',True)
            import statistics
            candidate_cpu = statistics.median(result['cpu_samples']['candidate'])
            baseline_cpu = statistics.median(result['cpu_samples']['baseline'])
            ram = worker.budget.last.get('ram_bytes')
            limits = {'ram':worker.memory,'cpu':max(baseline_cpu*1.25,baseline_cpu+.001)}
            if candidate.device != 'cpu':
                limits['vram'] = worker.memory
            gain = MaterialGainGate().evaluate(result['baseline'],result['candidate'],semantic=semantic,
                resources={'ram':ram,'cpu':candidate_cpu,'vram':result.get('vram_bytes')},limits=limits)
            values = result['candidate']
            measurement = {'p50':statistics.median(values),'p95':percentile(values,.95),'p99':percentile(values,.99),
                'throughput':1000/statistics.median(values),'startup':result['startup_ms'],
                'cpu_seconds':candidate_cpu,'ram':ram,'vram':result.get('vram_bytes'),'sample_count':len(values),'noise':gain.get('noise_floor',0)}
            # A paired replay over one observed query is useful evidence but it is
            # not a global equivalence certificate for an alternate embedding
            # implementation. Default auto-safe therefore records the point but
            # cannot promote it. Performance policies may explicitly accept this
            # observed-request scope; reference/auto-safe stay on the authority
            # embedding path until a stronger provider-wide certificate exists.
            activation_allowed = self.service.policy in ('auto-throughput','approximate-performance')
            with self.lock:
                if self.closed or worker.preempted:
                    return
                self.service.store.put(key,candidate.id,measurement,semantic_status='strict' if semantic else 'rejected',
                    material_gain=gain['decision'],pareto=gain['materially_faster'],
                    evidence={'sample_kind':'observed-end-to-end','semantic_scope':'observed-request-only'})
                promoted = bool(gain['materially_faster'] and activation_allowed)
                self.last = {'status':'ready' if promoted else 'measured-only' if gain['materially_faster'] else 'retain-reference',
                    'inference_provider':candidate.inference_provider,'generation_calls':0,
                    'embedding_profile':result['embedding_profile']['embedding_profile_id'],
                    'sample_kind':'observed-end-to-end','semantic_scope':'observed-request-only',
                    'automatic_activation_allowed':activation_allowed,'gain':gain}
                if promoted:
                    self.ready = (key.id,worker,candidate,result); keep = True
                elif not semantic:
                    self.service.store.failure(key,candidate.inference_provider,'semantic')
        except Exception as exc:
            with self.lock:
                if not self.closed:
                    self.last = {'status':'deferred','reason':'foreground-pressure' if worker.preempted else type(exc).__name__,'inference_provider':candidate.inference_provider}
                    if not worker.preempted:
                        self.service.store.failure(key,candidate.inference_provider,'compile')
        finally:
            if not keep:
                worker.close()
            with self.lock:
                self.preparing = None

    def preempt(self):
        with self.lock:
            worker = self.preparing
            if worker is None or worker.preempted:
                return
            worker.preempted = True
        threading.Thread(target=worker.close,name='thm-model-preempt',daemon=True).start()

    def new_session(self):
        with self.lock:
            self.active = self.ready

    def select(self, key):
        with self.lock:
            if self.active and self.active[0] == key.id:
                return self.active
            return None

    def fail(self, key, candidate):
        with self.lock:
            point = self.active; self.active = None; self.ready = None
            self.service.store.failure(key,candidate.inference_provider,'execution')
            self.last = {'status':'fallback','inference_provider':candidate.inference_provider}
        if point:
            point[1].close()

    def close(self):
        with self.lock:
            self.closed = True
            workers = [p[1] for p in (self.ready,self.active) if p]
            if self.preparing:
                workers.append(self.preparing)
        for worker in set(workers):
            worker.close()
        if self.thread and threading.current_thread() != self.thread:
            self.thread.join(timeout=self.service.explorer.wall+6)
