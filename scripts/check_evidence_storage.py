"""Reject newly introduced oversized raw evidence while preserving old Git blobs."""
import argparse
import os
import subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thm.evidence_storage import GIT_THRESHOLD


def comparison_base(head):
    base=os.environ.get('THM_EVIDENCE_BASE','')
    if base and set(base)!={'0'}:
        if os.environ.get('THM_EVIDENCE_EVENT')!='pull_request':return base
    else:
        base='origin/main'
    # PRs/new branches compare all introduced work, not only the last commit.
    # A missing admission ref fails closed; local callers can supply --base.
    return subprocess.check_output(['git','merge-base',base,head],cwd=ROOT,text=True).strip()


def check(base=None,head='HEAD'):
    base=base or comparison_base(head)
    paths=subprocess.check_output(['git','diff','--name-only','-z','--no-renames','--diff-filter=AM',base,head,'--','reports','research'],
                                  cwd=ROOT,text=True).split('\0')
    errors=[]
    for path in paths:
        if Path(path).suffix.lower() not in ('.json','.jsonl','.csv','.tsv','.zip','.parquet','.npy','.npz',
                                             '.gz','.bz2','.xz','.zst','.tar','.tgz','.7z'):
            continue
        size=int(subprocess.check_output(['git','cat-file','-s',head+':'+path],cwd=ROOT,text=True))
        if size>GIT_THRESHOLD:
            errors.append(f'{path}: {size} bytes exceeds {GIT_THRESHOLD}; publish manifest plus external/CAS object')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base');parser.add_argument('--head',default='HEAD')
    args=parser.parse_args();errors=check(args.base,args.head)
    for error in errors:print(error)
    if not errors:print('evidence storage policy passed; historical raw blobs unchanged')
    return int(bool(errors))


if __name__=='__main__':raise SystemExit(main())
