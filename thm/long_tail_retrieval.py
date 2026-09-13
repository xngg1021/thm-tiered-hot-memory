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
        self.allowed_source_ids=None
        self.matched_event_source_ids=frozenset()
        if graph is None:return channels
        if graph.scope!=scope:
            raise ValueError('event graph scope mismatch')
        rows={r['id']:r for r in self.rows(scope)}
        events_by_source={}
        for event in graph.events.values():
            if event.source_id not in rows or event.source_sha256!=rows[event.source_id]['hash']:
                raise ValueError('stale event representation/source identity')
            events_by_source.setdefault(event.source_id,[]).append(event)
        import re
        from thm.long_tail import TimeInterval
        category=classify_query(query)
        date_pattern=r'(\d{4}(?:-\d{2})?(?:-\d{2})?)'
        matches=re.findall(r'(?<![A-Za-z0-9])'+date_pattern+r'(?![A-Za-z0-9])',query)
        selected=()
        bounds={}
        for operation,value in re.findall(r'\b(after|before)\s+'+date_pattern,query,re.I):
            bounds.setdefault(operation.lower(),set()).add(value)
        for value,operation in re.findall(date_pattern+r'\s*(之后|之前)',query):
            bounds.setdefault('after' if operation=='之后' else 'before',set()).add(value)
        if 'after' in bounds and 'before' in bounds:
            if any(len(values)!=1 for values in bounds.values()):
                raise ValueError('ambiguous two-sided temporal bounds')
            lower=TimeInterval.parse(next(iter(bounds['after'])))
            upper=TimeInterval.parse(next(iter(bounds['before'])))
            if not lower.before(upper):raise ValueError('invalid two-sided temporal bounds')
            reference=TimeInterval(lower.start,upper.end,'range')
            selected=tuple(event for event in graph.select('date-range',reference)
                           if event.time.after(lower) and event.time.before(upper))
        elif matches:
            reference=TimeInterval.parse(matches[0])
            operation='closest-before' if 'closest before' in query.lower() else 'closest-after' if 'closest after' in query.lower() else \
                'before' if re.search(r'before|之前',query,re.I) else 'after' if re.search(r'after|之后',query,re.I) else 'date-range'
            if len(matches)>=2 and operation=='date-range':reference=TimeInterval.parse(matches[0]+'/'+matches[1])
            selected=graph.select(operation,reference)
        elif category=='ordering':
            if re.search(r'\bfirst\b|最早',query,re.I):selected=graph.select('first')
            elif re.search(r'\blast\b|最后',query,re.I):selected=graph.select('last')
            else:selected=tuple(sorted(graph.events.values(),key=lambda event:(event.time.start,event.time.end,event.identity)))
        elif category in ('update','contradiction','multi-hop'):
            selected=tuple(graph.events.values())
        sources=[];allowed=set()
        for event in selected[:candidate_limit]:
            chain=graph.required_chain(event.identity)
            self._bind_chain_requirements(chain)
            sources.extend(rows[e.source_id]['rowid'] for e in chain)
            allowed.update(e.source_id for e in chain)
        if matches or ('after' in bounds and 'before' in bounds) or category=='ordering':
            self.matched_event_source_ids=frozenset(event.source_id for event in selected[:candidate_limit])
            pending=list(allowed);visited=set()
            while pending:
                source=pending.pop()
                if source in visited:continue
                visited.add(source)
                # A complete document may contain several events. Preserve the
                # dependencies of every event carried by an admitted source.
                for event in events_by_source[source]:
                    chain=graph.required_chain(event.identity)
                    self._bind_chain_requirements(chain)
                    for parent in chain:
                        sources.append(rows[parent.source_id]['rowid'])
                        if parent.source_id not in allowed:
                            allowed.add(parent.source_id);pending.append(parent.source_id)
            self.allowed_source_ids=frozenset(allowed)
        if sources:channels.append(list(dict.fromkeys(sources))[:candidate_limit])
        return channels

    def _filter_candidates(self,rows):
        allowed=getattr(self,'allowed_source_ids',None)
        return rows if allowed is None else [row for row in rows if row['id'] in allowed]

    def _bind_chain_requirements(self,chain):
        # required_chain is topologically ordered. Bind every intermediate
        # event's own closure, including aliases sharing a source document.
        closures={}
        for event in chain:
            required={event.source_id}
            for parent in event.predecessor:required.update(closures[parent])
            closures[event.identity]=required
            self.required_source_sets[event.source_id]=self.required_source_sets.get(event.source_id,frozenset())|frozenset(required)

    def _pack_candidates(self, expanded, budget, query):
        graph=getattr(self,'event_graph',None)
        self.event_order_keys={}
        if graph is not None:
            source_ids={row['id'] for row in expanded}
            for event in graph.events.values():
                if event.source_id in source_ids:
                    self._bind_chain_requirements(graph.required_chain(event.identity))
                    key=(event.time.start.isoformat(),event.time.end.isoformat())
                    self.event_order_keys[event.source_id]=min(self.event_order_keys.get(event.source_id,key),key)
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
                self.long_tail_receipt = {'method': 'heuristic', 'reason': 'nonadditive-counter', 'query_class': category,
                                         'ordering_basis':'event-interval' if graph is not None else 'source-timestamp',
                                         'ordering_granularity':'complete-source-block'}
                return self._pack_dependency_closures(expanded,budget,query)
            overlap = query_terms & set(terms(row['text']))
            units = frozenset(overlap)
            required=getattr(self,'required_source_sets',{}).get(row['id'],frozenset())
            candidates.append(EvidenceCandidate(row['id'], len(block.encode())+2, 1/(rank+1), units,required))
        selection = joint_select(candidates, budget+2 if budget else 0)
        chosen = set(selection['ids'])
        rows = [row for row in expanded if row['id'] in chosen]
        if category == 'ordering':
            rows.sort(key=self._ordering_key)
        context, selected, units = super()._pack_candidates(rows, budget, query)
        self.long_tail_receipt = {'method': selection['method'], 'query_class': category,
                                 'ordering_basis':'event-interval' if graph is not None else 'source-timestamp',
                                 'ordering_granularity':'complete-source-block',
                                 'candidate_count': len(candidates), 'selection_ids': selection['ids'],
                                 'selected_evidence_count': len(selected), 'track': '0N', 'gold_used': False}
        return context, selected, units

    def _ordering_key(self,row):
        start,end=self.event_order_keys.get(row['id'],(row['timestamp'] or '',row['timestamp'] or ''))
        return (not bool(start),start,end,row['ord'],row['id'])

    def _pack_dependency_closures(self,expanded,budget,query):
        """Keep exact final counting while admitting every dependency group atomically."""
        by_id={row['id']:row for row in expanded}
        order={row['id']:position for position,row in enumerate(expanded)}
        required=getattr(self,'required_source_sets',{})
        chosen=[];selected_ids=set();result=('',[],0)
        for row in expanded:
            pending=[row['id']];group=set();missing=False
            while pending:
                key=pending.pop()
                if key in group or key in selected_ids:continue
                if key not in by_id:missing=True;break
                group.add(key);pending.extend(required.get(key,()))
            if missing or not group:continue
            proposal=chosen+[by_id[key] for key in sorted(group,key=order.get)]
            if classify_query(query)=='ordering':
                # Count the exact served order: nonadditive counters can change
                # cost when the same complete source blocks are rearranged.
                proposal.sort(key=self._ordering_key)
            packed=super()._pack_candidates(proposal,budget,query)
            if {item['id'] for item in packed[1]}!={item['id'] for item in proposal}:
                continue
            chosen=proposal;selected_ids={item['id'] for item in chosen};result=packed
        self.long_tail_receipt.update(dependencies_atomic=True,selection_ids=[row['id'] for row in chosen],
                                      selected_evidence_count=len(chosen),track='0N',gold_used=False)
        return result

    def _validate_search_options(self,scope,query,**kwargs):
        result=super()._validate_search_options(scope,query,**kwargs)
        if getattr(self,'event_graph',None) is not None and result[0].segment:
            raise ValueError('event dependencies require complete-source packing; segment packing is incompatible')
        return result

    def _search(self,scope,query,**kwargs):
        # search_many may prepare several lexical channels before serving any
        # row. Rebuild attached graph channels at the actual query boundary so
        # their source checks and dependency map belong to this query snapshot.
        prepared=getattr(self,'_batch_lexical',None)
        if getattr(self,'event_graph',None) is not None:self._batch_lexical=None
        self.long_tail_receipt={'method':'empty','track':'0N'}
        self.allowed_source_ids=None
        self.matched_event_source_ids=frozenset()
        try:
            result=super()._search(scope,query,**kwargs)
            self.long_tail_receipt['track']='0G' if result.get('semantic_encoder_used') else '0N'
            self.long_tail_receipt['source_constraint']={'active':self.allowed_source_ids is not None,
                'allowed_source_count':len(self.allowed_source_ids) if self.allowed_source_ids is not None else None,
                'required_dependency_sources_included':True,
                'selected_source_roles':{row['id']:('matched-event' if row['id'] in self.matched_event_source_ids else 'required-dependency')
                    for row in result.get('selected',[])} if self.allowed_source_ids is not None else {}}
            result['long_tail']=dict(self.long_tail_receipt)
            return result
        finally:self._batch_lexical=prepared

    def search(self, scope, query, **kwargs):
        # Receipts must not be borrowed from an unrelated cached query.
        with self._lock:
            self._results.clear()
            return super().search(scope, query, **kwargs)
