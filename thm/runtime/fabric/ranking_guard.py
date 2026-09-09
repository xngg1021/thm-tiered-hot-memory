"""Provider-independent strict verification for exact FP32 dot-product candidates.

A provider's own top-k or top-k+1 output cannot certify that it did not omit a
higher-scoring source row. Until THM has an independent upper-bound certificate
covering every omitted row, strict serving obtains its result from the complete
stable host reference scan. This deliberately prefers correctness to an
unproven steady-state acceleration claim.
"""


def certify(matrix, ids, query, ranking, top_k, *, fp32_accumulation):
    import numpy as np
    from ..autotune import numeric_guard

    vector = np.asarray(query, dtype=np.float32)
    if vector.ndim != 1 or matrix.shape[1] != vector.shape[0] or not np.isfinite(vector).all():
        raise ValueError('invalid strict-verification query')
    if type(top_k) is not int or not 1 <= top_k <= len(ids):
        raise ValueError('invalid strict-verification top-k')

    tolerance = numeric_guard(matrix.shape[1]) * 1.001
    ranked, values = ranking
    provider_shape_valid = (len(ranked) == len(values) and len(ranked) >= top_k
                            and len(set(ranked)) == len(ranked))
    provider_numeric_valid = False
    if provider_shape_valid:
        try:
            provider_numeric_valid = bool(np.isfinite(np.asarray(values, dtype=np.float64)).all())
        except (TypeError, ValueError):
            provider_numeric_valid = False

    # Strict completeness must be independent of the candidate provider. The
    # stable source-row scan is the authority until an independent omitted-row
    # upper bound is implemented and separately reviewed.
    scores = matrix @ vector
    order = np.argsort(-scores, kind='stable')[:top_k]
    reference_ids = [ids[int(i)] for i in order]
    reference_scores = [float(scores[i]) for i in order]

    provider_top_ids = list(ranked[:top_k]) if provider_shape_valid else []
    provider_top_scores = list(values[:top_k]) if provider_numeric_valid else []
    provider_matches_reference = (
        fp32_accumulation and provider_shape_valid and provider_numeric_valid
        and provider_top_ids == reference_ids
        and np.allclose(provider_top_scores, reference_scores, atol=tolerance, rtol=0)
    )

    return (reference_ids, reference_scores), {
        'verification': 'reference-fallback',
        'reference_rows_scored': len(ids),
        'reference_full_scans': 1,
        'provider_matches_reference': bool(provider_matches_reference),
        'fallback_reason': 'provider-independent-completeness-required',
        'numeric_tolerance': tolerance,
        'independent_omitted_row_bound': False,
    }
