#!/usr/bin/env python3
"""Generate a consolidated THM x Context Economics machine-test report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PINNED_HYBRID_600_ANY_GOLD_PERCENT = 71.34


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


def validate_locomo_bridge_pair(locomo: dict, econ: dict) -> None:
    """Fail closed unless retrieval and economics describe the same benchmark."""
    benchmark = econ.get("benchmark")
    if not isinstance(benchmark, dict):
        raise ValueError("bridge-v2 artifact is missing benchmark identity")

    fields = (
        "dataset_sha256",
        "protocol",
        "counter",
        "modes",
        "budgets",
        "generation_calls",
        "judge_calls",
    )
    mismatches = []
    for field in fields:
        if locomo.get(field) != benchmark.get(field):
            mismatches.append(
                f"{field}: locomo={locomo.get(field)!r} bridge={benchmark.get(field)!r}"
            )
    if mismatches:
        raise ValueError(
            "LoCoMo retrieval artifact does not match bridge-v2 benchmark identity: "
            + "; ".join(mismatches)
        )

    counterfactual = benchmark.get("counterfactual_dataset_sha256")
    if counterfactual is not None and counterfactual != locomo.get("dataset_sha256"):
        raise ValueError(
            "bridge-v2 counterfactual dataset does not match LoCoMo retrieval dataset"
        )
    if benchmark.get("counterfactual_dataset_matches_benchmark") is False:
        raise ValueError("bridge-v2 records a failed counterfactual dataset match")


def main_summary(data: dict, mode: str, budget: int) -> dict | None:
    summary = data.get("summaries", {}).get(f"{mode}@{budget}")
    if not isinstance(summary, dict):
        return None
    value = summary.get("main_categories_1_to_4")
    return value if isinstance(value, dict) else None


def locomo_observation(data: dict) -> str:
    """Describe only measurements actually present in the supplied artifact."""
    parts: list[str] = []
    hybrid_600 = main_summary(data, "hybrid", 600)
    if hybrid_600 is not None:
        pct = float(hybrid_600["any_gold_hit_rate"]) * 100.0
        claim = f"hybrid@600 = {pct:.2f}% any-gold"
        pinned = (
            data.get("dataset_matches_pinned_reference") is True
            and data.get("protocol") == 2
            and data.get("counter") == "cl100k_base"
            and round(pct, 2) == PINNED_HYBRID_600_ANY_GOLD_PERCENT
        )
        if pinned:
            claim += (
                f"，与当前仓库固定 Protocol 2 reference "
                f"{PINNED_HYBRID_600_ANY_GOLD_PERCENT:.2f}% 一致"
            )
        else:
            claim += "；该 artifact 不满足固定 reference reproduction 的全部条件"
        parts.append(claim)

    hybrid_1200 = main_summary(data, "hybrid", 1200)
    if hybrid_1200 is not None:
        pct = float(hybrid_1200["any_gold_hit_rate"]) * 100.0
        parts.append(f"hybrid@1200 = {pct:.2f}% any-gold")

    if not parts:
        return "当前 artifact 未包含 hybrid@600 / hybrid@1200，因此不生成这两项结论。"
    return "；".join(parts) + "。这些都是 evidence coverage，不是 answer accuracy。"


def economics_rows(econ: dict) -> list[str]:
    benchmark = econ.get("benchmark", {})
    modes = benchmark.get("modes") or []
    budgets = benchmark.get("budgets") or []
    lines: list[str] = []
    for mode in modes:
        for budget in budgets:
            key = f"{mode}@{budget}"
            cfg = econ.get("per_config", {}).get(key)
            if not cfg:
                continue
            packed = cfg["pricing_scenarios"]["rho=0.0"]
            cf = cfg.get("full_history_same_query_counterfactual")
            full = cf["pricing_scenarios"]["rho=0.0"] if cf else {}
            ratio = full.get("cost_ratio_vs_packed_retrieval")
            ratio_text = "-" if ratio is None else f"{ratio:.2f}x"
            lines.append(
                f"| {key} | {cfg['attempted_questions']}/{cfg['scorable_questions']} | "
                f"{money(packed['per_query_input_cost_usd'])} | "
                f"{money(full.get('per_query_input_cost_usd'))} | "
                f"{ratio_text} | "
                f"{money(packed['cost_per_any_gold_scorable_question_usd'])} |"
            )
    if not lines:
        lines.append("| - | - | - | - | - | - |")
    return lines


def _step_sort_key(value: str) -> tuple[int, int, str]:
    try:
        lo, hi = value.split("->", 1)
        return int(lo), int(hi), value
    except (TypeError, ValueError):
        return (10**12, 10**12, str(value))


def l6_rows(econ: dict) -> list[str]:
    lines: list[str] = []
    for mode, steps in econ.get("l6_budget_grid_sensitivity", {}).items():
        for step_name in sorted(steps, key=_step_sort_key):
            step = steps[step_name]
            lines.append(
                f"| {mode} | {step_name} | "
                f"{step.get('delta_any_gold_percentage_points', 0):.2f}pp | "
                f"{money(step.get('marginal_cost_usd_per_1pp_any_gold_gain'))} |"
            )
    if not lines:
        lines.append("| - | - | - | - |")
    return lines


def knee_observation(econ: dict) -> str:
    """Emit a 600-token knee candidate only when the artifact supports it."""
    steps = econ.get("l6_budget_grid_sensitivity", {}).get("hybrid", {})
    early = steps.get("300->600")
    late = steps.get("600->1200")
    if not early or not late:
        return (
            "当前 artifact 缺少相邻的 hybrid 300→600 与 600→1200 两段敏感性数据，"
            "因此不作 600-token knee claim。"
        )

    early_pp = early.get("delta_any_gold_percentage_points")
    late_pp = late.get("delta_any_gold_percentage_points")
    early_cost = early.get("marginal_cost_usd_per_1pp_any_gold_gain")
    late_cost = late.get("marginal_cost_usd_per_1pp_any_gold_gain")
    if not all(isinstance(v, (int, float)) for v in (early_pp, late_pp, early_cost, late_cost)):
        return "当前 artifact 的 hybrid 网格缺少可比较的正向边际成本，因此不作 600-token knee claim。"
    if early_pp <= 0 or late_pp <= 0 or early_cost <= 0 or late_cost <= 0:
        return "当前 artifact 的 hybrid 网格没有两段正向 recall 增益，因此不作 600-token knee claim。"
    if late_cost <= early_cost:
        return (
            "当前 artifact 中 hybrid 600→1200 的每 +1pp 边际成本并未高于 300→600，"
            "因此数据不支持 600-token knee candidate。"
        )

    ratio = late_cost / early_cost
    return (
        "在当前 artifact 的 hybrid 300/600/1200 网格里，600→1200 的每 +1pp "
        f"边际成本为 {money(late_cost)}，高于 300→600 的 {money(early_cost)} "
        f"（{ratio:.2f}x）；因此 600 仅可称为值得进一步验证的 knee candidate，"
        "不是全局最优阈值。"
    )


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
    validate_locomo_bridge_pair(locomo, econ)

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
        locomo_observation(locomo),
        "",
    ]

    if lme:
        out += [
            "## 2. LongMemEval-S 检索覆盖",
            "",
            f"- 实例数：{lme.get('instances', lme.get('questions', 'artifact-defined'))}；gold 为官方 answer_session_ids。",
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
        *economics_rows(econ),
    ]

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
        "packed-input proxy 成本，不是单查询成本。表格直接枚举 artifact 中实际存在的相邻预算步长。",
        "",
        "| 模式 | 预算步长 | Δany-gold | 每 +1pp 成本 |",
        "|---|---|---:|---:|",
        *l6_rows(econ),
        "",
        "## 5. 结论与限制",
        "",
        f"1. {locomo_observation(locomo)}",
        "2. 同查询口径下，固定预算 packed retrieval 的输入 token/cost proxy 可与 full-history carry 直接比较；"
        "该比较不等于真实账单，也不单独证明 O(N²) 历史增长。",
        f"3. {knee_observation(econ)}",
    ]

    if lme:
        out.append(
            "4. LongMemEval-S 提供第二数据集的 session-level generalization evidence，"
            "但其命中粒度与 LoCoMo 不同。"
        )
    else:
        out.append("4. 当前报告未提供 LongMemEval-S artifact，因此不作第二数据集 generalization claim。")
    out.append(
        "5. CPU/GPU 一致性应由独立 parity comparator 产物确认；运行时加速与检索质量必须分开报告。"
    )

    Path(args.output).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
