#!/usr/bin/env python3
"""Read-only-to-source audit of the THM public engine at 4e9b5d8.

Uses exact source bytes, temporary synthetic memory stores and a fixed clock.
It does not access real Hermes memory, install plugins, contact a model, or
modify a checkout. CONFIRMED means a diagnostic reproduced, not a healthy test.
Usage: python reproduce_public_engine_findings.py --engine /repo/scripts/thm.py
"""
from __future__ import annotations
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

EXPECTED_BLOB = '36e8a5af570c644d55ecee1f7577aaac53c95c0b'
TARGET_COMMIT = '4e9b5d8ed5a05c9a538f385acc8632e641ae5908'
FIXED_DATE = datetime.date(2026, 9, 6)


def capture(fn, *args):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            result = fn(*args)
        return out.getvalue(), result, None
    except Exception as exc:
        return out.getvalue(), None, {'type': type(exc).__name__, 'message': str(exc)}


def row(identifier='e001', key='alpha-record', summary='Synthetic alpha setting', **extra):
    result = {'id': identifier, 'key': key, 'summary': summary, 'store': 'MEMORY.md',
              'tier': 'T0', 'created': '2026-09-06', 'cost_class': 'med',
              'events': [{'t': '2026-09-06', 'type': 'create'}],
              'review_stage': 0, 'next_review': '2026-09-09'}
    result.update(extra)
    return result


