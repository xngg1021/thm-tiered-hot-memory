#!/usr/bin/env python3
"""Chronological residency-policy experiment. Default data are SYNTHETIC.

No QA order is interpreted as a use history. The chosen policy is selected on
first-half requests, evaluated on the second half, and is never auto-installed.
"""
from __future__ import annotations
import argparse
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import random
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from thm.policy import Policy, plan, curve_report


def synthetic(seed=711, days=360):
    rng=random.Random(seed)
    start=date(2025,1,1)
    entries=[{'id':f'e{i}', 'status':'active', 'pinned':False, 'cost_class':'med',
              'units':20+(i%5)*10, 'events':[]} for i in range(60)]
    events=[]
    for day in range(days):
        # Stable, weekly and shifting task groups. No claim of resemblance to a user.
        for _ in range(4):
            u=rng.random()
            if u<.35: target=rng.randrange(8)
            elif u<.50: target=8+(day%7)
            elif u<.9: target=15+((day//60)%3)*15+rng.randrange(15)
            else: target=rng.randrange(60)
            events.append({'id':f'e{target}','t':(start+timedelta(days=day)).isoformat()})
    return {'entries':entries,'events':events,'source':'synthetic-regime-switch-v1','seed':seed}


def evaluate(data,policy,budget):
    entries=copy.deepcopy(data['entries']); indexed={e['id']:e for e in entries}
    events=data['events']; split=len(events)//2; buckets=[[0,0],[0,0]]; timings=[]
    previous=None
    for n,event in enumerate(events):
        now=date.fromisoformat(event['t'])
        if previous and now<previous: raise ValueError('nonchronological events')
        previous=now
        start=time.perf_counter(); result=plan(entries,now,budget,policy,lambda e:e['units'])
        timings.append((time.perf_counter()-start)*1000)
        bucket=buckets[int(n>=split)]; bucket[1]+=1
        bucket[0]+=event['id'] in result['selected']
        indexed[event['id']]['events'].append({'event_id':f'use:{n}','type':'hit','t':event['t']})
    return {'development_hit_rate':buckets[0][0]/buckets[0][1],
            'heldout_hit_rate':buckets[1][0]/buckets[1][1], 'requests':len(events),
            'plan_p95_ms':sorted(timings)[int(.95*(len(timings)-1))]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input');parser.add_argument('--output',required=True)
    parser.add_argument('--budget',type=int,default=600)
    parser.add_argument('--sweep',action='store_true')
    args=parser.parse_args()
    data=json.loads(Path(args.input).read_text()) if args.input else synthetic()
    policies={k:Policy(kernel=k) for k in ('lru','lfu','legacy','power','exponential','mixture','bounded_power')}
    if args.sweep:
        policies.update({f'{k}@{h}d':Policy(kernel=k,half_life=h)
                         for k in ('power','exponential','bounded_power') for h in (3,7,14,60,90)})
    scores={name:evaluate(data,p,args.budget) for name,p in policies.items()}
    best=max(sorted(scores),key=lambda name:scores[name]['development_hit_rate'])
    result={'data_source':data.get('source','user_supplied_chronology'),'budget':args.budget,
            'scores':scores,'selected_on_development':best,
            'selected_heldout_result':scores[best]['heldout_hit_rate'],
            'policy_installed':False,'curve_report':curve_report(),
            'notes':['Residency hit rate, not answer accuracy or retrieval recall.',
                     'Default trace is synthetic; it cannot validate a real user optimal half-life.',
                     'All policies share the same budgets, events, source records and chronological split.']}
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print('THM_DECAY_SUMMARY_BEGIN'); print(json.dumps(result,indent=2));print('THM_DECAY_SUMMARY_END')

if __name__=='__main__': main()
