"""Disjoint primary drift classes; category-five is an orthogonal cohort."""
from research.recall.hardware_parity import row_key, SEMANTIC_FIELDS
from collections import Counter
import json


def classify(a,b):
    changed={k for k in SEMANTIC_FIELDS if a.get(k)!=b.get(k)}
    if not changed:
        da=a.get('runtime_diagnostics') or {};db=b.get('runtime_diagnostics') or {}
        if da.get('scores')!=db.get('scores'):return 'numeric-only'
        return 'diagnostic-only' if da!=db else 'identical'
    if set(a.get('selected_ids',[]))!=set(b.get('selected_ids',[])):return 'selected-set-change'
    if changed=={'selected_ranked_ids'}:return 'rank-only'
    if changed <= {'selected_ranked_ids','packed_selections','selected_ids','selected_sources'}:
        left=a.get('packed_selections');right=b.get('packed_selections')
        if isinstance(left,list) and isinstance(right,list) and sorted(map(lambda x:json.dumps(x,sort_keys=True),left))==sorted(map(lambda x:json.dumps(x,sort_keys=True),right)):
            return 'same-set-different-order'
    if changed & {'packed_selections','budget_used'}:return 'packed-boundary-change'
    return 'other-semantic-change'


def taxonomy(reference,candidate):
    a={row_key(r,i):r for i,r in enumerate(reference['rows'])}
    b={row_key(r,i):r for i,r in enumerate(candidate['rows'])}
    counts=Counter(classify(a[k],b[k]) if k in a and k in b else 'other-semantic-change' for k in set(a)|set(b))
    return {'primary_counts':dict(counts),'rows_accounted':sum(counts.values()),
        'count_semantics':'disjoint primary categories; diagnostic-only category 5 remains an orthogonal cohort'}
