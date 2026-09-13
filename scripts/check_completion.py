#!/usr/bin/env python3
"""Verify the current completion census, executable mappings and version boundaries."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thm.runtime.fabric.catalog import BUILTINS
from thm.physical.backends import FAMILIES
from thm.evaluation.adapters import ADAPTERS
from thm.actuator import ActuatorPolicy


def legacy():
    value=json.loads((ROOT/'reports/2026-09-12-thm-full-power-completion.json').read_text())
    assert value['schema']=='thm-full-power-completion/1'
    assert value['version']==(ROOT/'VERSION').read_text().strip()
    import thm
    assert value['version']==thm.__version__
    assert 'version = "'+value['version']+'"' in (ROOT/'pyproject.toml').read_text()
    domains=value['domains']
    assert len(domains)==28 and len({r['domain'] for r in domains})==28
    for row in domains:
        assert row['status']=='implemented'
        for path in row['implementation_paths']+row['validation_paths']:
            assert (ROOT/path).is_file() and (ROOT/path).resolve().is_relative_to(ROOT)
    rows=value['provider_census']['providers'];catalog={s.provider_id:s for s in BUILTINS}
    assert len(rows)==len(catalog)==value['provider_census']['total']
    assert {r['provider_id'] for r in rows}==set(catalog)
    for row in rows:
        assert row['native_catalog_maturity']=='L'+str(catalog[row['provider_id']].maturity)
        assert row['hardware_evidence']=='hardware-unvalidated'
    physical=value['physical_backend_census']
    assert physical['total']==len(FAMILIES)==len(physical['families'])
    assert {r['family'] for r in physical['families']}==set(FAMILIES)
    assert {r['name'] for r in value['benchmark_adapter_census']}==set(ADAPTERS)
    assert len(value['harness_census'])==11
    assert value['counts']==dict(implemented_domains=28,intentionally_rejected_policies=len(value['intentionally_rejected']),
        evidence_only_items=len(value['evidence_only']),external_only_governance_items=len(value['external_only']),implementation_external_gaps=0)
    assert all(r['status']=='intentionally-rejected' for r in value['intentionally_rejected'])
    assert all(r['status']=='evidence-only-pending' for r in value['evidence_only'])
    assert not ActuatorPolicy().automatic_mutation and value['boundaries']['automatic_mutation'] is False
    assert value['historical']['archive_v1_4_sha']=='e6e4dda5835e3cb345207457d5491131c6959b2c'
    assert value['historical']['machine_evidence_reclassified'] is False
    if value['release']['status']=='accepted':
        assert value['accepted_merge_commit'] and value['release']['head']
        assert len(value['release']['exact_head_workflows'])>=3 and len(value['release']['post_merge_workflows'])>=3
    print('completion census OK: 28 domains, 71 providers, 42 physical families, 5 benchmarks, 11 harness surfaces')




def current():
    value=json.loads((ROOT/'reports/2026-09-13-thm-1.6-full-power-completion.json').read_text())
    import thm
    assert value['schema']=='thm-full-power-completion/2'
    assert value['version']==thm.__version__==(ROOT/'VERSION').read_text().strip()=='1.6.0'
    assert 'version = "1.6.0"' in (ROOT/'pyproject.toml').read_text()
    domains=value['domains']
    expected={'logical memory','retrieval','ceiling decomposition','temporal algebra','event chain',
      'contradiction/supersession','multi-evidence assembly','hotness vector','dynamic topology','hotplug',
      'thermal','power','boost','sustainable envelope','elastic concurrency','QoS','NUMA','native async I/O',
      'SysCore','Linux native','Windows native','macOS native','CUDA driver/VMM','Apple MPS','CoreML',
      'MPSGraph','BNNS/Accelerate','KV bridge','agent program runtime','tool overlap/speculation',
      'full-stack ablation','reliability','aging','self-check','fault injection','CE bridge','evidence storage',
      'evaluation','multi-harness','release/governance'}
    assert {row['domain'] for row in domains}==expected and len(domains)==len(expected)
    for row in domains:
        assert row['status']=='implemented' and row['scope']
        for name in row['implementation_paths']+row['validation_paths']:
            assert (ROOT/name).is_file() and (ROOT/name).resolve().is_relative_to(ROOT)
    providers=value['provider_census']['providers'];catalog={p.provider_id:p for p in BUILTINS}
    assert len(providers)==len(catalog)==71
    assert {r['provider_id'] for r in providers}==set(catalog)
    assert all(r['native_catalog_maturity']=='L'+str(catalog[r['provider_id']].maturity) for r in providers)
    assert value['physical_backend_census']['total']==len(FAMILIES)==42
    assert {r['name'] for r in value['benchmark_adapter_census']}==set(ADAPTERS)
    assert len(value['harness_census'])==11
    assert value['counts']['implemented_domains']==40 and value['counts']['implementation_external_gaps']==0
    assert not value['boundaries']['automatic_mutation'] and not ActuatorPolicy().automatic_mutation
    assert value['historical']['archive_v1_5_sha']=='de26865f36df2205c29a470e51c65d5bf9beca4e'
    assert value['historical']['machine_evidence_reclassified'] is False
    for field,status in [('intentionally_rejected','intentionally-rejected'),('evidence_only','evidence-only-pending')]:
        assert all(row['status']==status for row in value[field])
    if value['release']['status']=='accepted':
        assert value['release']['accepted_merge_commit'] and value['release']['stable_archive_created']
    print('completion census OK: 40 domains, 71 providers, 42 physical families, 5 benchmarks, 11 harness surfaces')


def main():
    if (ROOT/'VERSION').read_text().strip()=='1.6.0':current()
    else:legacy()


if __name__=='__main__':main()
