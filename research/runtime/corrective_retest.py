"""Bounded corrective retest; local model only, no LoCoMo/LME matrix."""
import argparse
import json
import math
from pathlib import Path
import sys
import time
from thm.runtime.autotune import autotune
from thm.runtime.receipts import write_receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-path',required=True);p.add_argument('--model-id',required=True)
    p.add_argument('--output-dir',required=True);p.add_argument('--wall-seconds',type=float,default=600)
    p.add_argument('--prepare-ort',action='store_true')
    p.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args();root=Path(args.output_dir)
    if not math.isfinite(args.wall_seconds) or not 0<args.wall_seconds<=900:raise ValueError('corrective retest ceiling is 900 seconds')
    if not args.internal_worker:
        from research.runtime.bounds import bounded_process
        return bounded_process([sys.executable,'-m','research.runtime.corrective_retest',*sys.argv[1:],'--internal-worker'],args.wall_seconds,root)
    root.mkdir(parents=True,exist_ok=False);deadline=time.monotonic()+args.wall_seconds;session={}
    from research.runtime.synthetic import smoke
    write_receipt(root/'synthetic.json',smoke())
    common={'maximum':2,'deadline':deadline,'reference_session':session}
    baseline=autotune(args.model_path,args.model_id,baseline_only=True,**common)
    write_receipt(root/'reference-fallback.json',baseline)
    if baseline['status']!='calibrated':return 1
    result=autotune(args.model_path,args.model_id,**common,
        plan_callback=lambda entries:write_receipt(root/'candidate-plan.json',{'entries':entries,'phase':'before-execution'}))
    write_receipt(root/'auto-safe.json',result)
    if args.prepare_ort:
        from thm.runtime.prepare import prepare
        remaining=deadline-time.monotonic()
        if remaining>1:write_receipt(root/'ort-preparation.json',prepare(args.model_path,root/'derived','onnxruntime_fp32',timeout=min(90,remaining)))
    write_receipt(root/'completed.json',{'status':result['status'],'correctness_safe':result['status']=='calibrated',
        'optimized_auto_safe':result.get('optimized_auto_safe',False),'generation_calls':0,'full_dataset_acceptance':False,
        'evidence_scope':'fixed calibration corpus and synthetic ignition only; no dataset acceptance'})
    return 0 if result['status']=='calibrated' else 1

if __name__=='__main__':sys.exit(main())