def run(engine_path: Path):
    source = engine_path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
    if blob != EXPECTED_BLOB:
        raise ValueError(f'Expected reviewed Git blob {EXPECTED_BLOB}, received {blob}. '
                         'Do not apply these observations to a different source revision.')
    observations = []

    def probe(name, operation):
        with tempfile.TemporaryDirectory(prefix='thm-synthetic-review-') as tmp:
            root = Path(tmp); scripts = root / 'scripts'; scripts.mkdir()
            script = scripts / 'thm.py'; script.write_bytes(source)
            mem = root / 'synthetic-profile-A'; mem.mkdir()
            (mem/'MEMORY.md').write_text('', encoding='utf-8')
            (mem/'USER.md').write_text('', encoding='utf-8')
            with patch.dict(os.environ, {'THM_MEM_DIR': str(mem)}):
                spec = importlib.util.spec_from_file_location('reviewed_thm', script)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                module.today = lambda: FIXED_DATE
                try:
                    details = operation(module, root, mem, script)
                    observations.append({'case': name, 'diagnostic': 'CONFIRMED', **details})
                except Exception as exc:
                    observations.append({'case': name, 'diagnostic': 'PROBE_ERROR',
                                         'type': type(exc).__name__, 'message': str(exc)})

    def tie(e, root, mem, script):
        es = [row(f'e{i:03}', f'key-{i}', 'Identical synthetic summary') for i in range(1,4)]
        e.save_index({'version': 1, 'entries': es})
        (mem/'MEMORY.md').write_text('\n§\n'.join(x['key'] for x in es), encoding='utf-8')
        out, _, err = capture(e.cmd_audit)
        assert err and err['type'] == 'TypeError' and 'dict' in err['message']
        return {'expected': 'Audit sorts equal scores deterministically without comparing dictionaries',
                'observed': err, 'crashes_before_sorting_report': '── T0 排序' not in out}
    probe('audit_equal_similarity_crashes', tie)

    def collision(e, root, mem, script):
        prefix='a'*24
        (mem/'MEMORY.md').write_text(prefix+' production = enabled\n', encoding='utf-8')
        (mem/'USER.md').write_text(prefix+' testing = disabled\n', encoding='utf-8')
        out,_,err=capture(e.cmd_seed); assert not err
        data=e.load_index(); assert len(data['entries'])==1
        return {'source_entries':2,'registered_entries':1,'shared_prefix_length':24,
                'observed':out.strip(),'surviving_store':data['entries'][0]['store']}
    probe('seed_prefix_collision_across_stores', collision)

    def scope(e, root, mem, script):
        (mem/'MEMORY.md').write_text('ALPHA_ONLY setting enabled\n', encoding='utf-8')
        assert capture(e.cmd_seed)[2] is None
        b=root/'synthetic-profile-B'; b.mkdir()
        (b/'MEMORY.md').write_text('BETA_ONLY other setting\n', encoding='utf-8')
        (b/'USER.md').write_text('', encoding='utf-8')
        old_index=e.INDEX
        with patch.dict(os.environ, {'THM_MEM_DIR': str(b)}):
            e.MEM_DIR=e._resolve_mem_dir()
            assert capture(e.cmd_seed)[2] is None
            out,_,err=capture(e.cmd_hit, 'ALPHA_ONLY', 'synthetic profile-B request')
        assert not err
        data=e.load_index(); alpha=next(x for x in data['entries'] if 'ALPHA_ONLY' in x['key'])
        assert len(alpha['events'])==2 and e.INDEX==old_index and len(data['entries'])==2
        return {'profile_B_source_contains_alpha':False,'shared_index':True,
                'index_entry_count':2,'profile_A_entry_event_count_after_B_hit':2,'observed':out.strip()}
    probe('changing_memory_directory_does_not_isolate_index', scope)

    def dates(e, root, mem, script):
        values={d:{'age_days':e.days_since(d),'score':e.activation({'events':[{'type':'hit','t':d}]})}
                for d in ('not-a-date', '9999-12-31', '2026-09-06')}
        assert all(x['age_days']==0 and x['score']==2.0 for x in values.values())
        return {'observed':values,'expected':'Invalid/future timestamps are rejected or quarantined, not assigned maximum recency'}
    probe('invalid_and_future_dates_are_fresh', dates)

    def dedup(e, root, mem, script):
        e.save_index({'version':1,'entries':[row()]})
        for _ in range(2): assert capture(e.cmd_hit,'alpha-record','same retried request')[2] is None
        entry=e.load_index()['entries'][0]
        assert len(entry['events'])==3 and e.activation(entry)==5.0
        return {'identical_hit_calls':2,'events':entry['events'],'activity_after_calls':5.0,
                'note':'No request/event ID is available to distinguish a retry from another genuine use.'}
    probe('identical_hit_retries_inflate_activity', dedup)

    def confirms(e, root, mem, script):
        e.save_index({'version':1,'entries':[row()]})
        stages=[]
        for _ in range(3):
            assert capture(e.cmd_confirm,'alpha-record')[2] is None
            a=e.load_index()['entries'][0];stages.append({'stage':a['review_stage'],'next_review':a['next_review']})
        assert [x['stage'] for x in stages]==[1,2,3]
        return {'same_day_calls':3,'stages':stages,'evidence_reference_required':False}
    probe('same_day_confirmation_advances_to_90_days', confirms)

    def ambiguous(e, root, mem, script):
        es=[row('e001','common-A','Synthetic value A'),row('e002','common-B','Synthetic value B')]
        e.save_index({'version':1,'entries':es})
        out,_,err=capture(e.cmd_confirm,'common');assert not err
        data=e.load_index()['entries']; counts=[len(x['events']) for x in data]
        assert counts==[2,1]
        return {'matching_candidates':2,'after_event_counts':counts,'observed':out.strip(),
                'expected':'Ambiguous update requests identify an exact record or return ambiguity.'}
    probe('ambiguous_update_silently_uses_first_match', ambiguous)

    def lost(e, root, mem, script):
        e.save_index({'version':1,'entries':[row()]})
        a=e.load_index();b=e.load_index()
        a['entries'][0]['events'].append({'t':'2026-09-06','type':'hit','note':'writer-A'})
        b['entries'][0]['events'].append({'t':'2026-09-06','type':'hit','note':'writer-B'})
        e.save_index(a);e.save_index(b)
        notes=[x.get('note') for x in e.load_index()['entries'][0]['events']]
        assert 'writer-A' not in notes and 'writer-B' in notes
        return {'interleaving':['read-A','read-B','write-A','write-B'],
                'final_event_notes':notes,'conflict_reported':False,'lost_event':'writer-A'}
    probe('two_reader_interleaving_loses_first_update', lost)

    def interrupted(e, root, mem, script):
        data={'version':1,'entries':[row()]};e.save_index(data)
        original=Path(e.INDEX).read_bytes()
        def failing_dump(value, stream, **kwargs):
            stream.write('{');stream.flush();raise OSError('synthetic interrupted write')
        with patch.object(e.json,'dump',side_effect=failing_dump):
            _,_,err=capture(e.save_index,data)
        assert err and err['type']=='OSError'
        after=Path(e.INDEX).read_bytes();assert after==b'{' and after!=original
        _,_,readerr=capture(e.load_index);assert readerr and readerr['type']=='JSONDecodeError'
        return {'failure_injected':'json.dump wrote one byte then raised OSError',
                'old_valid_file_preserved':False,'remaining_bytes':'{','reload':readerr,
                'scope':'Function-boundary fault injection, not an OS power-loss test'}
    probe('interrupted_save_destroys_previous_valid_index', interrupted)

    def high(e, root, mem, script):
        old=(FIXED_DATE-datetime.timedelta(days=1000)).isoformat()
        item=row(cost_class='high',created=old,events=[{'t':old,'type':'create'}])
        e.save_index({'version':1,'entries':[item]})
        (mem/'MEMORY.md').write_text(item['key']+'\n',encoding='utf-8')
        out,_,err=capture(e.cmd_audit); assert not err
        score=e.activation(item);assert score<0.6
        assert '[降级提议 T0→T1]' not in out and '热层条目激活均在阈值之上' in out
        return {'age_days':1000,'score':score,'demotion_threshold':0.6,
                'demotion_suggested':False,'misleading_output':'热层条目激活均在阈值之上'}
    probe('high_priority_exemption_and_misleading_report', high)

    def promotion(e, root, mem, script):
        es=[{'t':'2026-09-06','type':'promote'}]
        score=e.activation({'events':es});unknown=e.activation({'events':[{'t':'2026-09-06','type':'nonsense'}]})
        assert score==1.5 and unknown==1.0
        return {'promotion_event_score':score,'unknown_event_score':unknown,
                'expected':'Relocation is state metadata, unknown events do not silently acquire a positive weight'}
    probe('relocation_and_unknown_events_increase_activity', promotion)

    def cli(e, root, mem, script):
        env={**os.environ,'THM_MEM_DIR':str(mem)}
        missing=subprocess.run([sys.executable,str(script),'hit'],capture_output=True,text=True,env=env,timeout=10)
        unknown=subprocess.run([sys.executable,str(script),'unknown-command'],capture_output=True,text=True,env=env,timeout=10)
        nohit=subprocess.run([sys.executable,str(script),'hit','not-found'],capture_output=True,text=True,env=env,timeout=10)
        assert 'IndexError' in missing.stderr and unknown.returncode==0 and nohit.returncode==0
        return {'missing_hit_argument':{'exit':missing.returncode,'exception':'IndexError'},
                'unknown_command_exit':unknown.returncode,'missing_record_exit':nohit.returncode}
    probe('cli_usage_and_failure_status_contracts', cli)

    def tilde(e, root, mem, script):
        with patch.dict(os.environ,{'THM_MEM_DIR':'~/synthetic-not-real-memories'}): result=e._resolve_mem_dir()
        assert result=='~/synthetic-not-real-memories'
        return {'configured':'~/synthetic-not-real-memories','resolved':result,'tilde_expanded':False}
    probe('configured_memory_path_does_not_expand_tilde', tilde)

    return {'date':'2026-09-06','target_commit':TARGET_COMMIT,'source_blob':blob,
            'source_bytes':len(source),'python':sys.version.split()[0],
            'scope':'Actual public-engine functions on synthetic temporary stores; no private data or live Hermes',
            'diagnostics_confirmed':sum(x['diagnostic']=='CONFIRMED' for x in observations),
            'probe_errors':sum(x['diagnostic']=='PROBE_ERROR' for x in observations),
            'observations':observations}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(); result=run(args.engine)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output: args.output.write_text(text,encoding='utf-8')
    print(text,end='')
    sys.exit(1 if result['probe_errors'] else 0)
