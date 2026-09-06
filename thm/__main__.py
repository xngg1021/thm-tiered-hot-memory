"""THM retrieval, observation, policy and shadow-residency CLI."""
from __future__ import annotations

import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys

from . import __version__
from .observations import scan, summarize, store_observations
from .policy import Policy, activity, curve_report, plan
from .residency import (
    BudgetControllerConfig, ShadowPlanConfig, aggregate_telemetry, apply_catalog,
    load_catalog, load_telemetry_jsonl, project_warm_directory, shadow_prefetch_plan,
    shadow_residency_plan, suggest_resident_budget,
)
from .retrieval import SearchIndex, SentenceEncoder, TokenCounter
from .sources import file_documents, hermes_documents, jsonl_documents, read_hermes


def legacy_engine():
    path = Path(__file__).resolve().parents[1] / "scripts/thm.py"
    spec = importlib.util.spec_from_file_location("_thm_legacy_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _add_engine_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mem-dir", required=True); parser.add_argument("--state-dir")


def _load_shadow_entries(args, *, with_sources: bool = False):
    legacy = legacy_engine(); engine = legacy.Engine(args.mem_dir, args.state_dir)
    entries = apply_catalog(engine.load().data["entries"], load_catalog(getattr(args, "catalog", None)))
    if not with_sources: return legacy, engine, entries, None
    source_text = {legacy.source_hash(store, text): text for store, rows in engine.stores().items() for text, _ in rows}
    return legacy, engine, entries, source_text


