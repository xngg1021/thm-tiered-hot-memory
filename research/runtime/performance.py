"""Summaries retain nested timing scopes instead of adding overlapping clocks."""
from collections import Counter
import math


def shared_batch_clocks(rows):
    """Native matrices have one search_many call per scope/mode/budget cohort.

    Receipts repeat once per query. Chunk length, not equal-clock hashing,
    establishes batch boundaries; matrix loading is shared by the entire call.
    """
    groups={};unresolved=0;amortized_rows=0
    fields=('embedding_ms','batch_preparation_ms','lexical_preparation_ms',
            'dense_scoring','transfer','dense_matrix_load')
    for row in rows:
        receipt=row.get('batch_receipt') or {}
        if not receipt:continue
        if 'query_batch_size' not in receipt:
            amortized_rows+=1;continue
        if not all(k in row for k in ('scope','mode','budget')):
            unresolved+=1;continue
        groups.setdefault((row['scope'],row['mode'],row['budget']),[]).append(receipt)
    totals=Counter();batches=0;calls=0;load_calls=0
    for receipts in groups.values():
        offset=0;chunks=[];valid=True
        while offset<len(receipts):
            first=receipts[offset];size=first.get('query_batch_size')
            if type(size) is not int or not 1<=size<=256:
                valid=False;break
            chunk=receipts[offset:offset+size]
            if len(chunk)!=size or any(r.get('query_batch_size')!=size or any(r.get(k)!=first.get(k) for k in fields) for r in chunk):
                valid=False;break
            numeric={k:first[k] for k in fields if k in first}
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in numeric.values()):
                valid=False;break
            chunks.append(numeric);offset+=size
        if not valid:
            unresolved+=len(receipts);continue
        calls+=1;batches+=len(chunks)
        for chunk in chunks:
            totals.update({k:v for k,v in chunk.items() if k!='dense_matrix_load'})
        loads=[chunk.get('dense_matrix_load') for chunk in chunks]
        if loads and loads[0] is not None and all(v==loads[0] for v in loads):
            totals['dense_matrix_load']+=loads[0];load_calls+=1
    return {'totals_ms':dict(totals),'batches':batches,'calls':calls,
        'matrix_load_calls':load_calls,'matrix_load_calls_unknown':calls-load_calls,
        'unresolved_receipt_rows':unresolved,'amortized_only_receipt_rows':amortized_rows,
        'scope':'complete native scope/mode/budget cohorts; chunk clocks once per batch, matrix load once per call',
        'overlap_semantics':'embedding and lexical clocks are nested in batch preparation; transfer is nested in scoring; amortized preembedding is already in row clocks'}


def decomposition(artifact):
    totals=Counter();count=0;batch_rows=0;checked=0;residual=0.0;invalid=0
    for row in artifact.get('rows',[]):
        timing=row.get('timing_breakdown_ms',row.get('timing_ms')) or {}
        if not timing:continue
        count+=1;batch_rows+=int(bool(row.get('batch_receipt')))
        numeric={name:value for name,value in timing.items() if type(value) in (float,int) and math.isfinite(value)}
        invalid+=len(timing)-len(numeric)
        totals.update(numeric)
        if {'total','retrieval_total','pack'}<=numeric.keys():
            checked+=1;residual+=numeric['total']-numeric['retrieval_total']-numeric['pack']
    return {'rows_with_timing':count,'rows_with_batch_receipt':batch_rows,
        'raw_stage_totals_ms':dict(totals),
        'raw_stage_scope':'row-local clocks only; shared batch clocks are reported separately',
        'shared_batch_clocks':shared_batch_clocks(artifact.get('rows',[])),
        'invalid_timing_fields':invalid,
        'component_sum_check':{'total_minus_retrieval_and_pack_ms':residual if checked else None,
            'rows_checked':checked,'rows_with_incomplete_components':count-checked,
            'scope':'unbatched row total = retrieval_total + pack; batch setup is outside row total'},
        'overlap_semantics':{'fts':'nested in sparse','query_embedding':'nested in retrieval_total',
            'dense_matrix_load':'nested in retrieval_total; shared in batched path',
            'dense_scoring':'includes transfer; shared in batched path',
            'fusion':'nested in retrieval_total','neighbor_expansion':'nested in retrieval_total',
            'row_materialization':'nested in retrieval_total','pack':'outside retrieval_total',
            'amortized_total':'alternative batched total, never add to total'},
        'orchestration_residual_ms':None,
        'interpretation':'Raw component sums are overlapping; E2E wall time is separately measured. Missing stages remain unmeasured.'}
