"""Bounded campaigns and exact, auditable reference reuse (protocol 2)."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from thm.runtime.identity import digest

PROTOCOL = 2

@dataclass(frozen=True)
class ReferenceArtifactKey:
    dataset_sha256: str
    source_manifest: str
    embedding_profile: dict
    reference_policy: dict
    semantic_implementation: str
    counter_identity: dict
    protocol: int = PROTOCOL

    @property
    def id(self):
        return digest(asdict(self))


def semantic_identity():
    # Explicit dependency closure; scheduler, probes, docs and physical placement
    # are excluded. Unknown future semantic modules must extend this closure.
    root = Path(__file__).resolve().parents[2]
    names = ['thm/retrieval.py', 'thm/entities.py', 'thm/features.py',
             'thm/runtime/identity.py', 'thm/runtime/storage.py',
             'thm/runtime/research.py', 'research/recall/benchmark.py',
             'research/recall/lme_retrieval.py']
    names += [str(p.relative_to(root)) for p in (root/'thm/runtime/backends').rglob('*.py')]
    return digest({n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(names)})


def reuse(source, key):
    source = Path(source)
    metadata = json.loads(source.with_suffix('.reference.json').read_text())
    raw = source.read_bytes()
    if metadata.get('key') != asdict(key) or metadata.get('key_id') != key.id:
        raise ValueError('stale reference reuse key')
    sha = hashlib.sha256(raw).hexdigest()
    if metadata.get('artifact_sha256') != sha or metadata.get('returncode') != 0:
        raise ValueError('invalid reference artifact')
    json.loads(raw)
    return raw, {'reused': True, 'source_artifact_sha256': sha,
                 'key': asdict(key), 'key_id': key.id,
                 'provenance': metadata.get('provenance')}


def campaign(mode='acceptance', *, full_campaign=False, acknowledge=False,
             wall_seconds=3600, approximate=False, retrieval_ab=False):
    if mode not in ('smoke', 'acceptance', 'full-research'):
        raise ValueError('unknown verification mode')
    if wall_seconds <= 0 or not math.isfinite(wall_seconds):
        raise ValueError('positive finite wall budget required')
    if mode == 'full-research' and not full_campaign:
        raise ValueError('full-research requires --full-campaign')
    if full_campaign:
        mode = 'full-research'
        if not acknowledge:
            raise ValueError('full campaign requires --acknowledge-multi-hour-run')
    if (approximate or retrieval_ab) and mode != 'full-research':
        raise ValueError('extended experiments require full campaign')
    return {'mode': mode, 'lme_limit': None if full_campaign else (2 if mode == 'smoke' else 5),
            'sample_instances': 2 if mode == 'smoke' else 5,
            'wall_seconds': wall_seconds, 'full_dataset_acceptance': False,
            'extended_diagnostics': full_campaign}


def estimate(sample_seconds, sample_count, total_count, arms, budget, *, extra_seconds=0):
    if sample_seconds <= 0 or sample_count <= 0 or arms <= 0:
        raise ValueError('positive measured sample required')
    reference = sample_seconds / sample_count * total_count
    total = reference * arms + extra_seconds
    return {'sample_instances': sample_count, 'sample_seconds': sample_seconds,
            'measured_instances_per_second': sample_count/sample_seconds,
            'projected_reference_seconds': reference,
            'projected_winner_seconds': reference*(arms-1),
            'projected_total_seconds': total, 'expected_matrix_artifacts': arms,
            'projection_method': 'measured-reference-linear-conservative; winners unmeasured',
            'within_budget': total <= budget}


def bounded_process(command, seconds, root):
    """Bound the entire owned process tree, including prepare/autotune children."""
    import os
    import signal
    import subprocess
    from thm.runtime.receipts import write_receipt
    if root.exists():raise FileExistsError('verification output namespace exists')
    process=subprocess.Popen(command,start_new_session=(os.name=='posix'))
    try:return process.wait(timeout=seconds)
    except (subprocess.TimeoutExpired,KeyboardInterrupt) as exc:
        if os.name=='posix':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
            if process.poll() is None:process.kill()
        process.wait(timeout=10)
        root.mkdir(parents=True,exist_ok=True)
        if not (root/'interrupted.json').exists():
            write_receipt(root/'interrupted.json',{'status':'interrupted-or-wall-budget-exceeded',
                'error_type':type(exc).__name__,'wall_budget_seconds':seconds,'full_dataset_acceptance':False})
        return 124
