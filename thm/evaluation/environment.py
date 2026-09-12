"""Bounded external environment and official scorer bridges; no built-in LLM."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from .contracts import digest, nonempty


@dataclass(frozen=True)
class EnvironmentIdentity:
    benchmark: str
    environment: str
    implementation_sha256: str
    provenance: str = 'deterministic-fixture'

    def __post_init__(self):
        nonempty(self.benchmark); nonempty(self.environment)
        if self.provenance not in ('deterministic-fixture', 'external-environment'):
            raise ValueError('invalid environment provenance')
        if len(self.implementation_sha256) != 64 or any(c not in '0123456789abcdef' for c in self.implementation_sha256):
            raise ValueError('environment implementation hash required')


class EnvironmentRunner:
    def __init__(self, environment, identity, *, max_steps=32, wall_seconds=30):
        if type(max_steps) is not int or not 1 <= max_steps <= 256 or type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds) or not 0 < wall_seconds <= 300:
            raise ValueError('bounded environment limits required')
        if not isinstance(identity, EnvironmentIdentity):
            raise TypeError('EnvironmentIdentity required')
        for method in ('reset', 'step', 'close'):
            if not callable(environment) and not callable(getattr(environment, method, None)):
                raise TypeError('environment protocol required')
        self.environment, self.identity = environment, identity
        self.max_steps, self.wall_seconds = max_steps, wall_seconds

    def run(self, task, policy, memory=None):
        """Run trusted, pickleable callbacks in an owned, interruptible process.

        `memory`, when supplied, is a pickleable factory for worker-owned memory.
        It is created and closed inside the same boundary as the environment.
        """
        import base64
        import os
        import pickle
        import signal
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        if memory is not None and not callable(memory):
            raise TypeError('worker-owned memory factory required')
        try:
            payload = pickle.dumps((self.environment, self.identity, task, policy, memory, self.max_steps))
        except (TypeError, AttributeError, pickle.PicklingError) as exc:
            raise ValueError('environment/policy/factory must be pickleable top-level definitions') from exc
        if len(payload) > 8_000_000:
            raise ValueError('environment configuration exceeds 8 MB')
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='thm-environment-') as temporary:
            root=Path(temporary); source=root/'configuration.pickle'; output=root/'result.json'
            source.write_bytes(payload)
            env=dict(os.environ)
            env['PYTHONPATH']=os.pathsep.join(str(Path(p).resolve()) for p in sys.path if Path(p or '.').is_dir())
            process=subprocess.Popen([sys.executable,'-m','thm.evaluation.environment_worker',str(source),str(output)],
                stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                start_new_session=os.name=='posix',env=env)
            budget=None
            try:
                if os.name=='nt':
                    from thm.runtime.fabric.resources import ChildBudget
                    budget=ChildBudget(process,memory=1024**3,cpu=self.wall_seconds,io=64*1024**2)
                if time.monotonic()-start >= self.wall_seconds:
                    raise TimeoutError('environment deadline exhausted before callbacks')
                process.stdin.write(b'go\n');process.stdin.close()
                try:
                    code=process.wait(timeout=max(.001,self.wall_seconds-(time.monotonic()-start)))
                except subprocess.TimeoutExpired:
                    raise TimeoutError('environment callback/process deadline') from None
                if not output.is_file() or output.stat().st_size > 6_000_000:
                    raise RuntimeError('environment worker failed or exceeded output bound')
                result=json.loads(output.read_text())
                if code or result.get('error'):
                    raise RuntimeError('environment worker: '+result.get('error','failed'))
                raw=base64.b64decode(result['trace'],validate=True)
                receipt=result['receipt']; checksum=receipt.pop('receipt_sha256',None)
                if checksum != digest(receipt) or receipt['trace_sha256'] != hashlib.sha256(raw).hexdigest():
                    raise ValueError('environment worker receipt corrupt')
                if time.monotonic()-start >= self.wall_seconds:
                    raise TimeoutError('environment result deadline')
                receipt['latency_ms']=(time.monotonic()-start)*1000
                receipt['execution_boundary']='owned-process-tree'
                return {**receipt,'receipt_sha256':digest(receipt)},raw
            finally:
                # Kill helpers even after the leader exits; a hung close is bounded too.
                if os.name=='posix':
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                elif budget is not None:
                    budget.close()
                elif process.poll() is None:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
                if process.poll() is None:process.kill()
                process.wait(timeout=5)
                if process.stdin and not process.stdin.closed:process.stdin.close()


def execute_environment(environment, identity, task, policy, memory_factory, maximum_steps):
    """Trusted worker body. Parent process enforces every callback's deadline."""
    start=time.monotonic();trace=[];memory=None
    definition=environment;environment=None
    try:
        environment=definition() if callable(definition) else definition
        memory=memory_factory() if memory_factory is not None else None
        observation=environment.reset(task.id)
        done,success=False,None
        for ordinal in range(maximum_steps):
            action=policy(task.query,observation,memory)
            result=environment.step(action)
            if not isinstance(result,dict) or type(result.get('done')) is not bool:
                raise ValueError('invalid environment step result')
            observation,done=result.get('observation'),result['done']
            trace.append({'task_id':task.id,'step':ordinal,'action':action,'observation':observation,'done':done})
            if len(json.dumps(trace,ensure_ascii=False,allow_nan=False).encode())>4_000_000:
                raise ValueError('trace exceeds bounded input')
            if memory is not None and isinstance(observation,str) and observation.strip():memory.add(observation)
            if done:
                success=result.get('success')
                if success is not None and type(success) is not bool:raise ValueError('invalid environment success')
                break
        raw=json.dumps(trace,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
        value={'schema':'thm-environment/1','task_id':task.id,'identity':asdict(identity),'steps':len(trace),
               'completed':done,'status':'completed' if done else 'step-limit','environment_success':success,
               'trace_sha256':hashlib.sha256(raw).hexdigest(),'latency_ms':(time.monotonic()-start)*1000,
               'task_outcome_accepted':False,'environment_closed':True}
        return {**value,'receipt_sha256':digest(value)},raw
    finally:
        try:
            if environment is not None:environment.close()
        finally:
            if memory is not None:memory.close()


class OfficialScorerBridge:
    """Explicit callback for an installed official scorer; gold never enters memory."""
    def __init__(self, scorer, *, evaluator_id, implementation_sha256):
        if not callable(scorer):
            raise TypeError('explicit scorer callback required')
        self.scorer, self.evaluator_id = scorer, nonempty(evaluator_id)
        self.implementation_sha256 = implementation_sha256
        EnvironmentIdentity('scorer', self.evaluator_id, implementation_sha256)

    def score(self, task, ground_truth, answer, *, trace_sha256):
        if task.id != ground_truth.task_id:
            raise ValueError('scorer task/gold identity mismatch')
        if len(trace_sha256) != 64 or any(c not in '0123456789abcdef' for c in trace_sha256):
            raise ValueError('trace identity required')
        score = self.scorer(answer=answer, ground_truth=ground_truth.answer, rubric=ground_truth.rubric)
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('official scorer returned invalid score')
        return {'task_id': task.id, 'evaluator_id': self.evaluator_id, 'implementation_sha256': self.implementation_sha256,
                'trace_sha256': trace_sha256, 'answer_accuracy': score, 'independently_certified': False}
