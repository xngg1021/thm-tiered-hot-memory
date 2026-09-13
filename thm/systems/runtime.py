"""Optional product integration over the existing THM RuntimeService."""
import threading
import time
import uuid
from .concurrency import ElasticConcurrencyController, WorkItem
from .contracts import digest
from .native import psi_snapshot
from .syscore import SysCore
from .topology import DynamicTopologyFabric, TopologyEvent
from .thermal import LinuxThermalPowerProvider


class AgentSystemsRuntime:
    """One owned host session. Source authority remains the underlying harness."""
    def __init__(self, runtime, *, syscore=None, topology=None, thermal=None):
        self.base=runtime
        self.syscore=syscore or SysCore()
        self.topology=topology or DynamicTopologyFabric()
        self.thermal=thermal
        self.controller=ElasticConcurrencyController(concurrency=1,worker_count=1,batch_size=1)
        self.lock=threading.RLock()
        self.closed=False
        self.session=uuid.uuid4().hex
        self.topology.open_session(self.session)
        self.sequence=0
        self.last={}
        self.samples=[]

    def event(self, event):
        # Epoch changes can be observed even while an in-flight search is running.
        with self.topology._lock:
            snapshot=self.topology.event(event)
            self.base.topology_epoch=snapshot['topology_epoch']
            return snapshot

    def search(self, scope, query, *, workload='interactive', **settings):
        with self.lock:
            if self.closed:
                raise RuntimeError('agent systems runtime closed')
            self.sequence+=1
            identity=f'{self.session}:{self.sequence}'
            arrived=time.monotonic()
            item=WorkItem(identity,self.session,workload,arrived,arrived+30)
            if not self.controller.submit(item,arrived):
                raise OverflowError('agent admission queue full')
            batch=self.controller.dispatch(arrived)
            if not batch:
                self.controller.queues[workload].remove(item)
                self.controller.known.remove(identity)
                raise RuntimeError('background work deferred by pressure policy')
            epoch=self.topology.epoch
            try:
                if self.thermal is not None:
                    try:
                        self.samples.append(self.thermal.sample())
                        self.samples=self.samples[-16:]
                    except (OSError,RuntimeError,ValueError):
                        self.samples=[]
                pressure=psi_snapshot()
                stalls={name:(value['rows'].get('some',{}).get('avg10',0)/100 if value['rows'] else None)
                        for name,value in pressure['resources'].items()}
                control=self.controller.feedback(self.samples,stalls,now=time.monotonic())
                result=self.base.search(scope,query,workload=workload,**settings)
                # Linearize epoch validation, fallback and publication against events.
                with self.topology._lock:
                    fallback=None
                    if self.topology.epoch!=epoch:
                        # Discard stale provider output, close device-bound state and
                        # rebuild from the source index in the reference sparse path.
                        with self.base.lock,self.base.index._lock:
                            for executor in self.base.executors.values():
                                executor.close()
                            self.base.executors.clear()
                            self.base.pinned.clear()
                            self.base.index._vector_executor=None
                            self.base.index._results.clear()
                            effective={k:v for k,v in settings.items() if k not in ('mode','encoder','model_id','scorer','deadline')}
                            result=self.base.index.search(scope,query,mode='sparse',**effective)
                        fallback='topology-epoch-changed'
                    finish=time.monotonic()
                    self.controller.complete(identity,finish)
                    self.last={'schema':'thm-agent-runtime/1','program':self.session,'trajectory':identity,
                        'session':self.session,'topology':self.topology.snapshot(),'topology_epoch':self.topology.epoch,
                        'thermal_power':[sample.public() for sample in self.samples], 'pressure':pressure,
                        'queue':self.controller.receipt(),'native_path':dict(self.syscore.last),
                        'fallback':fallback,'task_completion_time':finish-arrived,
                        'TUFR':None,'TUFR_reason':'host must mark useful output',
                        'source_memory_mutation':False,'evidence':'systems-runtime'}
                    result['systems_receipt']=dict(self.last)
                    return result
            except BaseException:
                if identity in self.controller.active:
                    self.controller.complete(identity,time.monotonic(),failed=True)
                raise

    def mark_useful_output(self, timestamp_from_submit):
        from .contracts import finite
        finite(timestamp_from_submit)
        self.last['TUFR']=timestamp_from_submit
        self.last['TUFR_reason']='explicit-host-useful-output-marker'

    def new_session(self):
        with self.lock:
            self.topology.close_session(self.session)
            self.session=uuid.uuid4().hex
            self.topology.open_session(self.session)
            return {**self.base.new_session(),'agent_session':self.session,'topology_epoch':self.topology.epoch}

    def status(self):
        return {**self.base.status(),'systems':dict(self.last),'syscore':self.syscore.capabilities()}

    def close(self):
        with self.lock:
            if not self.closed:
                self.base.close()
                self.topology.close_session(self.session)
                if self.thermal is not None:
                    self.thermal.close()
                self.closed=True
