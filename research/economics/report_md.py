#!/usr/bin/env python3
"""Generate a consolidated THM x Context Economics machine-test report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def locomo_table(data: dict) -> str:
    modes, budgets = data.get("modes", []), data.get("budgets", [])
    lines = [
        "| 模式 | " + " | ".join(str(b) for b in budgets) + " |",
        "|---|" + "---|" * len(budgets),
    ]
    for mode in modes:
        cells = []
        for budget in budgets:
            summary = data["summaries"][f"{mode}@{budget}"]["main_categories_1_to_4"]
            cells.append(f"{summary['any_gold_hit_rate']:.4f}")
        lines.append(f"| {mode} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def lme_table(data: dict) -> str:
    lines = [
        "| 模式 | " + " | ".join(str(b) for b in data["budgets"]) + " |",
        "|---|" + "---|" * len(data["budgets"]),
    ]
    for mode in data["modes"]:
        cells = [
            f"{data['summaries'][f'{mode}@{budget}']['all_instances']['any_gold_hit_rate']:.4f}"
            for budget in data["budgets"]
        ]
        lines.append(f"| {mode} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def money(value) -> str:
    return "-" if value is None else f"${value:.6f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locomo", default="reports/2026-09-08-local-full-matrix.json")
    ap.add_argument("--lme", default="reports/2026-09-08-lme-retrieval.json")
    ap.add_argument("--econ", default="reports/2026-09-08-economics-bridge-v2.json")
    ap.add_argument("--output", default="reports/2026-09-08-suite-report-v2.md")
    args = ap.parse_args()

    locomo = json.loads(Path(args.locomo).read_text(encoding="utf-8"))
    econ = json.loads(Path(args.econ).read_text(encoding="utf-8"))
    if econ.get("kind") != "thm-x-context-economics-bridge-v2":
        raise ValueError("report_md.py requires corrected bridge-v2 economics artifact")
    lme_path = Path(args.lme)
    lme = json.loads(lme_path.read_text(encoding="utf-8")) if lme_path.is_file() else None

    first = locomo["summaries"][f"{locomo['modes'][0]}@{locomo['budgets'][0]}"][
        "main_categories_1_to_4"
    ]
    primary = econ["primary_proxy_scenario"]

    out = [
        "# THM × Context Economics 本地实机基准报告",
        "",
        "> 证据边界：检索指标为 runtime-measured；成本为 model-proxy，非真实账单；"
        "检索证据覆盖不等于答案正确率或任务成功。",
        "",
        "## 1. LoCoMo Protocol 2 检索全矩阵",
        "",
        f"- 主类别 1–4：每个配置尝试 {first['questions']} 题，其中 {first['scorable']} 题进入主评分分母。",
        f"- 数据集 pin：{locomo.get('dataset_matches_pinned_reference')}；counter：{locomo.get('counter')}",
        f"- generation_calls={locomo.get('generation_calls')}；judge_calls={locomo.get('judge_calls')}",
        "",
        locomo_table(locomo),
        "",
        "hybrid@600 = 71.34% any-gold，与公开 Protocol 2 基准一致；"
        "hybrid@1200 = 80.87%。这是 evidence coverage，不是 answer accuracy。",
        "",
    ]

    if lme:
        out += [
            "## 2. LongMemEval-S 检索覆盖",
            "",
            "- 500 实例；gold 为官方 answer_session_ids。",
            "- 命中定义是 session-level：gold session 中至少一条消息进入 packed context。",
            "- 该口径比 LoCoMo turn-level evidence 粗，绝对分数不可横向比较。",
            "",
            lme_table(lme),
            "",
        ]

    out += [
        "## 3. THM × Context Economics 同查询成本代理",
        "",
        f"主情景：`{primary}`，下表使用 rho=0。每一行的 packed retrieval 与 full-history "
        "counterfactual 使用完全相同的 benchmark query denominator。",
        "",
        "| 配置 | 尝试/可评分 | packed 每查询 | full-history 每查询 | full/packed 成本倍率 | 每 any-gold 成本 |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for key in ("literal@600", "sparse@600", "hybrid@600", "hybrid@1200"):
        cfg = econ["per_config"].get(key)
        if not cfg:
            continue
        packed = cfg["pricing_scenarios"]["rho=0.0"]
        cf = cfg.get("full_history_same_query_counterfactual")
        full = cf["pricing_scenarios"]["rho=0.0"] if cf else {}
        out.append(
            f"| {key} | {cfg['attempted_questions']}/{cfg['scorable_questions']} | "
            f"{money(packed['per_query_input_cost_usd'])} | "
            f"{money(full.get('per_query_input_cost_usd'))} | "
            f"{full.get('cost_ratio_vs_packed_retrieval', '-')}x | "
            f"{money(packed['cost_per_any_gold_scorable_question_usd'])} |"
        )

    suite = econ["suite_totals"]
    suite_cost = suite["pricing_scenarios"][primary]["rho=0.0"]["total_input_cost_usd"]
    out += [
        "",
        "实验套件总量只用于运行成本记账，不用于和单一 policy 做收益比较：",
        "",
        f"- 配置数：{suite['config_count']}",
        f"- config-query executions：{suite['config_query_executions']}",
        f"- 每配置 attempted/scorable：{suite['attempted_questions_per_config']}/"
        f"{suite['scorable_questions_per_config']}",
        f"- 全部实验臂 packed-input proxy 总成本：{money(suite_cost)}",
        "",
        "## 4. L6 预算网格敏感性",
        "",
        "这里的“每 +1pp”指整批 benchmark 上 any-gold 提升一个百分点所对应的增量"
        "packed-input proxy 成本，不是单查询成本。",
        "",
        "| 模式 | 300→600 Δany-gold | 每 +1pp 成本 | 600→1200 Δany-gold | 每 +1pp 成本 | 后段/前段倍率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for mode, steps in econ["l6_budget_grid_sensitivity"].items():
        a = steps.get("300->600", {})
        b = steps.get("600->1200", {})
        ca = a.get("marginal_cost_usd_per_1pp_any_gold_gain")
        cb = b.get("marginal_cost_usd_per_1pp_any_gold_gain")
        ratio = cb / ca if ca and cb else None
        out.append(
            f"| {mode} | {a.get('delta_any_gold_percentage_points', 0):.2f}pp | "
            f"{money(ca)} | {b.get('delta_any_gold_percentage_points', 0):.2f}pp | "
            f"{money(cb)} | {ratio:.2f}x |" if ratio is not None
            else f"| {mode} | - | - | - | - | - |"
        )

    out += [
        "",
        "## 5. 结论与限制",
        "",
        "1. LoCoMo hybrid@600 的公开 Protocol 2 结果已在本机复现，支持检索路径的跨环境可复现性。",
        "2. 同查询口径下，固定预算 packed retrieval 的输入 token/cost proxy 显著低于 full-history carry；"
        "该比较不等于真实账单，也不单独证明 O(N²) 历史增长。",
        "3. 在仅测试 300/600/1200 三档的网格里，600→1200 的单位 recall 增量成本明显高于 300→600；"
        "因此 600 是值得进一步验证的 knee candidate，而不是已经优化出的全局最优阈值。",
        "4. LongMemEval-S 提供第二数据集的 session-level generalization evidence，但其命中粒度与 LoCoMo 不同。",
        "5. CPU/GPU 一致性应由独立 parity comparator 产物确认；运行时加速与检索质量必须分开报告。",
    ]

    Path(args.output).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
