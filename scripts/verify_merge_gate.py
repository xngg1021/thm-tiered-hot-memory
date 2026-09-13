#!/usr/bin/env python3
"""Validate an explicitly fetched GitHub snapshot before an expected-head merge.

This is an offline admission check, not remote branch protection. The actual
caller must fetch main immediately before admission, pass expected_head_sha to
GitHub, and verify the returned merge parents before accepting the release.
GitHub's merge API does not expose an atomic expected-base guard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

# Support direct execution from any directory without requiring installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thm._bounded_files import bounded_file_bytes

REPOSITORY = 'xngg1021/thm-tiered-hot-memory'
ARCHIVE = 'e6e4dda5835e3cb345207457d5491131c6959b2c'
ARCHIVE_V15 = 'de26865f36df2205c29a470e51c65d5bf9beca4e'
REQUIRED = ('THM correctness', 'THM Hermes integration', 'THM harness integrations', 'THM systems native and reliability')


def verify(snapshot, *, expected_head, expected_base):
    if not re.fullmatch('[0-9a-f]{40}', expected_head):
        raise ValueError('full expected head required')
    if snapshot.get('repository') != REPOSITORY or snapshot.get('head_sha') != expected_head:
        raise ValueError('repository/head changed')
    if snapshot.get('base_ref') != 'main' or snapshot.get('state') != 'open' or snapshot.get('draft') is not False:
        raise ValueError('open ready successor targeting main required')
    if type(snapshot.get('pr_number')) is not int or snapshot['pr_number'] <= 0:
        raise ValueError('valid PR required')
    if not re.fullmatch('[0-9a-f]{40}', expected_base):
        raise ValueError('full freshly observed base identity required')
    if snapshot.get('base_sha') != expected_base:
        raise ValueError('base changed; refresh snapshot and repeat admission')
    if snapshot.get('archive_v1_4_sha') != ARCHIVE:
        raise ValueError('historical archive moved')
    if snapshot.get('archive_v1_5_sha') != ARCHIVE_V15:
        raise ValueError('1.5 stable archive moved')
    if snapshot.get('merge_method') != 'merge' or snapshot.get('force_push') is not False:
        raise ValueError('forward-only normal merge required')
    admitted = {}
    for name in REQUIRED:
        rows = [r for r in snapshot.get('workflow_runs', []) if r.get('name') == name and
                r.get('head_sha') == expected_head and r.get('event') == 'push']
        if not rows:
            raise ValueError('missing exact-head workflow: ' + name)
        # A newer failed/running attempt cannot hide behind an older success.
        row = max(rows, key=lambda r:(r.get('id', 0), r.get('run_attempt', 1)))
        if row.get('status') != 'completed' or row.get('conclusion') != 'success':
            raise ValueError('workflow not successful: ' + name)
        if type(row.get('id')) is not int or row['id'] <= 0:
            raise ValueError('workflow identity required')
        admitted[name] = row['id']
    review = snapshot.get('review', {})
    if review.get('unresolved_actionable') != 0:
        raise ValueError('actionable review findings remain')
    if review.get('head_sha') != expected_head:
        raise ValueError('review head mismatch')
    if review.get('status') == 'service-unavailable':
        if type(review.get('attempts')) is not int or not 1 <= review['attempts'] <= 2 or not review.get('reason'):
            raise ValueError('bounded external review exception needs evidence')
    elif review.get('status') != 'reviewed':
        raise ValueError('review state unsupported')
    out = {'schema': 'thm-merge-gate/1', 'repository': REPOSITORY, 'pr_number': snapshot['pr_number'],
           'expected_head_sha': expected_head, 'expected_base_sha': expected_base,
           'base_sha': snapshot['base_sha'], 'merge_method': 'merge',
           'workflow_ids': admitted, 'review': review, 'archive_v1_4_sha': ARCHIVE, 'archive_v1_5_sha':ARCHIVE_V15,
           'remote_protection': snapshot.get('remote_protection', 'unknown'),
           'scope': 'snapshot admission against freshly observed main; expected-head merge and exact-parent postcondition still required'}
    raw = json.dumps(out, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {**out, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}


def verify_merge_result(receipt, *, parents):
    """Reject an intervening base/head change before archive/release acceptance."""
    body = {k: v for k, v in receipt.items() if k != 'receipt_sha256'}
    raw = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if receipt.get('receipt_sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('invalid admission receipt')
    expected = [receipt['expected_base_sha'], receipt['expected_head_sha']]
    if list(parents) != expected:
        raise ValueError('merge parents changed; release not accepted; refresh evidence and repeat admission')
    return {'status': 'matched', 'parents': expected, 'admission_sha256': receipt['receipt_sha256']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path);p.add_argument('--expected-head', required=True)
    p.add_argument('--expected-base', required=True,
                   help='main SHA independently fetched immediately before admission')
    args=p.parse_args()
    raw = bounded_file_bytes(args.snapshot, 8*1024*1024).decode('utf-8')
    print(json.dumps(verify(json.loads(raw),expected_head=args.expected_head,
                            expected_base=args.expected_base),indent=2))


if __name__ == '__main__':main()
