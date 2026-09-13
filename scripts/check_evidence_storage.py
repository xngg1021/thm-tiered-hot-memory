"""Reject newly introduced oversized raw evidence while preserving old Git blobs."""
import argparse
import subprocess
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from thm.evidence_storage import GIT_THRESHOLD


def check(base='HEAD^',head='HEAD'):
    paths=subprocess.check_output(['git','diff','--name-only','--diff-filter=AM',base,head,'--','reports','research'],
                                  cwd=ROOT,text=True).splitlines()
    errors=[]
    for path in paths:
        if Path(path).suffix.lower() not in ('.json','.jsonl','.csv','.tsv','.zip','.parquet','.npy','.npz'):
            continue
        size=int(subprocess.check_output(['git','cat-file','-s',head+':'+path],cwd=ROOT,text=True))
        if size>GIT_THRESHOLD:
            errors.append(f'{path}: {size} bytes exceeds {GIT_THRESHOLD}; publish manifest plus external/CAS object')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='HEAD^');parser.add_argument('--head',default='HEAD')
    args=parser.parse_args();errors=check(args.base,args.head)
    for error in errors:print(error)
    if not errors:print('evidence storage policy passed; historical raw blobs unchanged')
    return int(bool(errors))


if __name__=='__main__':raise SystemExit(main())
