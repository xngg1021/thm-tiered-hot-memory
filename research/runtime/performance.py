"""Summaries retain nested timing scopes instead of adding overlapping clocks."""
from collections import Counter


def decomposition(artifact):
    totals=Counter();count=0;batch_rows=0
    for row in artifact.get('rows',[]):
        timing=row.get('timing_ms') or {}
        if not timing:continue
        count+=1;batch_rows+=int(bool(row.get('batch_receipt')))
        for name,value in timing.items():
            if type(value) in (float,int):totals[name]+=value
    return {'rows_with_timing':count,'rows_with_batch_receipt':batch_rows,
        'raw_stage_totals_ms':dict(totals),
        'component_sum_check':{'total_minus_retrieval_and_pack_ms':totals['total']-totals['retrieval_total']-totals['pack'],
            'scope':'unbatched row total = retrieval_total + pack; batch setup is outside row total'},
        'overlap_semantics':{'fts':'nested in sparse','query_embedding':'nested in retrieval_total',
            'dense_matrix_load':'nested in retrieval_total; shared in batched path',
            'dense_scoring':'includes transfer; shared in batched path',
            'fusion':'nested in retrieval_total','neighbor_expansion':'nested in retrieval_total',
            'row_materialization':'nested in retrieval_total','pack':'outside retrieval_total',
            'amortized_total':'alternative batched total, never add to total'},
        'orchestration_residual_ms':None,
        'interpretation':'Raw component sums are overlapping; E2E wall time is separately measured. Missing stages remain unmeasured.'}
