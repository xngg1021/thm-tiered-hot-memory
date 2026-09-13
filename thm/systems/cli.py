"""Bounded agent systems smoke, observability and trace replay CLI."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
import tempfile
import time
from .contracts import atomic_json, digest
from .topology import DynamicTopologyFabric, TopologyEvent
from .syscore import SysCore
from .thermal import LinuxThermalPowerProvider
from .native import psi_snapshot, apple_observations
from .simulator import AgentSystemsSimulator, AgentTaskTrace
from thm.reliability import accelerated_life


def reliability_smoke(*, events=128, seed=0, full_research=False):
    """Exercise actual state/source checks under deterministic fault injection."""
    fabric=DynamicTopologyFabric(); sequence=0
    def workload(fault,index,rng):
        nonlocal sequence
        from thm.reliability.faults import publication_fault, worker_fault, byte_identity_fault
        if fault in ('short-write','disk-full'):
            return publication_fault(fault)
        if fault in ('provider-crash','worker-hang'):
            return worker_fault(fault)
        if fault in ('corruption','source-mutation','storage-disappearance'):
            return byte_identity_fault(fault)
        if fault in ('stale-profile','clock-jump'):
            from .contracts import ProfileStamp
            profile=ProfileStamp('provider',1,1,'driver',10,5)
            accepted=profile.fresh(9 if fault=='clock-jump' else 20,1,1,'driver')
            return {'recovered':not accepted,'mechanism':fault,'stale_profile_rejected':not accepted}
        if fault=='out-of-order-events':
            fresh=DynamicTopologyFabric(); fresh.event(TopologyEvent('wake','cpu',1))
            try:
                fresh.event(TopologyEvent('wake','cpu',0))
            except ValueError:
                return {'recovered':True,'mechanism':fault,'old_event_rejected':True}
            return {'recovered':False,'class':'F0'}
        sequence+=1
        fabric.event(TopologyEvent('gpu-appeared','fixture-device',sequence,f'driver-{index}'))
        device=fabric.devices['fixture-device']
        fabric.qualify(device.identity,device.generation,device.fingerprint,passed=True)
        session=f'session-{index}'; fabric.open_session(session,device.identity)
        handle=fabric.admit(session,'source-authority','derived-index')
        sequence+=1
        fabric.event(TopologyEvent('gpu-lost' if fault!='sleep-wake' else 'sleep',device.identity,sequence))
        stale_rejected=False
        try:
            fabric.validate(handle)
        except ValueError:
            stale_rejected=True
        fallback=fabric.admit(session,'source-authority','derived-index') is None
        fabric.close_session(session)
        return {'recovered':stale_rejected and fallback,'stale_handle_rejected':stale_rejected,
                'source_locator_preserved':handle.source_identity=='source-authority',
                'injected_mechanism':'topology loss while '+fault,'recovery_seconds':None}
    report=accelerated_life(workload,events=events,seed=seed,full_research=full_research)
    report['fault_coverage_scope']='real publication and byte identity rejection; contained crash/hang; topology/generation/session/migration/profile transitions'
    return report


def smoke():
    from thm.retrieval import SearchIndex, Document
    from thm.harness import HarnessConfig, THMHarnessAdapter
    from thm.evaluation.adapters import ADAPTERS
    from thm.evaluation.fixtures import FIXTURES
    from thm.evaluation.runner import run
    with tempfile.TemporaryDirectory(prefix='thm-systems-smoke-') as directory:
        root=Path(directory); db=root/'memory.sqlite'
        index=SearchIndex(db)
        try:
            index.replace_scope('s',[Document('fact','s','session',0,'The launch code is cobalt.',source='source-authority')])
        finally:
            index.close()
        with THMHarnessAdapter(HarnessConfig(str(db),'s',systems=True,long_tail=True)) as adapter:
            first=adapter.recall('launch code')
            if 'cobalt' not in first['context']:
                raise ValueError('systems integration lost source evidence')
            adapter.new_session(); second=adapter.recall('launch code')
            if first['sources']!=second['sources']:
                raise ValueError('session transition changed source evidence')
        baseline=run(ADAPTERS['locomo'],FIXTURES['locomo'],root/'baseline',provenance='deterministic-fixture',ceiling=True)
        candidate=run(ADAPTERS['locomo'],FIXTURES['locomo'],root/'candidate',provenance='deterministic-fixture',long_tail=True,ceiling=True)
    trace=AgentTaskTrace('t1','user','session',0,.01,.01,.02,.03,.04,.01,'prefix')
    ladder=AgentSystemsSimulator().ablation_ladder((trace,replace(trace,task_id='t2',arrival=1)))
    reliability=reliability_smoke(events=32)
    if reliability['invariant_failures']:
        raise ValueError('reliability invariant failure')
    return {'schema':'thm-systems-smoke/1','status':'passed','systems_receipt':second['systems_receipt'],
            'baseline':baseline,'candidate':candidate,'ablation_ladder':ladder,
            'reliability':reliability,'generation_calls':0,'judge_calls':0,
            'hardware_acceptance':False,'source_authority':'unchanged'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('smoke','reliability','observe','replay'))
    p.add_argument('--output');p.add_argument('--trace');p.add_argument('--full-research',action='store_true')
    p.add_argument('--events',type=int,default=128);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--syscore-executable')
    args=p.parse_args(argv)
    if args.command=='smoke':
        result=smoke()
    elif args.command=='reliability':
        result=reliability_smoke(events=args.events,seed=args.seed,full_research=args.full_research)
    elif args.command=='observe':
        result={'schema':'thm-native-observation/1','platform':platform.platform(),
                'syscore':SysCore(args.syscore_executable).capabilities(),'psi':psi_snapshot(),
                'thermal':[s.public() for s in LinuxThermalPowerProvider().samples()] if platform.system()=='Linux' else [],
                'apple':apple_observations(),'hardware_acceptance':False}
    else:
        if not args.trace:
            p.error('replay requires a trace file')
        from thm._bounded_files import bounded_file_bytes
        value=json.loads(bounded_file_bytes(args.trace,1048576 if not args.full_research else 128*1048576))
        tasks=tuple(AgentTaskTrace(**row) for row in value['tasks'])
        result=AgentSystemsSimulator(concurrency=value.get('concurrency',2),
            topology_events=value.get('topology_events',()),thermal_trace=value.get('thermal_trace',())).replay(
                tasks,ablation=value.get('ablation',0),full_research=args.full_research)
    if args.output:
        atomic_json(args.output,result)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
