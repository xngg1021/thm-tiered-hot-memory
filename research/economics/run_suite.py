#!/usr/bin/env python3
"""Benchmark suite orchestrator: THM retrieval benches + CE economics bridge.

Produces one consolidated markdown report with evidence labels. This is the
"full-house" local run: LoCoMo Protocol 2, LongMemEval-S, THM suite artifacts
(decay/frontier), CE local E2E, and the THM x CE economics bridge.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
MODEL_PATH = ENGINE.parent / "models" / "all-MiniLM-L6-v2"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DATASETS = ENGINE.parent / "datasets"
REPORTS = ENGINE / "reports"


def run_checked(cmd: list[str], label: str) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - t0
    out = {"label": label, "cmd": " ".join(cmd), "exit_code": proc.returncode,
           "elapsed_s": round(elapsed, 1),
           "stdout_tail": (proc.stdout or "")[-2000:]}
    if proc.returncode != 0:
        out["stderr_tail"] = (proc.stderr or "")[-2000:]
    print(f"[{'OK' if proc.returncode == 0 else 'FAIL'}] {label} ({elapsed:.0f}s)", flush=True)
    return out


def summarize_json(path: Path, keys: list[str]) -> dict:
    if not path.is_file():
        return {"missing": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: data.get(k) for k in keys if k in data}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-locomo", action="store_true")
    ap.add_argument("--skip-lme", action="store_true")
    ap.add_argument("--budgets", nargs="+", type=int, default=[300, 600, 1200])
    ap.add_argument("--modes", nargs="+", default=["literal", "sparse", "dense", "hybrid"])
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    budgets = [str(b) for b in args.budgets]
    steps = []
    locomo_out = REPORTS / "2026-09-08-local-full-matrix.json"
    lme_out = REPORTS / "2026-09-08-lme-retrieval.json"
    econ_out = REPORTS / "2026-09-08-economics-bridge.json"

    if not args.skip_locomo:
        steps.append(run_checked([
            sys.executable, "research/recall/benchmark.py",
            "--dataset", str(DATASETS / "locomo10.json"),
            "--counter", "cl100k_base",
            "--modes", *args.modes,
            "--budgets", *budgets,
            "--model-path", str(MODEL_PATH), "--model-id", MODEL_ID,
            "--device", args.device, "--batch-size", str(args.batch_size),
            "--output", str(locomo_out),
        ], "LoCoMo Protocol 2 full matrix"))

    if not args.skip_lme:
        steps.append(run_checked([
            sys.executable, "research/recall/lme_retrieval.py",
            "--dataset", str(DATASETS / "longmemeval_s"),
            "--counter", "cl100k_base",
            "--modes", *args.modes,
            "--budgets", *budgets,
            "--model-path", str(MODEL_PATH), "--model-id", MODEL_ID,
            "--threads", "16", "--device", args.device, "--batch-size", str(args.batch_size),
            "--output", str(lme_out),
        ], "LongMemEval-S retrieval coverage"))

    if locomo_out.is_file():
        steps.append(run_checked([
            sys.executable, "research/economics/thm_ce_bridge.py",
            "--results", str(locomo_out),
            "--dataset", str(DATASETS / "locomo10.json"),
            "--output", str(econ_out),
        ], "THM x CE economics bridge (LoCoMo telemetry)"))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "evidence_labels": {
            "retrieval_metrics": "runtime-measured",
            "cost_figures": "model-proxy",
            "pricing": "provider-doc-as-relayed (scenarios)",
        },
        "steps": steps,
        "artifacts": {
            "locomo": summarize_json(locomo_out, ["protocol", "modes", "budgets", "generation_calls", "judge_calls", "summaries"]),
            "lme": summarize_json(lme_out, ["benchmark", "protocol", "modes", "budgets", "generation_calls", "judge_calls", "summaries"]),
            "economics": summarize_json(econ_out, ["kind", "l5_totals", "l6_marginal"]),
        },
    }
    out = REPORTS / "2026-09-08-suite-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"suite report: {out}")


if __name__ == "__main__":
    main()
