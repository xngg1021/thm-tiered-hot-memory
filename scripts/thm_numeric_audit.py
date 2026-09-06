#!/usr/bin/env python3
"""Reproduce numeric checks of the public THM specification.

Scope: xngg1021/thm-tiered-hot-memory at
3fc7d6c438e167c384f20697cc1c0642d3de9e8a.
This does not import or test the private thm.py implementation.
No network access, third-party dependencies, or personal memory data.
Run: python thm_numeric_audit.py
"""
from __future__ import annotations

import json
import math
from typing import Iterable
import unittest

Event = tuple[float, float]  # age in days, positive event weight


def activation(events: Iterable[Event], smoothing: float = 1.0) -> float:
    """Weighted power score in the public specification, using d=0.5."""
    if not math.isfinite(smoothing) or smoothing < 0:
        raise ValueError("smoothing must be finite and nonnegative")
    total = 0.0
    for age, weight in events:
        if not math.isfinite(age) or not math.isfinite(weight):
            raise ValueError("age and weight must be finite")
        if age < 0 or weight < 0 or age + smoothing <= 0:
            raise ValueError("invalid event age or weight")
        total += weight / math.sqrt(age + smoothing)
    return total


def specified_t0_demotion(age: int, score: float, cost_class: str) -> bool:
    """Direct transcription of the documented rule, not the private engine."""
    return score < 0.6 and age > 21 and cost_class != "high"


def results() -> dict:
    old = activation([(90, 1), (88, 2), (89, 2), (90, 2)])
    recent = activation([(90, 1), (0, 2), (1, 2), (2, 2)])
    first_daily = next(t for t in range(100)
                       if specified_t0_demotion(t, activation([(t, 1)]), "low"))
    first_weekly = next(t for t in range(0, 100, 7)
                        if specified_t0_demotion(t, activation([(t, 1)]), "low"))
    return {
        "scope": "Public specification arithmetic and rule transcription only",
        "repo_commit": "3fc7d6c438e167c384f20697cc1c0642d3de9e8a",
        "citation_growth_baddeley_openalex_percent": (7293 / 5261 - 1) * 100,
        "create_only": {str(t): activation([(t, 1)]) for t in (0, 1, 2, 21, 22, 28, 90)},
        "create_day0_hit_day1_evaluated_day1": activation([(1, 1), (0, 2)]),
        "three_hits_old_within_inclusive_90_day_window": old,
        "three_hits_recent_within_same_window": recent,
        "smoothing_rank_reversal": {
            "raw_A_age1": activation([(1, 1)], smoothing=0),
            "raw_B_two_age5": activation([(5, 1), (5, 1)], smoothing=0),
            "smooth_A_age1": activation([(1, 1)]),
            "smooth_B_two_age5": activation([(5, 1), (5, 1)]),
        },
        "first_daily_demotion_day_create_only": first_daily,
        "first_weekly_demotion_day_checks_at_multiples_of_7": first_weekly,
        "exponential_day90_if_rate_0_05_per_day": math.exp(-0.05 * 90),
        "high_class_demotes_under_published_rule": specified_t0_demotion(1000, 0.001, "high"),
    }


class SpecificationChecks(unittest.TestCase):
    def test_create_only(self):
        self.assertAlmostEqual(activation([(2, 1)]), 1 / math.sqrt(3))

    def test_create_and_next_day_hit(self):
        self.assertAlmostEqual(activation([(1, 1), (0, 2)]), 2 + 1 / math.sqrt(2))

    def test_log_monotonic_for_same_positive_score(self):
        self.assertGreater(math.log(1.0), math.log(2 / math.sqrt(5)))

    def test_plus_one_can_reverse_ranking(self):
        self.assertGreater(activation([(1, 1)], 0), activation([(5, 1), (5, 1)], 0))
        self.assertLess(activation([(1, 1)]), activation([(5, 1), (5, 1)]))

    def test_three_hits_do_not_define_unique_activation(self):
        self.assertNotAlmostEqual(
            activation([(90, 1), (88, 2), (89, 2), (90, 2)]),
            activation([(90, 1), (0, 2), (1, 2), (2, 2)]),
        )

    def test_age_strict_inequality(self):
        self.assertFalse(specified_t0_demotion(21, activation([(21, 1)]), "low"))
        self.assertTrue(specified_t0_demotion(22, activation([(22, 1)]), "low"))

    def test_high_class_eviction_immunity(self):
        self.assertFalse(specified_t0_demotion(1000, 0.001, "high"))

    def test_published_citation_growth_not_one_percent(self):
        self.assertGreater((7293 / 5261 - 1) * 100, 38)

    def test_exponential_comparison_requires_rate(self):
        self.assertAlmostEqual(math.exp(-0.05 * 90), 0.011108996538242306)

    def test_invalid_event_rejected(self):
        with self.assertRaises(ValueError):
            activation([(-1, 1)])


if __name__ == "__main__":
    print(json.dumps(results(), indent=2, ensure_ascii=False), flush=True)
    unittest.main(verbosity=2)
