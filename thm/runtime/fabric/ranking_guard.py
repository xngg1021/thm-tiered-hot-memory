"""Bounded top-k certificate for an admitted exact FP32 dot-product profile."""
from bisect import bisect_left


def certify(matrix, ids, query, ranking, top_k, *, fp32_accumulation):
    import numpy as np
    from ..autotune import numeric_guard
    vector = np.asarray(query,dtype=np.float32)
    ranked, values = ranking
    width = min(len(ids),top_k+1)
    tolerance = numeric_guard(matrix.shape[1])*1.001  # normalized storage allows 1e-4 norm error
    rows_scored = 0; reason = 'unverified-accumulation'
    if fp32_accumulation and len(ranked) == len(values) == width and len(set(ranked)) == width:
        positions = [bisect_left(ids, row) for row in ranked]
        valid = all(pos < len(ids) and ids[pos] == row for pos,row in zip(positions,ranked))
        if valid and np.isfinite(values).all():
            # A cutoff witness covers omitted rows. Only selected rows plus one
            # are scored on the host; row IDs use the source's stable sorted order.
            scores = matrix[positions] @ vector
            rows_scored = width
            bounded = np.allclose(scores,values,atol=tolerance,rtol=0)
            separated = len(values) == 1 or bool(np.all(np.diff(np.asarray(values)) < -2*tolerance))
            host_separated = len(scores) == 1 or bool(np.all(np.diff(scores) < -2*tolerance))
            if bounded and separated and host_separated:
                return (list(ranked[:top_k]),[float(x) for x in scores[:top_k]]), {
                    'verification':'admitted-cutoff','reference_rows_scored':rows_scored,
                    'reference_full_scans':0,'cutoff_witness':width>top_k,'numeric_tolerance':tolerance}
            reason = 'ambiguous-cutoff-or-order' if bounded else 'numeric-envelope-exceeded'
        else:
            reason = 'invalid-provider-ranking'
    # Ties, overlapping error envelopes, unknown math mode or malformed output
    # require the original full singleton operation and stable source-row ties.
    scores = matrix @ vector
    order = np.argsort(-scores,kind='stable')[:top_k]
    return ([ids[int(i)] for i in order],[float(scores[i]) for i in order]), {
        'verification':'reference-fallback','reference_rows_scored':rows_scored+len(ids),
        'reference_full_scans':1,'fallback_reason':reason,'numeric_tolerance':tolerance}
