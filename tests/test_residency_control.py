from datetime import date
import unittest

from thm.residency import (
    BudgetControllerConfig, ResidencyError, ShadowPlanConfig, aggregate_telemetry,
    apply_catalog, project_warm_directory, shadow_prefetch_plan, shadow_residency_plan,
    suggest_resident_budget, validate_telemetry_event,
)


def entry(item_id, tier, *, units=None, pinned=False, locator=None, status="active", cost="med", events=None, **extra):
    row={"id":item_id,"tier":tier,"store":extra.pop("store","MEMORY.md" if tier=="T0" else f"warm/{item_id}.md"),
         "key":extra.pop("key",item_id),"summary":extra.pop("summary",item_id),"created":extra.pop("created","2026-09-01"),
         "events":events if events is not None else [{"event_id":f"create:{item_id}","type":"create","t":"2026-09-01"}],
         "cost_class":cost,"pinned":pinned,"status":status}
    if units is not None: row["resident_units"]=units
    if locator is not None: row["locator"]=locator
    row.update(extra); return row


class TelemetryTests(unittest.TestCase):
    def test_planned_retrieval_is_not_miss(self):
        r=aggregate_telemetry([{"event_id":"1","task_id":"t","kind":"planned_retrieval","item_id":"a","extra_tokens":40},{"event_id":"2","task_id":"t","kind":"resident_hit","item_id":"b"}])
        self.assertEqual(r["planned_retrievals"],1); self.assertEqual(r["demand_count"],1); self.assertEqual(r["resident_miss_rate"],0); self.assertEqual(r["miss_penalty"]["extra_tokens"],0)

    def test_prefetch_net_value_and_coverage(self):
        r=aggregate_telemetry([{"event_id":"1","task_id":"t1","kind":"prefetch","item_id":"a","used":True,"mode":"locator","extra_tokens":10,"avoided_miss":True,"avoided_extra_tokens":100},{"event_id":"2","task_id":"t2","kind":"resident_miss","item_id":"a","extra_tokens":50}])
        self.assertEqual(r["prefetch"]["net_tokens_observed"],90); self.assertAlmostEqual(r["prefetch"]["coverage_observed"],.5); self.assertEqual(r["items"]["a"]["prefetch_net_tokens_observed"],90)

    def test_prefetch_mode_bounded(self):
        with self.assertRaisesRegex(ResidencyError,"mode"):
            validate_telemetry_event({"event_id":"1","task_id":"t","kind":"prefetch","item_id":"a","used":False,"mode":"full"})

    def test_unattributed_stale_is_global(self):
        r=aggregate_telemetry([{"event_id":"1","task_id":"t","kind":"stale_resident_failure"}]); self.assertEqual(r["stale_resident_failures"],1); self.assertEqual(r["items"],{})


