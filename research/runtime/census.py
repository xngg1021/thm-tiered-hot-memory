"""Exact encoder-input reuse census, without estimating hardware speedup."""
import hashlib
import json
from pathlib import Path
from thm.retrieval import TokenCounter
from research.recall.lme_retrieval import messages_of


def census(dataset,counter=None):
    counter=counter or TokenCounter();seen=set();total=0;duplicate=0;avoided_bytes=0;avoided_units=0;instances=[]
    for instance in dataset:
        n=0;reused=0
        for _,text,_,speaker in messages_of(instance):
            encoder_input=f'{speaker}: {text}';raw=encoder_input.encode('utf-8');key=hashlib.sha256(raw).hexdigest();total+=1;n+=1
            if key in seen:duplicate+=1;reused+=1;avoided_bytes+=len(raw);avoided_units+=counter(encoder_input)
            seen.add(key)
        instances.append({'instance_ordinal':len(instances),'inputs':n,'reused_exact_inputs':reused})
    return {'schema':1,'total_encoder_inputs':total,'unique_exact_encoder_inputs':len(seen),'duplicate_count':duplicate,
        'duplicate_percentage':100*duplicate/total if total else 0,'bytes_avoided':avoided_bytes,'counter_units_avoided':avoided_units,
        'counter':counter.name,'reuse_opportunity_by_instance':instances,'speedup':None,'generation_calls':0}