def _resident_unit_cost(counter: TokenCounter, source_text: dict[str, str]):
    def cost(entry):
        explicit = entry.get("resident_units")
        if explicit is not None: return explicit
        if entry.get("tier") == "T0":
            text = source_text.get(entry.get("source_hash"))
            if text is not None: return max(1, counter(text + "\n§\n"))
        return None
    return cost


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["index"]: return legacy_engine().main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("import-jsonl", "import-files", "import-hermes"):
        p=sub.add_parser(name); p.add_argument("source"); p.add_argument("--db",required=True); p.add_argument("--scope",required=True)
    for name in ("search","embed"):
        p=sub.add_parser(name); p.add_argument("--db",required=True); p.add_argument("--scope",required=True); p.add_argument("--model-path"); p.add_argument("--model-id")
        if name=="search":
            p.add_argument("query"); p.add_argument("--budget",type=int,default=600); p.add_argument("--counter",default="utf8_bytes")
            p.add_argument("--mode",choices=["literal","sparse","hybrid","dense"],default="sparse"); p.add_argument("--neighbors",type=int,choices=[0,1,2],default=0)
    p=sub.add_parser("scan"); p.add_argument("--state-db",required=True); p.add_argument("--scope",required=True); p.add_argument("--anchors",required=True); p.add_argument("--now",required=True); p.add_argument("--days",type=int,default=7); p.add_argument("--save-observations")
    sub.add_parser("curves")
    p=sub.add_parser("plan"); _add_engine_paths(p); p.add_argument("--date",required=True); p.add_argument("--budget",type=int,required=True); p.add_argument("--counter",default="utf8_bytes"); p.add_argument("--kernel",default="bounded_power"); p.add_argument("--half-life",type=float,default=30)
    p=sub.add_parser("residency-telemetry"); p.add_argument("trace")
    p=sub.add_parser("warm-directory"); _add_engine_paths(p); p.add_argument("--date",required=True); p.add_argument("--budget",type=int); p.add_argument("--counter",default="utf8_bytes"); p.add_argument("--catalog")
    p=sub.add_parser("residency-plan"); _add_engine_paths(p); p.add_argument("--date",required=True); p.add_argument("--budget",type=int,required=True); p.add_argument("--telemetry",required=True); p.add_argument("--catalog"); p.add_argument("--counter",default="utf8_bytes"); p.add_argument("--kernel",default="bounded_power"); p.add_argument("--half-life",type=float,default=30); p.add_argument("--horizon-tasks",type=int,default=20); p.add_argument("--min-tasks",type=int,default=20); p.add_argument("--min-item-demands",type=int,default=1); p.add_argument("--complete-coverage",action="store_true"); p.add_argument("--candidate-tier",action="append",choices=["T1","T2","T3"]); p.add_argument("--allow-stale",action="store_true")
    p=sub.add_parser("prefetch-plan"); _add_engine_paths(p); p.add_argument("--date",required=True); p.add_argument("--telemetry",required=True); p.add_argument("--catalog"); p.add_argument("--active",action="append",required=True); p.add_argument("--max-candidates",type=int,default=3); p.add_argument("--min-support",type=int,default=2); p.add_argument("--min-confidence",type=float,default=.5); p.add_argument("--candidate-tier",action="append",choices=["T1","T2","T3"]); p.add_argument("--mode",choices=["locator","tiny_excerpt"],default="locator")
    p=sub.add_parser("residency-budget"); p.add_argument("trace"); p.add_argument("--current-budget",type=int,required=True); p.add_argument("--context-pressure",type=float,required=True); p.add_argument("--min-budget",type=int,required=True); p.add_argument("--max-budget",type=int,required=True); p.add_argument("--step",type=int,required=True); p.add_argument("--min-demands",type=int,default=20); p.add_argument("--miss-target",type=float,default=.10); p.add_argument("--pressure-target",type=float,default=.80); p.add_argument("--miss-weight",type=float,default=1.0); p.add_argument("--pressure-weight",type=float,default=1.0); p.add_argument("--risk-weight",type=float,default=.5); p.add_argument("--hysteresis",type=float,default=.05)
    p=sub.add_parser("index",help="pass arguments to the existing scripts/thm.py CLI"); p.add_argument("args",nargs=argparse.REMAINDER)
    args=parser.parse_args(argv); index=None
    try:
        if args.command=="index": return legacy_engine().main(args.args)
        if args.command.startswith("import-"):
            extra={}
            if args.command=="import-jsonl": docs=list(jsonl_documents(args.source,args.scope))
            elif args.command=="import-files": docs=list(file_documents(args.source,args.scope))
            else:
                records,extra=read_hermes(args.source,args.scope)
                if extra["partial"]: raise ValueError("partial import refused; export a bounded scope explicitly")
                docs=list(hermes_documents(records,args.scope))
            index=SearchIndex(args.db); result=index.replace_scope(args.scope,docs) if args.command=="import-jsonl" else index.sync_kind(args.scope,docs,"file:" if args.command=="import-files" else "hermes-message:"); out={**result,"source_read":extra}
        elif args.command in ("search","embed"):
            if not Path(args.db).is_file(): raise ValueError("search index does not exist; import sources first")
            encoder=SentenceEncoder(args.model_path,args.model_id) if args.model_path else None; index=SearchIndex(args.db,TokenCounter(getattr(args,"counter","utf8_bytes")))
            if args.command=="embed":
                if not encoder: raise ValueError("embed requires a local model")
                out=index.embed(args.scope,encoder,args.model_id)
            else: out=index.search(args.scope,args.query,budget=args.budget,mode=args.mode,neighbor_turns=args.neighbors,encoder=encoder,model_id=args.model_id)
        elif args.command=="scan":
            from datetime import timedelta
            from .sources import epoch
            since=(epoch(args.now)-timedelta(days=args.days)).isoformat(); records,read_meta=read_hermes(args.state_db,args.scope,since=since); anchors=json.loads(Path(args.anchors).read_text(encoding="utf-8")); observed,meta=scan(records,anchors,scope=args.scope,now=args.now,days=args.days); out={"summary":summarize(observed),"scan":meta,"read":read_meta,"activity_change":0,"confidence":"mentions_only"}
            if args.save_observations: out["new_observations"]=store_observations(args.save_observations,observed)
        elif args.command=="curves": out=curve_report()
        elif args.command=="plan":
            _legacy,_engine,rows,source_text=_load_shadow_entries(args,with_sources=True); current=[e for e in rows if e["tier"]=="T0" and e.get("source_hash") in source_text]; count=TokenCounter(args.counter); out=plan(current,date.fromisoformat(args.date),args.budget,Policy(kernel=args.kernel,half_life=args.half_life),lambda e:max(1,count(source_text[e["source_hash"]]+"\n§\n"))); out["counter"]=count.name
        elif args.command=="residency-telemetry": out=aggregate_telemetry(load_telemetry_jsonl(args.trace))
        elif args.command=="warm-directory":
            _legacy,_engine,rows,_=_load_shadow_entries(args); count=TokenCounter(args.counter); out=project_warm_directory(rows,now=date.fromisoformat(args.date),budget=args.budget,count_units=count); out["counter"]=count.name
        elif args.command=="residency-plan":
            _legacy,_engine,rows,source_text=_load_shadow_entries(args,with_sources=True); count=TokenCounter(args.counter); telemetry=aggregate_telemetry(load_telemetry_jsonl(args.telemetry)); decay=Policy(kernel=args.kernel,half_life=args.half_life); config=ShadowPlanConfig(horizon_tasks=args.horizon_tasks,min_tasks=args.min_tasks,min_item_demands=args.min_item_demands,candidate_tiers=tuple(args.candidate_tier or ["T1"]),complete_coverage=args.complete_coverage,stale_failure_blocks=not args.allow_stale); out=shadow_residency_plan(rows,telemetry,now=date.fromisoformat(args.date),budget=args.budget,unit_cost=_resident_unit_cost(count,source_text),config=config,activity_fn=lambda entry,stamp:activity(entry,stamp,decay)); out["counter"]=count.name
        elif args.command=="prefetch-plan":
            _legacy,_engine,rows,_=_load_shadow_entries(args); telemetry=aggregate_telemetry(load_telemetry_jsonl(args.telemetry)); out=shadow_prefetch_plan(rows,telemetry,active_item_ids=args.active,now=date.fromisoformat(args.date),max_candidates=args.max_candidates,min_support=args.min_support,min_confidence=args.min_confidence,candidate_tiers=tuple(args.candidate_tier or ["T1","T2"]),mode=args.mode)
        elif args.command=="residency-budget":
            telemetry=aggregate_telemetry(load_telemetry_jsonl(args.trace)); config=BudgetControllerConfig(min_budget=args.min_budget,max_budget=args.max_budget,step=args.step,min_demands=args.min_demands,miss_target=args.miss_target,pressure_target=args.pressure_target,miss_weight=args.miss_weight,pressure_weight=args.pressure_weight,risk_weight=args.risk_weight,hysteresis=args.hysteresis); out=suggest_resident_budget(telemetry,current_budget=args.current_budget,context_pressure=args.context_pressure,config=config)
        print(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)); return 0
    except Exception as exc:
        print(json.dumps({"status":"ERROR","error":str(exc)},ensure_ascii=False),file=sys.stderr); return 1
    finally:
        if index is not None: index.close()


if __name__=="__main__": sys.exit(main())