class DirectoryAndCatalogTests(unittest.TestCase):
    def test_directory_locator_only_budgeted(self):
        rows=[entry("a","T1",units=50,locator="warm/a.md",key="db",scope="p",cost="high"),entry("b","T1",units=50,locator="warm/b.md",key="other",scope="p",cost="low"),entry("hot","T0",units=10)]
        r=project_warm_directory(rows,now=date(2026,9,7),budget=55,count_units=lambda text:len(text.encode())//10+1)
        self.assertEqual(r["projection"],"locator_only"); self.assertTrue(r["lines"]); self.assertTrue(r["budget_used"]<=55); self.assertFalse(r["changes_applied"])

    def test_native_store_is_not_t1_locator(self):
        r=project_warm_directory([entry("a","T1",store="MEMORY.md")],now=date(2026,9,7),budget=None,count_units=len); self.assertEqual(r["unlocatable_item_ids"],["a"])

    def test_invalid_entry_excluded(self):
        r=project_warm_directory([entry("a","T1",status="invalid",locator="warm/a.md")],now=date(2026,9,7),budget=None,count_units=len); self.assertEqual(r["excluded"],[{"item_id":"a","reason":"status_or_validity"}])

    def test_path_traversal_rejected(self):
        r=project_warm_directory([entry("a","T1",locator="../secret.md")],now=date(2026,9,7),budget=None,count_units=len); self.assertEqual(r["unlocatable_item_ids"],["a"])

    def test_overlay_does_not_mutate_or_override_tier(self):
        src=[entry("a","T1")]; out=apply_catalog(src,{"a":{"resident_units":12,"locator":"warm/a.md"}}); self.assertNotIn("resident_units",src[0]); self.assertEqual(out[0]["resident_units"],12)
        with self.assertRaisesRegex(ResidencyError,"unsupported field tier"): apply_catalog(src,{"a":{"tier":"T0"}})


class ShadowPlanTests(unittest.TestCase):
    def telemetry(self):
        events=[{"event_id":f"h{i}","task_id":f"t{i}","kind":"resident_hit","item_id":"hot"} for i in range(20)]
        events += [{"event_id":f"m{i}","task_id":f"m{i}","kind":"resident_miss","item_id":"warm","extra_tokens":1000,"avoidable":True} for i in range(5)]
        return aggregate_telemetry(events)

    def test_positive_candidate_admitted(self):
        r=shadow_residency_plan([entry("hot","T0",units=100,pinned=True),entry("warm","T1",units=10,miss_penalty_tokens=1000)],self.telemetry(),now=date(2026,9,7),budget=120,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=20,min_tasks=1,min_item_demands=1,complete_coverage=True))
        self.assertIn("warm",r["admit"]); self.assertIn("hot",r["retain"]); self.assertFalse(r["changes_applied"])

    def test_unknown_current_resident_protected(self):
        r=shadow_residency_plan([entry("hot","T0",units=40)],aggregate_telemetry([]),now=date(2026,9,7),budget=50,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=20,complete_coverage=False)); self.assertEqual(r["selected"],["hot"]); self.assertIn({"item_id":"hot","reason":"counterfactual_miss_cost_unknown"},r["review_required"])

    def test_stale_blocks_residency(self):
        t=aggregate_telemetry([{"event_id":"s","task_id":"t","kind":"stale_resident_failure","item_id":"hot"},{"event_id":"h","task_id":"t","kind":"resident_hit","item_id":"hot"}])
        r=shadow_residency_plan([entry("hot","T0",units=20)],t,now=date(2026,9,7),budget=20,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=1,complete_coverage=True)); self.assertIn("hot",r["evict"]); self.assertIn({"item_id":"hot","reason":"stale_resident_failure"},r["review_required"])

    def test_missing_cost_and_protected_over_budget_explicit(self):
        t=aggregate_telemetry([{"event_id":"m","task_id":"t","kind":"resident_miss","item_id":"warm","extra_tokens":100}]); r=shadow_residency_plan([entry("warm","T1")],t,now=date(2026,9,7),budget=100,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=1,complete_coverage=True)); self.assertIn({"item_id":"warm","reason":"missing_resident_cost"},r["excluded"])
        r=shadow_residency_plan([entry("hot","T0",units=200,pinned=True)],aggregate_telemetry([]),now=date(2026,9,7),budget=100,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=0)); self.assertEqual(r["status"],"PROTECTED_OVER_BUDGET")

    def test_prefetch_use_not_residency_demand(self):
        t=aggregate_telemetry([{"event_id":"p","task_id":"t","kind":"prefetch","item_id":"warm","used":True}]); r=shadow_residency_plan([entry("warm","T1",units=5,miss_penalty_tokens=1000)],t,now=date(2026,9,7),budget=10,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=10,min_tasks=1,min_item_demands=1,complete_coverage=True)); self.assertEqual(r["admit"],[]); self.assertEqual(r["rows"][0]["need_task_rate"],0.0)

    def test_insufficient_telemetry_suppresses_deltas(self):
        t=aggregate_telemetry([{"event_id":"m","task_id":"t","kind":"resident_miss","item_id":"warm","extra_tokens":500}]); r=shadow_residency_plan([entry("hot","T0",units=20),entry("warm","T1",units=5,miss_penalty_tokens=500)],t,now=date(2026,9,7),budget=30,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=10,min_item_demands=1,complete_coverage=True)); self.assertEqual(r["status"],"INSUFFICIENT_TELEMETRY"); self.assertEqual(r["admit"],[]); self.assertEqual(r["evict"],[]); self.assertIn("warm",r["provisional_admit"])

    def test_uncosted_current_blocks_changes(self):
        r=shadow_residency_plan([entry("hot","T0")],aggregate_telemetry([]),now=date(2026,9,7),budget=30,unit_cost=lambda _:None,config=ShadowPlanConfig(horizon_tasks=5,min_tasks=0)); self.assertEqual(r["status"],"UNCOSTED_CURRENT_RESIDENT"); self.assertEqual(r["admit"],[]); self.assertEqual(r["evict"],[])


