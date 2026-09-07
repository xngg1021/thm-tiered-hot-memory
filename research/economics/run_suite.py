#!/usr/bin/env python3
"""Orchestrate THM machine retrieval runs and corrected CE cost proxies.

The suite keeps runtime-measured retrieval evidence separate from model-proxy
cost estimates. New runs are immutable-by-default: output names are tagged and
an existing target is never overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ENGINE.parent / "models" / "all-MiniLM-L6-v2"
DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DATASETS = ENGINE.parent / "datasets"
DEFAULT_REPORTS = ENGINE / "reports"


def redact_text(value: str, redactions: list[tuple[str, str]]) -> str:
    text = value
    for raw, replacement in sorted(redactions, key=lambda item: len(item[0]), reverse=True):
        if raw:
            text = text.replace(raw, replacement)
    return text


def run_checked(cmd: list[str], label: str, redactions: list[tuple[str, str]]) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd, cwd=ENGINE, capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )
    elapsed = time.perf_counter() - t0
    out = {
        "label": label,
        "command": [redact_text(str(part), redactions) for part in cmd],
        "exit_code": proc.returncode,
        "elapsed_s": round(elapsed, 1),
        "stdout_tail": redact_text((proc.stdout or "")[-2000:], redactions),
    }
    if proc.returncode != 0:
        out["stderr_tail"] = redact_text((proc.stderr or "")[-2000:], redactions)
    print(f"[{'OK' if proc.returncode == 0 else 'FAIL'}] {label} ({elapsed:.0f}s)", flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {proc.returncode}")
    return out


def summarize_json(path: Path, keys: list[str]) -> dict:
    if not path.is_file():
        return {"missing": path.name}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: data.get(key) for key in keys if key in data}


def tagged(stem: str, tag: str, suffix: str) -> str:
    return f"{stem}{tag}{suffix}"


def require_new(path: Path) -> None:
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing machine-test artifact: {path.name}; "
            "choose a new --artifact-tag"
        )


def normalize_tag(value: str | None, device: str) -> str:
    tag = value if value is not None else ("-gpu-v2" if device == "cuda" else "-cpu-v2")
    if not tag:
        raise ValueError("--artifact-tag must be nonempty; historical untagged artifacts are immutable")
    if not tag.startswith("-"):
        tag = "-" + tag
    if not re.fullmatch(r"-[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError("--artifact-tag must contain only letters, numbers, dot, underscore and hyphen")
    return tag


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-locomo", action="store_true")
    ap.add_argument("--skip-lme", action="store_true")
    ap.add_argument("--budgets", nargs="+", type=int, default=[300, 600, 1200])
    ap.add_argument("--modes", nargs="+", default=["literal", "sparse", "dense", "hybrid"])
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument(
        "--artifact-tag", default=None,
        help="nonempty filename tag; defaults to -cpu-v2 or -gpu-v2",
    )
    ap.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    ap.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    ap.add_argument("--datasets-root", default=str(DEFAULT_DATASETS))
    ap.add_argument("--reports-dir", default=str(DEFAULT_REPORTS))
    ap.add_argument("--ce-root", default=os.environ.get("CONTEXT_ECONOMICS_ROOT"))
    args = ap.parse_args()

    if type(args.batch_size) is not int or args.batch_size <= 0:
        raise ValueError("--batch-size must be a positive integer")
    if type(args.threads) is not int or args.threads <= 0:
        raise ValueError("--threads must be a positive integer")

    tag = normalize_tag(args.artifact_tag, args.device)
    reports = Path(args.reports_dir).expanduser().resolve()
    datasets = Path(args.datasets_root).expanduser().resolve()
    model_path = Path(args.model_path).expanduser().resolve()
    ce_root = Path(args.ce_root).expanduser().resolve() if args.ce_root else None
    reports.mkdir(parents=True, exist_ok=True)

    redactions = [
        (str(sys.executable), "<PYTHON>"),
        (str(ce_root), "<CONTEXT_ECONOMICS_ROOT>") if ce_root else ("", ""),
        (str(model_path), "<MODEL_PATH>"),
        (str(datasets), "<DATASETS_ROOT>"),
        (str(reports), "<REPORTS_DIR>"),
        (str(ENGINE), "<THM_ROOT>"),
    ]

    budgets = [str(value) for value in args.budgets]
    steps = []
    locomo_out = reports / tagged("2026-09-08-local-full-matrix", tag, ".json")
    lme_out = reports / tagged("2026-09-08-lme-retrieval", tag, ".json")
    econ_out = reports / tagged("2026-09-08-economics-bridge-v2", tag, ".json")
    md_out = reports / tagged("2026-09-08-suite-report-v2", tag, ".md")
    suite_out = reports / tagged("2026-09-08-suite-report-v2", tag, ".json")

    if not args.skip_locomo:
        require_new(locomo_out)
        steps.append(run_checked([
            sys.executable, "research/recall/benchmark.py",
            "--dataset", str(datasets / "locomo10.json"),
            "--counter", "cl100k_base",
            "--modes", *args.modes,
            "--budgets", *budgets,
            "--model-path", str(model_path), "--model-id", args.model_id,
            "--device", args.device, "--batch-size", str(args.batch_size),
            "--output", str(locomo_out),
        ], "LoCoMo Protocol 2 full matrix", redactions))

    if not args.skip_lme:
        require_new(lme_out)
        steps.append(run_checked([
            sys.executable, "research/recall/lme_retrieval.py",
            "--dataset", str(datasets / "longmemeval_s"),
            "--counter", "cl100k_base",
            "--modes", *args.modes,
            "--budgets", *budgets,
            "--model-path", str(model_path), "--model-id", args.model_id,
            "--threads", str(args.threads),
            "--device", args.device, "--batch-size", str(args.batch_size),
            "--output", str(lme_out),
        ], "LongMemEval-S retrieval coverage", redactions))

    if not locomo_out.is_file():
        raise ValueError(f"LoCoMo artifact missing for tag {tag}")
    if ce_root is None:
        raise ValueError("--ce-root or CONTEXT_ECONOMICS_ROOT is required for economics bridge")

    require_new(econ_out)
    steps.append(run_checked([
        sys.executable, "research/economics/thm_ce_bridge.py",
        "--results", str(locomo_out),
        "--dataset", str(datasets / "locomo10.json"),
        "--ce-root", str(ce_root),
        "--output", str(econ_out),
    ], "THM x Context Economics bridge v2", redactions))

    require_new(md_out)
    report_cmd = [
        sys.executable, "research/economics/report_md.py",
        "--locomo", str(locomo_out),
        "--econ", str(econ_out),
        "--output", str(md_out),
    ]
    if lme_out.is_file():
        report_cmd += ["--lme", str(lme_out)]
    steps.append(run_checked(report_cmd, "Consolidated machine-test report v2", redactions))

    require_new(suite_out)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "device": args.device,
        "artifact_tag": tag,
        "evidence_labels": {
            "retrieval_metrics": "runtime-measured",
            "cost_figures": "model-proxy",
            "pricing": "provider-doc-as-relayed (scenarios)",
            "answer_accuracy": "not_measured",
            "observed_provider_bill": "not_measured",
        },
        "steps": steps,
        "artifacts": {
            "locomo_file": locomo_out.name,
            "locomo": summarize_json(
                locomo_out,
                ["protocol", "counter", "dataset_sha256", "modes", "budgets",
                 "generation_calls", "judge_calls", "summaries"],
            ),
            "lme_file": lme_out.name if lme_out.is_file() else None,
            "lme": summarize_json(
                lme_out,
                ["benchmark", "protocol", "modes", "budgets",
                 "generation_calls", "judge_calls", "summaries"],
            ),
            "economics_file": econ_out.name,
            "economics": summarize_json(
                econ_out,
                ["kind", "context_economics_provenance", "primary_proxy_scenario",
                 "suite_totals", "l6_budget_grid_sensitivity"],
            ),
            "markdown_report": md_out.name,
        },
    }
    suite_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"suite report: {suite_out.name}")


if __name__ == "__main__":
    main()
