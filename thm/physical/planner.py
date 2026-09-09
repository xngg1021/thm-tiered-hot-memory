"""Constraint admission precedes measured single-objective ordering."""
from dataclasses import asdict
import math
from .contracts import DataRole


def plan(intent, targets, profiles):
    profiles={p.target_fingerprint:p for p in profiles}
    admitted=[];rejected=[]
    for t in sorted(targets,key=lambda t:t.target_id):
        reasons=[];profile=profiles.get(t.fingerprint);cost=None
        if t.adapter!='local-filesystem':reasons.append('adapter-unavailable')
        if intent.local_only and t.remote is not False:reasons.append('locality-unverified')
        if t.readonly is not False:reasons.append('placement-requires-verified-writable-target')
        if t.free_capacity is None or t.free_capacity<intent.capacity_required:reasons.append('capacity')
        if intent.minimum_replicas is not None and (t.replication is None or t.replication<intent.minimum_replicas):reasons.append('durability-unverified')
        if intent.failure_domain is not None and t.failure_domain!=intent.failure_domain:reasons.append('failure-domain')
        if profile:
            matching=[c for c in profile.costs if (c.get('operation'),c.get('size'),c.get('concurrency'))==(intent.operation,intent.transfer_size,intent.concurrency)]
            if matching:cost=matching[0]
        if cost is None or any(not isinstance(cost.get(k),(int,float)) or not math.isfinite(cost[k]) or cost[k]<=0 for k in ('p95_ms','bytes_per_second')):
            reasons.append('required-cost-unmeasured')
        elif intent.p95_latency_ms is not None and cost['p95_ms']>intent.p95_latency_ms:reasons.append('latency-slo')
        if intent.max_write_amplification is not None:
            if not cost or cost.get('write_amplification') is None or cost['write_amplification']>intent.max_write_amplification:reasons.append('write-amplification-unmeasured')
        if intent.workload=='archive':reasons.append('capacity-cost-unmeasured')
        if reasons:rejected.append({'target_id':t.target_id,'reasons':reasons})
        else:admitted.append((cost['p95_ms'] if intent.workload=='interactive' else -cost['bytes_per_second'],t.target_id,profile.id))
    admitted.sort()
    return {'schema':1,'mode':'shadow-recommendation','intent':asdict(intent),
        'selected_target':admitted[0][1] if admitted else None,
        'storage_profile_id':admitted[0][2] if admitted else None,'rejected':rejected,
        'ordering':'measured-latency' if intent.workload=='interactive' else 'measured-throughput',
        'semantic_mutation':False,'automatic_relocation':False}
