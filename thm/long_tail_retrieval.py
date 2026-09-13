"""Opt-in long-tail serving path using the existing scoped snapshot engine."""
import json
from thm.retrieval import SearchIndex, terms
from thm.long_tail import EvidenceCandidate, classify_query, joint_select


class LongTailSearchIndex(SearchIndex):
    def attach_events(self, graph):
        """Explicit source-derived metadata, checked again on every read snapshot."""
        self.event_graph=graph
        self._results.clear()

    def _lexical_channels(self,scope,query,mode,candidate_limit):
        channels=super()._lexical_channels(scope,query,mode,candidate_limit)
        graph=getattr(self,'event_graph',None)
        self.required_source_sets={}
        if graph is None:return channels
        if graph.scope!=scope:
            raise ValueError('event graph scope mismatch')
        rows={r['id']:r for r in self.rows(scope)}
        for event in graph.events.values():
            if event.source_id not in rows or event.source_sha256!=rows[event.source_id]['hash']:
                raise ValueError('stale event representation/source identity')
        import re
        from thm.long_tail import TimeInterval
        category=classify_query(query)
        matches=re.findall(r'\b\d{4}(?:-\d{2})?(?:-\d{2})?\b',query)
        selected=()
        if matches:
            reference=TimeInterval.parse(matches[0])
            operation='closest-before' if 'closest before' in query.lower() else 'closest-after' if 'closest after' in query.lower() else \
                'before' if re.search(r'before|之前',query,re.I) else 'after' if re.search(r'after|之后',query,re.I) else 'date-range'
            if len(matches)>=2 and operation=='date-range':reference=TimeInterval.parse(matches[0]+'/'+matches[1])
            selected=graph.select(operation,reference)
        elif category=='ordering':
            selected=graph.select('first' if re.search(r'first|最早',query,re.I) else 'last')
        elif category in ('update','contradiction','multi-hop'):
            selected=tuple(graph.events.values())
        sources=[]
        for event in selected[:candidate_limit]:
            chain=graph.required_chain(event.identity)
            required=frozenset(e.source_id for e in chain)
            self.required_source_sets[event.source_id]=required
            sources.extend(rows[e.source_id]['rowid'] for e in chain)
        if sources:channels.append(list(dict.fromkeys(sources))[:candidate_limit])
        return channels

    def _pack_candidates(self, expanded, budget, query):
        category = classify_query(query)
        query_terms = set(terms(query))
        candidates, blocks = [], {}
        for rank, row in enumerate(expanded):
            label = json.dumps({'id': row['id'], 'speaker': row['speaker'], 'date': row['timestamp']}, ensure_ascii=False)
            block = f"[source {label}]\n{row['text']}"
            blocks[row['id']] = block
            # Exact additivity is available for the native UTF-8 counter only.
            # Tokenizer and caller counters use the existing exact final packer.
            from thm.retrieval import TokenCounter
            if type(self.counter) is not TokenCounter or self.counter.encode is not None:
                self.long_tail_receipt = {'method': 'heuristic', 'reason': 'nonadditive-counter', 'query_class': category}
                return super()._pack_candidates(expanded, budget, query)
            overlap = query_terms & set(terms(row['text']))
            units = frozenset(overlap)
            required=getattr(self,'required_source_sets',{}).get(row['id'],frozenset())
            candidates.append(EvidenceCandidate(row['id'], len(block.encode())+2, 1/(rank+1), units,required))
        selection = joint_select(candidates, budget+2 if budget else 0)
        chosen = set(selection['ids'])
        rows = [row for row in expanded if row['id'] in chosen]
        if category == 'ordering':
            rows.sort(key=lambda row: (row['timestamp'] or '', row['ord'], row['id']))
        context, selected, units = super()._pack_candidates(rows, budget, query)
        self.long_tail_receipt = {'method': selection['method'], 'query_class': category,
                                 'candidate_count': len(candidates), 'selection_ids': selection['ids'],
                                 'selected_evidence_count': len(selected), 'track': '0N', 'gold_used': False}
        return context, selected, units

    def search(self, scope, query, **kwargs):
        # Receipts must not be borrowed from an unrelated cached query.
        with self._lock:
            self._results.clear()
            self.long_tail_receipt = {'method': 'empty', 'track': '0N'}
            result = super().search(scope, query, **kwargs)
            result['long_tail'] = dict(self.long_tail_receipt)
            return result
