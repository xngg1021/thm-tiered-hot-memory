"""Pure LoCoMo scoring and economics denominator contracts."""
SCORABLE_DEFINITION = {
    "scope": "main_categories_1_to_4",
    "requires_gold_evidence": True,
    "requires_fully_resolved": True,
}


def is_scorable(row):
    return bool(row.get("evidence_count", 0) > 0 and row.get("fully_resolved", False))


def validate_denominators(source, per_config, totals):
    expected = {f"{mode}@{budget}" for mode in source["modes"] for budget in source["budgets"]}
    if not expected or set(per_config) != expected or set(source.get("summaries", {})) != expected:
        raise ValueError("denominator contract: configuration keys do not match")
    attempted, scorable = [], []
    for key in sorted(expected):
        summary = source["summaries"][key].get("main_categories_1_to_4", {})
        cfg = per_config[key]
        a, s = summary.get("questions"), summary.get("scorable")
        if type(a) is not int or type(s) is not int or not 0 <= s <= a:
            raise ValueError(f"denominator contract: invalid canonical summary {key}")
        if cfg.get("attempted_questions") != a or cfg.get("scorable_questions") != s:
            raise ValueError(f"denominator contract: attempted/scorable mismatch {key}")
        full = cfg.get("full_history_same_query_counterfactual")
        if full is not None and (not isinstance(full, dict) or full.get("attempted_questions") != a):
            raise ValueError(f"denominator contract: full-history attempted mismatch {key}")
        attempted.append(a)
        scorable.append(s)
    def cohort(values):
        unique = sorted(set(values))
        return unique[0] if len(unique) == 1 else unique
    expected_totals = {
        "config_count": len(expected), "config_query_executions": sum(attempted),
        "scorable_config_query_executions": sum(scorable),
        "attempted_questions_per_config": cohort(attempted),
        "scorable_questions_per_config": cohort(scorable),
    }
    for key, value in expected_totals.items():
        if totals.get(key) != value:
            raise ValueError(f"denominator contract: suite total mismatch {key}")
