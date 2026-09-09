"""Bounded dataplane measurements with orthogonal runtime/storage receipts."""
from dataclasses import asdict, replace
from pathlib import Path
import platform
import sqlite3
import sys
import time
from thm.retrieval import SearchIndex, TokenCounter
from .contracts import Receipt, Result, Taxonomy, digest
from .metrics import summarize


from .identity import implementation_identity


def run(adapter, source, root, *, mode='acceptance', provenance='external-dataset',
        full_research=False, budget=600, logical_tier='T3'):
    if mode not in ('smoke', 'acceptance', 'full-research'):
        raise ValueError('invalid mode')
    if (mode == 'full-research') != full_research:
        raise ValueError('full campaign requires mode=full-research and explicit full_research=True')
    if type(budget) is not int or not 0 <= budget <= 32768:
        raise ValueError('invalid budget')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    maximum = 2 if mode == 'smoke' else 8 if mode == 'acceptance' else None
    rows, identities = [], set()
    truncated = False
    total_docs, source_bytes = 0, 0
    start = time.perf_counter()
    for task, gold in adapter.tasks(source):
        if maximum is not None and len(rows) >= maximum:
            truncated = True
            break
        if task.id in identities:
            raise ValueError('duplicate task ID')
        identities.add(task.id)
        if task.query_image is not None:
            raise ValueError('query images require a separate multimodal operating point')
        docs = tuple(replace(d, tier=logical_tier) for d in task.documents)
        nbytes = sum(len(d.text.encode('utf-8')) for d in docs)
        if maximum is not None and (len(docs) > 2000 or nbytes > 2_000_000):
            raise ValueError('task exceeds bounded corpus limit; use explicit full-research')
        total_docs += len(docs)
        source_bytes += nbytes
        index = SearchIndex(root / f'{len(rows)}.sqlite', TokenCounter('utf8_bytes'))
        try:
            index.replace_scope(task.scope, docs)
            out = index.search(task.scope, task.query, mode='sparse', budget=budget)
        finally:
            index.close()
        selected = tuple(x['id'] for x in out['selected'] if x['complete'])
        unit_map = {d.id: d.source if gold.unit == 'session' else d.id for d in docs}
        units = tuple(unit_map[x] for x in selected)
        parents = tuple(unit_map[x] for x in out.get('parent_locator_ids', selected) if x in unit_map)
        result = Result(task.id, gold, selected, units, parents, out['budget_used'],
                        out['timing_ms']['total'], len(out['selected']))
        rows.append(result.public())
    if not rows:
        raise ValueError('empty campaign')
    taxonomy = Taxonomy(logical_tier=logical_tier)
    layers = {
        'memory-dataplane': {'status': 'measured', 'metrics': summarize(rows), 'rows': rows,
                             'counter': 'utf8_bytes', 'budget': budget, 'mode': 'sparse'},
        'systems-runtime': {'status': 'measured', 'wall_seconds': time.perf_counter() - start,
            'python': sys.version.split()[0], 'os': platform.platform(), 'sqlite': sqlite3.sqlite_version,
            'compute_profile': taxonomy.compute_profile,
            'documents_indexed_including_rebuilds': total_docs, 'source_bytes_including_rebuilds': source_bytes,
            'physical_storage': {'status': 'unavailable', 'storage_profile': None, 'placement': None,
                                 'io_telemetry': None, 'reason': 'SQLite OS I/O is not instrumented'}},
        'LLM-agent-outcome': {'status': 'not-run', 'generation_calls': 0, 'judge_calls': 0,
                              'answer_accuracy': None, 'environment_success': None}}
    receipt = Receipt(adapter.name, adapter.protocol, digest(source), implementation_identity(), mode,
        provenance, taxonomy, layers, {'executed_tasks': len(rows), 'truncated': truncated,
                                      'scope': 'retrieval-only; agent/environment outcome not executed'})
    return receipt.public()


def storage_probe(root):
    """Separate bounded local-filesystem probe; never attributed to SQLite I/O."""
    from thm.physical.probe import probe
    from thm.physical.benchmark import benchmark
    from thm.physical.adapters import LocalFilesystemAdapter
    from thm.physical.contracts import PhysicalTelemetry, TransferExtent
    import hashlib
    root = Path(root)
    root.mkdir()
    target, topology = probe(root)
    if target.adapter != 'local-filesystem' or target.readonly is not False:
        return {'status': 'unavailable', 'target': target.public(), 'storage_profile': None,
                'placement': None, 'io_telemetry': None}
    profile = benchmark(target, scratch_bytes=1024*1024, seconds=5)
    data = b'THM Evaluation Fabric physical fixture\n' * 128
    sha = hashlib.sha256(data).hexdigest()
    path = root / (sha + '.seg')
    path.write_bytes(data)
    try:
        telemetry = PhysicalTelemetry(target.target_id)
        reader = LocalFilesystemAdapter(root)
        if not reader.verify(sha) or reader.read(TransferExtent(sha, 0, len(data)), telemetry=telemetry) != data:
            raise ValueError('physical fixture mismatch')
        return {'status': 'measured', 'scope': 'separate physical fixture; not SQLite telemetry',
                'target': target.public(), 'storage_profile': asdict(profile), 'storage_profile_id': profile.id,
                'placement': {'target_id': target.target_id, 'object_sha256': sha, 'bytes': len(data)},
                'io_telemetry': telemetry.receipt(), 'hardware_acceptance': False}
    finally:
        path.unlink()
