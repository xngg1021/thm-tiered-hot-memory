"""Evaluator-only candidate/oracle/ranking/packing decomposition."""
from dataclasses import dataclass
from thm.long_tail import EvidenceCandidate, joint_select
from thm.systems.contracts import integer

REPRESENTATION_FAILURES = ('lexical-ambiguity', 'missing-entity-relation', 'temporal-ambiguity',
                           'semantic-mismatch', 'unresolved-coreference')
ANNOTATION_ISSUES = ('multiple-valid-evidence', 'missing-gold', 'parent-child-mismatch',
                     'requires-inference', 'ambiguous-question')


def _oracle(candidates, gold, budget, max_states=100000):
    """Exact coverage mask DP with an explicit inexact lower bound on overflow."""
    ids = {key: n for n, key in enumerate(sorted(gold))}
    states = {0: 0}
    exact = True
    for candidate in candidates:
        mask = sum(1 << ids[key] for key in candidate.units & gold)
        if not mask:
            continue
        updated = dict(states)
        for covered, used in states.items():
            if used + candidate.cost <= budget:
                combined = covered | mask
                updated[combined] = min(updated.get(combined, budget+1), used+candidate.cost)
        if len(updated) > max_states:
            exact = False
            updated = dict(sorted(updated.items(), key=lambda pair: (-pair[0].bit_count(), pair[1], pair[0]))[:max_states])
        states = updated
    maximum = max((mask.bit_count() for mask in states), default=0)
    return {'covered_units': maximum, 'any_gold': maximum > 0, 'all_gold': bool(gold) and maximum == len(gold),
            'method': 'exact' if exact else 'heuristic', 'ceiling_valid': exact,
            'lower_bound_only': not exact, 'states': len(states)}


@dataclass(frozen=True)
class RetrievalCeilingReport:
    task_id: str
    gold: frozenset[str]
    candidates: tuple[EvidenceCandidate, ...]
    ranked_ids: tuple[str, ...]
    packed_ids: tuple[str, ...]
    budget: int
    representation_loss: tuple[str, ...] = ()
    annotation_ambiguity: tuple[str, ...] = ()

    def public(self):
        integer(self.budget, maximum=1048576)
        if len(self.gold) > 256 or len(self.candidates) > 1000:
            raise ValueError('bounded ceiling input required')
        if not set(self.representation_loss) <= set(REPRESENTATION_FAILURES) or not set(self.annotation_ambiguity) <= set(ANNOTATION_ISSUES):
            raise ValueError('unknown annotated failure class')
        by_id = {c.identity: c for c in self.candidates}
        if len(by_id) != len(self.candidates):
            raise ValueError('duplicate candidate')
        if len(set(self.ranked_ids)) != len(self.ranked_ids) or len(set(self.packed_ids)) != len(self.packed_ids):
            raise ValueError('duplicate selected identity')
        if not set(self.packed_ids) <= set(self.ranked_ids) <= set(by_id):
            raise ValueError('candidate/ranked/packed identity mismatch')
        if sum(by_id[key].cost for key in self.packed_ids) > self.budget:
            raise ValueError('packed evidence exceeds declared budget')
        available = set().union(*(c.units for c in self.candidates)) if self.candidates else set()
        ranked = tuple(by_id[key] for key in self.ranked_ids)
        packed = set().union(*(by_id[key].units for key in self.packed_ids)) if self.packed_ids else set()
        oracle = _oracle(self.candidates, self.gold, self.budget)
        rank_oracle = _oracle(ranked, self.gold, self.budget)
        accepted = len(packed & self.gold)
        valid = oracle['ceiling_valid'] and rank_oracle['ceiling_valid']
        return {'schema': 'thm-retrieval-ceiling/1', 'task_id': self.task_id, 'gold_units': len(self.gold),
            'candidate_ceiling': {'covered_units': len(available & self.gold), 'any_gold': bool(available & self.gold),
                                  'all_gold': bool(self.gold) and self.gold <= available},
            'budget_oracle': oracle, 'ranked_budget_oracle': rank_oracle,
            'ranking_loss': oracle['covered_units']-rank_oracle['covered_units'] if valid else None,
            'packing_loss': rank_oracle['covered_units']-accepted if valid else None,
            'selected_coverage': accepted, 'representation_loss': list(self.representation_loss),
            'annotation_ambiguity': list(self.annotation_ambiguity), 'generation_calls': 0, 'judge_calls': 0,
            'representation_loss_automatically_estimated': False, 'gold_used_for_serving': False}
