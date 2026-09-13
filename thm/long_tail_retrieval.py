"""Opt-in long-tail serving path using the existing scoped snapshot engine."""
import json
from thm.retrieval import SearchIndex, terms
from thm.long_tail import EvidenceCandidate, classify_query, joint_select


class LongTailSearchIndex(SearchIndex):
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
            candidates.append(EvidenceCandidate(row['id'], len(block.encode())+2, 1/(rank+1), units))
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
