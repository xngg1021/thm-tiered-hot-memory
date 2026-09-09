"""Explicit local conversion into a fresh content-addressed artifact directory."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from .identity import manifest,digest
from .hardware import versions
from .receipts import write_receipt
from .failures import failure


def _convert(config, state):
    state[0]="model-load"
    from sentence_transformers import SentenceTransformer
    source=Path(config['model_path']);out=Path(config['staging']);backend=config['backend']
    family='onnx' if backend.startswith('onnxruntime') else 'openvino'
    if manifest(source)['sha256']!=config['source_manifest_sha256']:raise ValueError('source model changed')
    # Load/export from a private source copy, then save only this conversion into
    # a fresh output tree. Existing optimized variants must not become candidates.
    if out.exists():raise FileExistsError('conversion output already exists')
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        state[0]='source-copy'
        private=Path(temp)/'source';shutil.copytree(source,private)
        state[0]='export'
        model=SentenceTransformer(str(private),backend=family,device='cpu',local_files_only=True,trust_remote_code=False,model_kwargs={'export':True})
        model.save_pretrained(str(out))
    state[0]='artifact-discovery'
    transform='local-export-fp32'
    if family=='onnx':
        files=sorted(out.rglob('*.onnx'))
        if len(files)!=1:raise ValueError('ambiguous exported ONNX architecture')
        target=files[0]
        if backend.endswith('int8'):
            state[0]='quantization'
            from onnxruntime.quantization import quantize_dynamic,QuantType
            quantized=target.with_name('model.thm-int8.onnx')
            quantize_dynamic(str(target),str(quantized),weight_type=QuantType.QInt8)
            target=quantized;transform='ort-dynamic-qint8-v1'
    else:
        files=sorted(out.rglob('*.xml'))
        if len(files)!=1:raise ValueError('ambiguous exported OpenVINO architecture')
        target=files[0]
        import openvino as ov
        core=ov.Core();model_ir=core.read_model(str(target))
        if backend.endswith('int8'):
            state[0]='quantization'
            import nncf
            model_ir=nncf.compress_weights(model_ir,mode=nncf.CompressWeightsMode.INT8)
            target=target.with_name('model.thm-int8.xml');transform='openvino-weight-only-int8-v1'
        ov.save_model(model_ir,str(target),compress_to_fp16=False)
    state[0]='verification'
    if manifest(source)['sha256']!=config['source_manifest_sha256']:raise ValueError('source model changed during conversion')
    result={'schema':1,'status':'prepared','backend':backend,'precision':'int8' if backend.endswith('int8') else 'fp32',
        'source_manifest_sha256':config['source_manifest_sha256'],'derived_manifest_sha256':manifest(out)['sha256'],
        'converter_versions':versions(),'transformation':transform,'model_file':target.relative_to(out).as_posix(),
        'admission':'approximate/performance-candidate' if backend.endswith('int8') else 'pending-semantic-gate',
        'generation_calls':0}
    state[0]='publication'
    write_receipt(out/'thm-preparation.json',result)
    return result


def convert(config):
    state=['model-load']
    try:return _convert(config,state)
    except Exception as exc:
        return failure(exc,state[0],config['backend'],
            'ambiguous-artifact' if state[0]=='artifact-discovery' and isinstance(exc,ValueError) else None)


def _prepare(source,cache_root,backend,timeout=600, state=None):
    if backend not in ('onnxruntime_fp32','onnxruntime_int8','openvino_fp32','openvino_int8'):raise ValueError('unsupported conversion target')
    source=Path(source).resolve();cache_root=Path(cache_root).resolve()
    if source==cache_root or source in cache_root.parents:raise ValueError('derived cache must be outside source model')
    cache_root.mkdir(parents=True,exist_ok=True);source_sha=manifest(source)['sha256']
    with tempfile.TemporaryDirectory(dir=cache_root) as temp:
        staging=Path(temp)/'model';config={'model_path':str(source),'source_manifest_sha256':source_sha,'backend':backend,'staging':str(staging),'threads':1}
        cfg=Path(temp)/'config.json';cfg.write_text(json.dumps(config));output=Path(temp)/'result.json'
        state[0]='conversion-worker'
        subprocess.run([sys.executable,'-m','thm.runtime.worker','prepare',str(cfg),str(output)],timeout=timeout,check=True,capture_output=True)
        receipt=json.loads(output.read_text())
        if receipt.get('status')!='prepared':return receipt
        state[0]='verification'
        if manifest(staging)['sha256']!=receipt['derived_manifest_sha256']:raise ValueError('derived bytes changed')
        target=cache_root/receipt['derived_manifest_sha256']
        # mkdir is the cross-process exclusive reservation; never replace existing content.
        state[0]='publication'
        target.mkdir()
        try:
            for item in staging.iterdir():shutil.move(str(item),str(target/item.name))
        except Exception:
            # Partial destination is consumed and has no valid manifest; no overwrite retry.
            raise
        return {**receipt,'artifact_locator':target.name}


def prepare(source,cache_root,backend,timeout=600):
    state=['source-copy']
    try:return _prepare(source,cache_root,backend,timeout,state)
    except Exception as exc:return failure(exc,state[0],backend)
