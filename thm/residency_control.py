"""Shadow T0 residency, speculative prefetch and budget recommendations for THM."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import math
from typing import Any, Callable, Mapping, Sequence

from ._residency_common import (
    PREFETCH_MODES, VALID_COST_CLASS, VALID_TIERS, ResidencyError, _entry_current,
    _entry_locator, _nonempty, _nonnegative_int, _nonnegative_number,
    _positive_int, _unit_interval,
)


@dataclass(frozen=True)
class ShadowPlanConfig:
    horizon_tasks: int = 20
    min_tasks: int = 20
    min_item_demands: int = 1
    candidate_tiers: tuple[str, ...] = ("T1",)
    complete_coverage: bool = False
    stale_failure_blocks: bool = True

    def __post_init__(self):
        _positive_int(self.horizon_tasks, "horizon_tasks")
        _nonnegative_int(self.min_tasks, "min_tasks")
        _nonnegative_int(self.min_item_demands, "min_item_demands")
        if not isinstance(self.candidate_tiers, tuple) or not self.candidate_tiers:
            raise ResidencyError("candidate_tiers: expected non-empty tuple")
        if any(t not in VALID_TIERS - {"T0"} for t in self.candidate_tiers):
            raise ResidencyError("candidate_tiers: only T1/T2/T3 candidates are supported")
        if type(self.complete_coverage) is not bool or type(self.stale_failure_blocks) is not bool:
            raise ResidencyError("coverage/stale flags must be boolean")


def _activity_score(entry: Mapping[str, Any], now: date,
                    activity_fn: Callable[[Mapping[str, Any], date], float] | None) -> float:
    if activity_fn is None:
        return 0.0
    value = activity_fn(entry, now)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise ResidencyError("activity_fn: expected finite nonnegative score")
    return float(value)


def _item_resident_units(entry: Mapping[str, Any],
                         unit_cost: Callable[[Mapping[str, Any]], int | None]) -> int | None:
    explicit = entry.get("resident_units")
    if explicit is not None:
        return _positive_int(explicit, "resident_units")
    value = unit_cost(entry)
    return None if value is None else _positive_int(value, "resident_units")


def shadow_residency_plan(entries: Sequence[Mapping[str, Any]], telemetry: Mapping[str, Any], *,
                          now: date, budget: int,
                          unit_cost: Callable[[Mapping[str, Any]], int | None],
                          config: ShadowPlanConfig = ShadowPlanConfig(),
                          activity_fn: Callable[[Mapping[str, Any], date], float] | None = None) -> dict[str, Any]:
    """Recommend a T0 set without applying a tier move or changing activity."""
    if type(budget) is not int or budget < 0:
        raise ResidencyError("budget: expected nonnegative integer")
    if not isinstance(telemetry, Mapping):
        raise ResidencyError("telemetry: expected aggregate object")
    task_count = telemetry.get("tasks")
    if isinstance(task_count, bool) or not isinstance(task_count, int) or task_count < 0:
        raise ResidencyError("telemetry.tasks: expected nonnegative integer")
    item_stats = telemetry.get("items", {})
    if not isinstance(item_stats, Mapping):
        raise ResidencyError("telemetry.items: expected object")

    seen: set[str] = set(); rows: list[dict[str, Any]] = []; excluded: list[dict[str, str]] = []
    current_ids: set[str] = set(); current_units: dict[str, int] = {}; uncosted_current: list[str] = []
    for raw in entries:
        if not isinstance(raw, Mapping): raise ResidencyError("entry: expected object")
        item_id = _nonempty(raw.get("id"), "entry id")
        if item_id in seen: raise ResidencyError("duplicate entry id")
        seen.add(item_id); tier = raw.get("tier")
        if tier not in VALID_TIERS: raise ResidencyError("entry tier: unsupported")
        if tier != "T0" and tier not in config.candidate_tiers: continue
        if not _entry_current(raw, now):
            excluded.append({"item_id": item_id, "reason": "status_or_validity"}); continue
        if tier == "T0": current_ids.add(item_id)
        pinned = raw.get("pinned", False)
        if type(pinned) is not bool: raise ResidencyError("pinned: expected boolean")
        cost_class = raw.get("cost_class", "med")
        if cost_class not in VALID_COST_CLASS: raise ResidencyError("cost_class: unsupported")
        units = _item_resident_units(raw, unit_cost)
        if units is None:
            excluded.append({"item_id": item_id, "reason": "missing_resident_cost"})
            if tier == "T0": uncosted_current.append(item_id)
            continue
        if tier == "T0": current_units[item_id] = units
        stats = item_stats.get(item_id, {})
        if not isinstance(stats, Mapping): raise ResidencyError(f"telemetry.items[{item_id}]: expected object")
        demand = stats.get("observed_need_events", 0); misses = stats.get("observed_miss_events", 0)
        stale = stats.get("stale_resident_failures", 0); miss_tokens = stats.get("miss_extra_tokens", 0)
        for value, field in ((demand,"observed_need_events"),(misses,"observed_miss_events"),
                             (stale,"stale_resident_failures"),(miss_tokens,"miss_extra_tokens")):
            _nonnegative_int(value, field)
        demand_tasks = stats.get("demand_task_ids", [])
        if not isinstance(demand_tasks, list) or any(not isinstance(v, str) for v in demand_tasks):
            raise ResidencyError("demand_task_ids: expected string list")
        need_rate = 0.0 if task_count == 0 else len(set(demand_tasks)) / task_count
        miss_rate = 0.0 if demand == 0 else misses / demand
        explicit_penalty = raw.get("miss_penalty_tokens")
        if explicit_penalty is not None:
            avg_miss = _nonnegative_number(explicit_penalty, "miss_penalty_tokens"); basis = "catalog"
        elif misses:
            avg_miss = miss_tokens / misses; basis = "observed_miss_average"
        else:
            avg_miss = None; basis = "unknown"
        measurable_need = demand >= config.min_item_demands
        zero_is_evidence = config.complete_coverage and task_count >= config.min_tasks
        uncertain = False
        if avg_miss is None:
            if tier == "T0" and (not zero_is_evidence or measurable_need): uncertain = True
            expected_saved = net = density = None
        else:
            empirical_miss_rate = miss_rate if demand else (1.0 if tier != "T0" else 0.0)
            expected_misses = need_rate * config.horizon_tasks * empirical_miss_rate
            if basis == "catalog" and demand and misses == 0 and tier != "T0":
                expected_misses = need_rate * config.horizon_tasks
            expected_saved = expected_misses * avg_miss
            net = expected_saved - units * config.horizon_tasks
            density = net / units
        rows.append({
            "item_id": item_id, "tier": tier, "pinned": pinned, "resident_units": units,
            "cost_class": cost_class, "activity_score": _activity_score(raw, now, activity_fn),
            "observed_need_events": demand, "observed_miss_events": misses,
            "need_task_rate": need_rate, "miss_rate": miss_rate if demand else None,
            "avg_miss_extra_tokens": avg_miss, "miss_penalty_basis": basis,
            "expected_saved_tokens_horizon": expected_saved,
            "resident_carry_tokens_horizon": units * config.horizon_tasks,
            "net_token_value_horizon": net, "net_token_value_density": density,
            "stale_resident_failures": stale, "uncertain": uncertain,
        })

    if uncosted_current:
        return {"status":"UNCOSTED_CURRENT_RESIDENT","budget":budget,"selected":sorted(current_ids),
                "retain":sorted(current_ids),"admit":[],"evict":[],"rows":sorted(rows,key=lambda r:r["item_id"]),
                "excluded":excluded,"review_required":[{"item_id":i,"reason":"missing_resident_cost"} for i in sorted(uncosted_current)],
                "changes_applied":False,"config":asdict(config),
                "warning":"current T0 cost is incomplete; no placement change is recommended"}

    fixed: list[dict[str, Any]] = []; candidates: list[dict[str, Any]] = []; review: list[dict[str, str]] = []
    for row in rows:
        if row["stale_resident_failures"] and config.stale_failure_blocks:
            review.append({"item_id":row["item_id"],"reason":"stale_resident_failure"}); continue
        if row["pinned"]:
            fixed.append(row); continue
        if row["uncertain"] and row["tier"] == "T0":
            fixed.append(row); review.append({"item_id":row["item_id"],"reason":"counterfactual_miss_cost_unknown"}); continue
        if row["net_token_value_horizon"] is not None and row["net_token_value_horizon"] > 0:
            candidates.append(row)
        elif row["tier"] == "T0" and not config.complete_coverage:
            fixed.append(row); review.append({"item_id":row["item_id"],"reason":"telemetry_coverage_incomplete"})
    fixed.sort(key=lambda r:r["item_id"]); fixed_units = sum(r["resident_units"] for r in fixed)
    if fixed_units > budget:
        return {"status":"PROTECTED_OVER_BUDGET","budget":budget,"required":fixed_units,
                "selected":[r["item_id"] for r in fixed],"rows":sorted(rows,key=lambda r:r["item_id"]),
                "excluded":excluded,"review_required":sorted(review,key=lambda r:(r["item_id"],r["reason"])),
                "changes_applied":False,"config":asdict(config)}
    candidates.sort(key=lambda r:(-(r["net_token_value_density"] if r["net_token_value_density"] is not None else -math.inf),
                                  -r["activity_score"], -{"low":1,"med":2,"high":3}[r["cost_class"]], r["item_id"]))
    selected = list(fixed); used = fixed_units; blocked: list[dict[str, Any]] = []
    for row in candidates:
        if used + row["resident_units"] <= budget:
            selected.append(row); used += row["resident_units"]
        else:
            blocked.append({"item_id":row["item_id"],"reason":"budget","resident_units":row["resident_units"]})
    selected_ids = {r["item_id"] for r in selected}; admit = sorted(selected_ids-current_ids)
    evict = sorted(current_ids-selected_ids); retain = sorted(current_ids&selected_ids)
    insufficient = task_count < config.min_tasks
    return {
        "status":"INSUFFICIENT_TELEMETRY" if insufficient else "OK", "evidence":"shadow_token_objective",
        "budget":budget, "budget_used":sum(current_units.values()) if insufficient else used,
        "selected":sorted(current_ids) if insufficient else sorted(selected_ids),
        "retain":sorted(current_ids) if insufficient else retain, "admit":[] if insufficient else admit,
        "evict":[] if insufficient else evict, "provisional_selected":sorted(selected_ids) if insufficient else [],
        "provisional_admit":admit if insufficient else [], "provisional_evict":evict if insufficient else [],
        "blocked":blocked,"excluded":excluded,"review_required":sorted(review,key=lambda r:(r["item_id"],r["reason"])),
        "rows":sorted(rows,key=lambda r:r["item_id"]),"tasks_observed":task_count,"config":asdict(config),
        "changes_applied":False,"warning":"recommendations are non-causal unless validated by runtime/task outcomes",
    }


def shadow_prefetch_plan(entries: Sequence[Mapping[str, Any]], telemetry: Mapping[str, Any], *,
                         active_item_ids: Sequence[str], now: date, max_candidates: int = 3,
                         min_support: int = 2, min_confidence: float = 0.5,
                         candidate_tiers: tuple[str, ...] = ("T1","T2"), mode: str = "locator") -> dict[str, Any]:
    """Recommend bounded locator/excerpt prefetches from explicit co-demand only."""
    _nonnegative_int(max_candidates,"max_candidates"); _positive_int(min_support,"min_support")
    min_confidence = _unit_interval(min_confidence,"min_confidence")
    if mode not in PREFETCH_MODES: raise ResidencyError("mode: prefetch must be locator or tiny_excerpt")
    if not isinstance(candidate_tiers, tuple) or not candidate_tiers: raise ResidencyError("candidate_tiers: expected non-empty tuple")
    if any(t not in VALID_TIERS-{"T0"} for t in candidate_tiers): raise ResidencyError("candidate_tiers: only T1/T2/T3 candidates are supported")
    if not isinstance(telemetry, Mapping): raise ResidencyError("telemetry: expected aggregate object")
    stats_by_id = telemetry.get("items", {})
    if not isinstance(stats_by_id, Mapping): raise ResidencyError("telemetry.items: expected object")
    active: list[str] = []; active_set: set[str] = set()
    for value in active_item_ids:
        item_id = _nonempty(value,"active_item_id")
        if item_id not in active_set: active_set.add(item_id); active.append(item_id)
    by_id: dict[str, Mapping[str, Any]] = {}
    for raw in entries:
        if not isinstance(raw, Mapping): raise ResidencyError("entry: expected object")
        item_id = _nonempty(raw.get("id"),"entry id")
        if item_id in by_id: raise ResidencyError("duplicate entry id")
        by_id[item_id] = raw
    seeds: list[tuple[str,set[str]]] = []; unavailable: list[dict[str,str]] = []
    for item_id in active:
        stats = stats_by_id.get(item_id)
        if not isinstance(stats, Mapping): unavailable.append({"item_id":item_id,"reason":"no_demand_telemetry"}); continue
        raw_tasks = stats.get("demand_task_ids", [])
        if not isinstance(raw_tasks,list) or any(not isinstance(v,str) or not v for v in raw_tasks):
            raise ResidencyError(f"telemetry.items[{item_id}].demand_task_ids: expected string list")
        tasks = set(raw_tasks)
        if len(tasks) < min_support: unavailable.append({"item_id":item_id,"reason":"insufficient_seed_support"}); continue
        seeds.append((item_id,tasks))
    seed_sizes = {item_id:len(tasks) for item_id,tasks in seeds}; candidates: list[dict[str,Any]] = []; excluded: list[dict[str,str]] = []
    for item_id in sorted(by_id):
        if item_id in active_set: continue
        entry = by_id[item_id]; tier = entry.get("tier")
        if tier not in VALID_TIERS: raise ResidencyError("entry tier: unsupported")
        if tier not in candidate_tiers: continue
        if not _entry_current(entry,now): excluded.append({"item_id":item_id,"reason":"status_or_validity"}); continue
        locator = _entry_locator(entry)
        if locator is None: excluded.append({"item_id":item_id,"reason":"missing_safe_locator"}); continue
        stats = stats_by_id.get(item_id)
        if not isinstance(stats,Mapping): continue
        raw_tasks = stats.get("demand_task_ids", [])
        if not isinstance(raw_tasks,list) or any(not isinstance(v,str) or not v for v in raw_tasks):
            raise ResidencyError(f"telemetry.items[{item_id}].demand_task_ids: expected string list")
        candidate_tasks = set(raw_tasks)
        if not candidate_tasks: continue
        best = None
        for seed_id,seed_tasks in seeds:
            support = len(seed_tasks & candidate_tasks); confidence = support/len(seed_tasks)
            if support < min_support or confidence < min_confidence: continue
            if best is None or (confidence,support) > best[:2] or ((confidence,support)==best[:2] and seed_id<best[2]):
                best = (confidence,support,seed_id)
        if best is None: continue
        confidence,support,seed_id = best
        misses = stats.get("observed_miss_events",0); miss_tokens = stats.get("miss_extra_tokens",0)
        _nonnegative_int(misses,f"telemetry.items[{item_id}].observed_miss_events")
        _nonnegative_int(miss_tokens,f"telemetry.items[{item_id}].miss_extra_tokens")
        caller = entry.get("miss_penalty_tokens")
        if caller is not None: caller = _nonnegative_number(caller,"miss_penalty_tokens")
        avg = miss_tokens/misses if misses else None; penalty = caller if caller is not None else avg
        candidates.append({"item_id":item_id,"tier":tier,"locator":locator,"mode":mode,"seed_item_id":seed_id,
            "support_tasks":support,"seed_demand_tasks":seed_sizes[seed_id],"confidence":confidence,
            "candidate_demand_tasks":len(candidate_tasks),"observed_miss_events":misses,
            "avg_miss_extra_tokens":avg,"miss_penalty_tokens":penalty})
    candidates.sort(key=lambda r:(-r["confidence"],-r["support_tasks"],-(r["miss_penalty_tokens"] if r["miss_penalty_tokens"] is not None else -1.0),r["item_id"]))
    return {"status":"OK" if seeds else "INSUFFICIENT_SEED_TELEMETRY","mode":mode,"active_item_ids":active,
        "candidates":candidates[:max_candidates],"eligible_candidates":len(candidates),"unavailable_seeds":unavailable,"excluded":excluded,
        "parameters":{"max_candidates":max_candidates,"min_support":min_support,"min_confidence":min_confidence,"candidate_tiers":list(candidate_tiers)},
        "training_signal":"explicit_demand_task_cooccurrence_only","prefetch_events_used_for_training":False,
        "changes_applied":False,"warning":"shadow co-demand heuristic; candidate recommendation is not a causal utility claim"}


@dataclass(frozen=True)
class BudgetControllerConfig:
    min_budget: int
    max_budget: int
    step: int
    min_demands: int = 20
    miss_target: float = 0.10
    pressure_target: float = 0.80
    miss_weight: float = 1.0
    pressure_weight: float = 1.0
    risk_weight: float = 0.5
    hysteresis: float = 0.05

    def __post_init__(self):
        for value,field in ((self.min_budget,"min_budget"),(self.max_budget,"max_budget"),(self.step,"step")): _positive_int(value,field)
        if self.min_budget > self.max_budget: raise ResidencyError("min_budget must not exceed max_budget")
        _nonnegative_int(self.min_demands,"min_demands")
        _unit_interval(self.miss_target,"miss_target"); _unit_interval(self.pressure_target,"pressure_target")
        for value,field in ((self.miss_weight,"miss_weight"),(self.pressure_weight,"pressure_weight"),(self.risk_weight,"risk_weight"),(self.hysteresis,"hysteresis")):
            _nonnegative_number(value,field)


def suggest_resident_budget(telemetry: Mapping[str, Any], *, current_budget: int,
                            context_pressure: float, config: BudgetControllerConfig) -> dict[str, Any]:
    """Return one bounded shadow budget step; never apply it."""
    if type(current_budget) is not int or not config.min_budget <= current_budget <= config.max_budget:
        raise ResidencyError("current_budget outside controller bounds")
    pressure = _unit_interval(context_pressure,"context_pressure"); demand = telemetry.get("demand_count")
    if isinstance(demand,bool) or not isinstance(demand,int) or demand<0: raise ResidencyError("telemetry.demand_count: expected nonnegative integer")
    miss_rate = telemetry.get("resident_miss_rate")
    if miss_rate is not None: miss_rate = _unit_interval(miss_rate,"resident_miss_rate")
    prefetch = telemetry.get("prefetch", {})
    if not isinstance(prefetch,Mapping): raise ResidencyError("telemetry.prefetch: expected object")
    count = prefetch.get("count",0); used = prefetch.get("used",0); _nonnegative_int(count,"prefetch.count"); _nonnegative_int(used,"prefetch.used")
    if used > count: raise ResidencyError("prefetch.used exceeds prefetch.count")
    pollution = 0.0 if count==0 else (count-used)/count
    stale = telemetry.get("stale_resident_failures",0); _nonnegative_int(stale,"stale_resident_failures")
    stale_rate = (1.0 if stale else 0.0) if demand==0 else min(1.0,stale/demand)
    signals = {"demand_count":demand,"resident_miss_rate":miss_rate,"context_pressure":pressure,
               "prefetch_pollution_rate":pollution,"stale_failure_rate":stale_rate}
    if demand < config.min_demands or miss_rate is None:
        return {"status":"INSUFFICIENT_TELEMETRY","current_budget":current_budget,"suggested_budget":current_budget,
                "direction":"hold","changes_applied":False,"signals":signals,"config":asdict(config)}
    grow = config.miss_weight*max(0.0,miss_rate-config.miss_target)
    shrink = config.pressure_weight*max(0.0,pressure-config.pressure_target)+config.risk_weight*(pollution+stale_rate)
    score = grow-shrink
    if score > config.hysteresis: direction="grow"; suggested=min(config.max_budget,current_budget+config.step)
    elif score < -config.hysteresis: direction="shrink"; suggested=max(config.min_budget,current_budget-config.step)
    else: direction="hold"; suggested=current_budget
    if suggested==current_budget and direction!="hold": direction="hold_at_bound"
    signals.update({"miss_excess":max(0.0,miss_rate-config.miss_target),"pressure_excess":max(0.0,pressure-config.pressure_target)})
    return {"status":"OK","current_budget":current_budget,"suggested_budget":suggested,"direction":direction,
            "controller_score":score,"signals":signals,"config":asdict(config),"changes_applied":False,
            "warning":"shadow feedback suggestion; no automatic T0 budget mutation"}
