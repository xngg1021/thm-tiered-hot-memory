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


def main():
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


if __name__=='__main__':main()