class PrefetchPlanTests(unittest.TestCase):
    def base(self, prefetch_only=False):
        events=[{"event_id":"h1","task_id":"t1","kind":"resident_hit","item_id":"hot"},{"event_id":"h2","task_id":"t2","kind":"resident_hit","item_id":"hot"}]
        kind="prefetch" if prefetch_only else "resident_miss"
        for i,task in enumerate(("t1","t2"),1):
            e={"event_id":f"x{i}","task_id":task,"kind":kind,"item_id":"warm"}
            if prefetch_only: e["used"]=True
            else: e["extra_tokens"]=100
            events.append(e)
        return aggregate_telemetry(events)

    def test_co_demand_recommends_locator(self):
        r=shadow_prefetch_plan([entry("hot","T0",units=10),entry("warm","T1",locator="warm/warm.md")],self.base(),active_item_ids=["hot"],now=date(2026,9,7)); self.assertEqual([x["item_id"] for x in r["candidates"]],["warm"]); self.assertEqual(r["candidates"][0]["confidence"],1.0); self.assertFalse(r["changes_applied"])

    def test_prefetch_does_not_train_itself(self):
        t=self.base(True); self.assertEqual(t["items"]["warm"]["demand_task_ids"],[]); r=shadow_prefetch_plan([entry("hot","T0",units=10),entry("warm","T1",locator="warm/warm.md")],t,active_item_ids=["hot"],now=date(2026,9,7)); self.assertEqual(r["candidates"],[]); self.assertFalse(r["prefetch_events_used_for_training"])

    def test_unsafe_locator_and_insufficient_seed(self):
        t=self.base(); r=shadow_prefetch_plan([entry("hot","T0",units=10),entry("warm","T1",locator="../x")],t,active_item_ids=["hot"],now=date(2026,9,7)); self.assertEqual(r["candidates"],[]); self.assertIn({"item_id":"warm","reason":"missing_safe_locator"},r["excluded"])
        t=aggregate_telemetry([{"event_id":"h","task_id":"t","kind":"resident_hit","item_id":"hot"},{"event_id":"m","task_id":"t","kind":"resident_miss","item_id":"warm"}]); r=shadow_prefetch_plan([entry("hot","T0",units=10),entry("warm","T1",locator="warm/warm.md")],t,active_item_ids=["hot"],now=date(2026,9,7),min_support=2); self.assertEqual(r["status"],"INSUFFICIENT_SEED_TELEMETRY")


class BudgetTests(unittest.TestCase):
    def cfg(self): return BudgetControllerConfig(min_budget=100,max_budget=500,step=50,min_demands=10,miss_target=.1,pressure_target=.8,hysteresis=.02)
    def test_grow_shrink_and_insufficient(self):
        t=aggregate_telemetry([*({"event_id":f"m{i}","task_id":f"t{i}","kind":"resident_miss","item_id":"a"} for i in range(8)),*({"event_id":f"h{i}","task_id":f"x{i}","kind":"resident_hit","item_id":"a"} for i in range(2))]); self.assertEqual(suggest_resident_budget(t,current_budget=200,context_pressure=.5,config=self.cfg())["suggested_budget"],250)
        t=aggregate_telemetry([*({"event_id":f"h{i}","task_id":f"t{i}","kind":"resident_hit","item_id":"a"} for i in range(10)),{"event_id":"p1","task_id":"p1","kind":"prefetch","item_id":"b","used":False},{"event_id":"p2","task_id":"p2","kind":"prefetch","item_id":"c","used":False}]); self.assertEqual(suggest_resident_budget(t,current_budget=200,context_pressure=.95,config=self.cfg())["suggested_budget"],150)
        t=aggregate_telemetry([{"event_id":"h","task_id":"t","kind":"resident_hit","item_id":"a"}]); self.assertEqual(suggest_resident_budget(t,current_budget=200,context_pressure=.9,config=self.cfg())["status"],"INSUFFICIENT_TELEMETRY")


if __name__ == "__main__": unittest.main()
