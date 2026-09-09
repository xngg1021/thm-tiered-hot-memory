"""Measured candidate deltas for mismatching queries; absent scores stay unknown."""
from research.recall.hardware_parity import row_key


def score_deltas(reference,candidate, maximum_rows=50, maximum_candidates=64):
    if maximum_rows<1 or maximum_candidates<1:raise ValueError("positive forensic bounds required")
    left={row_key(r,i):r for i,r in enumerate(reference['rows'])}
    right={row_key(r,i):r for i,r in enumerate(candidate['rows'])}
    out=[];total=0
    def priority(key):
        # Strict evidence changes must not be crowded out by numeric-only rows.
        same=all(left[key].get(field)==right[key].get(field) for field in ('selected_ids','selected_ranked_ids','budget_used','packed_selections'))
        return same,repr(key)
    for key in sorted(set(left)&set(right),key=priority):
        a,b=left[key],right[key]
        da,db=a.get('runtime_diagnostics') or {},b.get('runtime_diagnostics') or {}
        def scores(d):
            ids,values=d.get('candidate_ids'),d.get('scores')
            if not isinstance(ids,list) or not isinstance(values,list) or len(ids)!=len(values):return {}
            if len(set(ids))!=len(ids):raise ValueError('duplicate candidate score identity')
            return dict(zip(ids,values))
        sa,sb=scores(da),scores(db)
        same_selection=all(a.get(field)==b.get(field) for field in ('selected_ids','selected_ranked_ids','budget_used','packed_selections'))
        if same_selection and sa==sb and da.get('candidate_ids')==db.get('candidate_ids'):continue
        total+=1
        if len(out)>=maximum_rows:continue
        entries=[]
        ar=a.get('selected_ranked_ids',a.get('selected_ids',[]));br=b.get('selected_ranked_ids',b.get('selected_ids',[]))
        def position(values,identifier):return values.index(identifier)+1 if identifier in values else None
        for identifier in sorted(set(sa)|set(sb))[:maximum_candidates]:
            x,y=sa.get(identifier),sb.get(identifier)
            entries.append({'candidate_id':identifier,'reference_score':x,'candidate_score':y,'score_delta':y-x if x is not None and y is not None else None,
                'reference_dense_score':x,'candidate_dense_score':y,
                'reference_dense_rank':position(da.get('candidate_ids',[]),identifier),
                'candidate_dense_rank':position(db.get('candidate_ids',[]),identifier),
                'reference_selected':identifier in ar,'candidate_selected':identifier in br,
                'reference_selected_rank':position(ar,identifier),'candidate_selected_rank':position(br,identifier),
                'reference_sparse_component':(da.get('sparse_components') or {}).get(identifier),
                'candidate_sparse_component':(db.get('sparse_components') or {}).get(identifier),
                'reference_fused_score':(da.get('fused_scores') or {}).get(identifier),
                'candidate_fused_score':(db.get('fused_scores') or {}).get(identifier)})
        out.append({'query_identity':dict(key),'status':'measured' if sa and sb else 'missing-score-evidence',
            'reference_embedding_profile':da.get('embedding_profile_id'),'candidate_embedding_profile':db.get('embedding_profile_id'),
            'reference_scorer':da.get('scorer'),'candidate_scorer':db.get('scorer'),
            'reference_selected':a.get('selected_ranked_ids',a.get('selected_ids')),
            'candidate_selected':b.get('selected_ranked_ids',b.get('selected_ids')),
            'mode':a.get('mode'),'cutoff_position':{'reference':len(ar),'candidate':len(br)},
            'packing_boundary':{'reference':a.get('budget_used'),'candidate':b.get('budget_used')},
            'component_status':'dense measured when present; sparse/fused unavailable in legacy receipts',
            'candidate_count':len(set(sa)|set(sb)),'candidates_truncated':len(set(sa)|set(sb))>maximum_candidates,
            'budget':a.get('budget'),'reference_budget_used':a.get('budget_used'),'candidate_budget_used':b.get('budget_used'),
            'reference_feature_components':da.get('feature_components'),'candidate_feature_components':db.get('feature_components'),
            'scores':entries,'root_cause':'not inferred from proximity alone'})
    return {'schema':1,'mismatching_queries':total,'rows_truncated':total>len(out),'queries':out,'epsilon_tie_policy_changed':False}
