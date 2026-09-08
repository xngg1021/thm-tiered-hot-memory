"""Measured candidate deltas for mismatching queries; absent scores stay unknown."""
from research.recall.hardware_parity import row_key


def score_deltas(reference,candidate):
    left={row_key(r,i):r for i,r in enumerate(reference['rows'])}
    right={row_key(r,i):r for i,r in enumerate(candidate['rows'])}
    out=[]
    for key in sorted(set(left)&set(right),key=repr):
        a,b=left[key],right[key]
        if all(a.get(field)==b.get(field) for field in ('selected_ids','selected_ranked_ids','budget_used')):continue
        da,db=a.get('runtime_diagnostics') or {},b.get('runtime_diagnostics') or {}
        def scores(d):
            ids,values=d.get('candidate_ids'),d.get('scores')
            if not isinstance(ids,list) or not isinstance(values,list) or len(ids)!=len(values):return {}
            if len(set(ids))!=len(ids):raise ValueError('duplicate candidate score identity')
            return dict(zip(ids,values))
        sa,sb=scores(da),scores(db)
        entries=[]
        for identifier in sorted(set(sa)|set(sb)):
            x,y=sa.get(identifier),sb.get(identifier)
            entries.append({'candidate_id':identifier,'reference_score':x,'candidate_score':y,'score_delta':y-x if x is not None and y is not None else None})
        out.append({'query_identity':dict(key),'status':'measured' if sa and sb else 'missing-score-evidence',
            'reference_embedding_profile':da.get('embedding_profile_id'),'candidate_embedding_profile':db.get('embedding_profile_id'),
            'reference_scorer':da.get('scorer'),'candidate_scorer':db.get('scorer'),
            'reference_selected':a.get('selected_ranked_ids',a.get('selected_ids')),
            'candidate_selected':b.get('selected_ranked_ids',b.get('selected_ids')),
            'budget':a.get('budget'),'reference_budget_used':a.get('budget_used'),'candidate_budget_used':b.get('budget_used'),
            'reference_feature_components':da.get('feature_components'),'candidate_feature_components':db.get('feature_components'),
            'scores':entries,'root_cause':'not inferred from proximity alone'})
    return {'schema':1,'mismatching_queries':len(out),'queries':out,'epsilon_tie_policy_changed':False}
