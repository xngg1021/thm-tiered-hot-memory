#!/usr/bin/env python3
"""One-shot THM 1.4 documentation/runtime-metadata synchronization.

This file is intentionally temporary and is removed after it generates the
reviewable documentation commit on the dedicated closeout branch.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MILESTONE = "e6e4dda5835e3cb345207457d5491131c6959b2c"
ARCHIVE = "archive/v1.4.0-stable"
START = "<!-- current-v1.4-status:start -->"
END = "<!-- current-v1.4-status:end -->"

FOUNDATION_DOCS = [
    "docs/01-研究综述.md",
    "docs/02-架构设计.md",
    "docs/03-validation-contract.md",
    "docs/04-related-work.md",
    "docs/05-hermes-upstream.md",
    "docs/06-engine-guide.md",
    "docs/09-retrieval-and-measurement.md",
    "docs/10-recall-integration-review.md",
    "docs/11-harness-adapters.md",
]

GENERIC_STATUS = f"""{START}
> **Current release status — THM 1.4.0 accepted/stable implementation milestone.** Stable code/content milestone: `{MILESTONE}`; immutable recovery pointer: `{ARCHIVE}`. This document retains its original research/design/1.2/1.3 scope as historical foundation rather than rewriting old evidence as a new result. Current implementation state is tracked in [07-implementation-status.md](07-implementation-status.md), the 1.4 shadow control plane in [14-residency-control-plane.md](14-residency-control-plane.md), the opt-in Hermes T1 surface in [15-hermes-warm-directory.md](15-hermes-warm-directory.md), and the exact acceptance record in [the 1.4 closeout](../reports/2026-09-07-v1.4-closeout.md).
{END}"""

STATUS_13 = f"""{START}
> **Current release status — implemented in THM 1.4.0.** The hardware-analogy audit below is the design provenance for the accepted shadow miss/residency/prefetch/budget control surface. Stable code/content milestone: `{MILESTONE}`; recovery pointer: `{ARCHIVE}`. The implementation remains advisory: it does not silently move T0–T3 or mutate Hermes/T0 budgets, and production superiority still requires held-out runtime/task A/B evidence. See [14-residency-control-plane.md](14-residency-control-plane.md) and [15-hermes-warm-directory.md](15-hermes-warm-directory.md).
{END}"""

STATUS_14 = f"""{START}
> **Release status — accepted/stable implementation.** The code described here is frozen at `{MILESTONE}` with recovery pointer `{ARCHIVE}`. “Shadow” describes the advisory/non-mutating policy boundary, not unfinished implementation. Automatic tier movement and automatic resident-budget mutation remain deliberately disabled until held-out runtime/task evidence justifies them.
{END}"""

STATUS_15 = f"""{START}
> **Release status — accepted/stable opt-in runtime surface.** The implementation described here is part of THM 1.4.0 frozen at `{MILESTONE}` with recovery pointer `{ARCHIVE}`. It is disabled by default, session-frozen when enabled, and remains independent of the shadow residency/prefetch/budget recommender.
{END}"""

LOCALE_SECTIONS = {
    "README.zh-CN.md": f"""## THM 1.4 当前稳定状态

THM 1.4 已完成并冻结为 **accepted/stable implementation milestone**。稳定代码/内容里程碑为 `{MILESTONE}`，恢复指针为 `{ARCHIVE}`。T0–T3 四层模型保持不变。

1.4 在既有 1.3 harness-neutral 召回层之上新增：显式 resident/hard miss 与 planned retrieval telemetry、严格 locator-only 的 T1 温层目录、基于 avoidable-miss penalty 与 resident carry cost 的 shadow T0 recommendation、精确有界 0/1 packing、只由真实 demand co-occurrence 训练的 bounded prefetch、以及只给出建议而不自动改预算的 resident-budget feedback。Hermes 另提供默认关闭的 session-frozen T1 locator snapshot。

这些能力已经通过 1.4 的 correctness、Hermes 与 multi-harness 验收；1.4 没有修改 retrieval path，因此没有冒充产生新的 LoCoMo/Protocol 2 数字。自动 T0–T3 换层和自动预算修改仍保持关闭，直到真实留出任务 A/B 能同时证明质量、成本、延迟和 reacquisition 改善。详见 [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md) 与 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)。""",
    "README.zh-TW.md": f"""## THM 1.4 目前穩定狀態

THM 1.4 已完成並凍結為 **accepted/stable implementation milestone**。穩定程式碼/內容里程碑為 `{MILESTONE}`，恢復指標為 `{ARCHIVE}`。T0–T3 四層模型保持不變。

1.4 在既有 1.3 harness-neutral 召回層之上新增：顯式 resident/hard miss 與 planned retrieval telemetry、嚴格 locator-only 的 T1 溫層目錄、基於 avoidable-miss penalty 與 resident carry cost 的 shadow T0 recommendation、精確有界 0/1 packing、只由真實 demand co-occurrence 訓練的 bounded prefetch，以及只提供建議而不自動改預算的 resident-budget feedback。Hermes 另提供預設關閉的 session-frozen T1 locator snapshot。

這些能力已通過 1.4 correctness、Hermes 與 multi-harness 驗收；1.4 沒有修改 retrieval path，因此沒有宣稱產生新的 LoCoMo/Protocol 2 數字。自動 T0–T3 換層和自動預算修改仍保持關閉，直到真實留出任務 A/B 能同時證明品質、成本、延遲和 reacquisition 改善。詳見 [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md) 與 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)。""",
    "README.ja.md": f"""## THM 1.4 の現在の安定状態

THM 1.4 は **accepted/stable implementation milestone** として完了・凍結されています。安定コード/コンテンツのマイルストーンは `{MILESTONE}`、復旧ポインタは `{ARCHIVE}` です。T0–T3 の4層モデルは変更していません。

1.4 は既存の 1.3 harness-neutral recall に加えて、resident/hard miss と planned retrieval の明示 telemetry、厳密な locator-only T1 warm directory、avoidable-miss penalty と resident carry cost に基づく shadow T0 recommendation、境界付きの正確な 0/1 packing、実 demand の co-occurrence だけで学習する bounded prefetch、予算を自動変更しない resident-budget feedback を追加します。Hermes には既定で無効な session-frozen T1 locator snapshot もあります。

これらは 1.4 correctness、Hermes、multi-harness の受け入れ検証を通過しています。1.4 は retrieval path を変更していないため、新しい LoCoMo/Protocol 2 数値は主張しません。自動 T0–T3 移動と自動予算変更は、held-out runtime/task A/B が品質・コスト・遅延・reacquisition の改善を示すまで無効のままです。詳細は [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md)、[1.4 closeout](reports/2026-09-07-v1.4-closeout.md) を参照してください。""",
    "README.ko.md": f"""## THM 1.4 현재 안정 상태

THM 1.4는 **accepted/stable implementation milestone**로 완료되어 고정되었습니다. 안정 코드/콘텐츠 마일스톤은 `{MILESTONE}`, 복구 포인터는 `{ARCHIVE}`입니다. T0–T3 4계층 모델은 그대로 유지됩니다.

1.4는 기존 1.3 harness-neutral recall 위에 명시적 resident/hard miss 및 planned retrieval telemetry, 엄격한 locator-only T1 warm directory, avoidable-miss penalty와 resident carry cost 기반 shadow T0 recommendation, 경계가 있는 정확한 0/1 packing, 실제 demand co-occurrence만 학습하는 bounded prefetch, 예산을 자동 변경하지 않는 resident-budget feedback을 추가합니다. Hermes에는 기본 비활성화된 session-frozen T1 locator snapshot도 있습니다.

이 기능들은 1.4 correctness, Hermes, multi-harness 승인 검증을 통과했습니다. 1.4는 retrieval path를 변경하지 않았으므로 새로운 LoCoMo/Protocol 2 수치를 주장하지 않습니다. 자동 T0–T3 이동과 자동 예산 변경은 held-out runtime/task A/B가 품질·비용·지연·reacquisition 개선을 입증할 때까지 비활성화 상태입니다. 자세한 내용은 [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md), [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)을 참조하십시오.""",
    "README.es.md": f"""## Estado estable actual de THM 1.4

THM 1.4 está terminado y congelado como **accepted/stable implementation milestone**. El hito estable de código/contenido es `{MILESTONE}` y el puntero de recuperación es `{ARCHIVE}`. El modelo de cuatro niveles T0–T3 no cambia.

Sobre la capa de recall harness-neutral de 1.3, 1.4 añade telemetry explícita de resident/hard miss y planned retrieval, un directorio T1 estrictamente locator-only, recomendación shadow de T0 basada en avoidable-miss penalty frente a resident carry cost, packing 0/1 exacto y acotado, prefetch acotado entrenado sólo por co-occurrence de demanda real y feedback de resident budget que nunca modifica el presupuesto automáticamente. Hermes también dispone de un T1 locator snapshot session-frozen y desactivado por defecto.

Estas superficies superaron la aceptación correctness, Hermes y multi-harness de 1.4. Como 1.4 no cambió el retrieval path, no se atribuyen nuevos números LoCoMo/Protocol 2. El movimiento automático T0–T3 y el cambio automático de presupuesto siguen desactivados hasta que A/B held-out de runtime/tareas demuestre mejoras conjuntas de calidad, coste, latencia y reacquisition. Véanse [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) y [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).""",
    "README.fr.md": f"""## État stable actuel de THM 1.4

THM 1.4 est terminé et figé comme **accepted/stable implementation milestone**. Le jalon stable code/contenu est `{MILESTONE}` et le pointeur de restauration est `{ARCHIVE}`. Le modèle à quatre niveaux T0–T3 reste inchangé.

Au-dessus du recall harness-neutral de 1.3, la 1.4 ajoute une telemetry explicite resident/hard miss et planned retrieval, un répertoire T1 strictement locator-only, une recommandation shadow T0 fondée sur avoidable-miss penalty face au resident carry cost, un packing 0/1 exact et borné, un prefetch borné entraîné uniquement par la co-occurrence de demande réelle, et un resident-budget feedback qui ne modifie jamais automatiquement le budget. Hermes dispose aussi d'un T1 locator snapshot session-frozen, désactivé par défaut.

Ces surfaces ont passé l'acceptation correctness, Hermes et multi-harness de la 1.4. La 1.4 n'ayant pas modifié le retrieval path, aucun nouveau chiffre LoCoMo/Protocol 2 n'est revendiqué. Le mouvement automatique T0–T3 et la modification automatique du budget restent désactivés jusqu'à ce qu'un A/B held-out runtime/tâches démontre simultanément des gains de qualité, coût, latence et reacquisition. Voir [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) et [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).""",
    "README.de.md": f"""## Aktueller stabiler Stand von THM 1.4

THM 1.4 ist als **accepted/stable implementation milestone** abgeschlossen und eingefroren. Der stabile Code-/Content-Meilenstein ist `{MILESTONE}`, der Recovery-Pointer `{ARCHIVE}`. Das Vier-Stufen-Modell T0–T3 bleibt unverändert.

Auf der harness-neutralen Recall-Schicht von 1.3 ergänzt 1.4 explizite resident/hard-miss- und planned-retrieval-Telemetrie, ein strikt locator-only T1-Warmverzeichnis, eine Shadow-T0-Empfehlung aus avoidable-miss penalty gegenüber resident carry cost, exaktes begrenztes 0/1-Packing, begrenztes Prefetching, das nur aus echter Demand-Co-Occurrence lernt, sowie resident-budget feedback ohne automatische Budgetänderung. Hermes erhält zusätzlich einen standardmäßig deaktivierten session-frozen T1 locator snapshot.

Diese Oberflächen haben die 1.4-Akzeptanz für correctness, Hermes und multi-harness bestanden. Da 1.4 den retrieval path nicht geändert hat, werden keine neuen LoCoMo/Protocol-2-Zahlen beansprucht. Automatische T0–T3-Bewegung und automatische Budgetänderung bleiben deaktiviert, bis held-out Runtime-/Task-A/B gemeinsam Verbesserungen bei Qualität, Kosten, Latenz und Reacquisition nachweist. Siehe [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) und [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).""",
}

ENGLISH_14 = f"""## THM 1.4 current stable status

THM 1.4 is complete and frozen as an **accepted/stable implementation milestone**. The stable code/content milestone is `{MILESTONE}` and the recovery pointer is `{ARCHIVE}`; the T0–T3 four-tier model is unchanged.

On top of the 1.3 harness-neutral recall layer, 1.4 adds explicit resident/hard-miss and planned-retrieval telemetry, a strict locator-only T1 warm directory, shadow T0 residency recommendations based on avoidable-miss penalty versus resident carry cost, exact bounded 0/1 packing, bounded prefetch trained only from real demand co-occurrence, and resident-budget feedback that never mutates budgets automatically. Hermes also exposes a default-off, session-frozen T1 locator snapshot.

These surfaces passed the accepted 1.4 correctness, Hermes and multi-harness validation. Because 1.4 did not change the retrieval path, it does not claim a new LoCoMo/Protocol 2 result. Automatic T0–T3 movement and automatic budget mutation remain disabled until held-out runtime/task A/B evidence jointly supports quality, cost, latency and reacquisition improvement. See [the 1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md), and [the 1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**."""


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_managed_after_title(path: str, block: str) -> None:
    text = read(path)
    if START in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        text = before.rstrip() + "\n\n" + block + after
    else:
        first_nl = text.find("\n")
        if first_nl < 0 or not text.startswith("# "):
            raise RuntimeError(f"missing H1 in {path}")
        text = text[: first_nl + 1].rstrip() + "\n\n" + block + "\n\n" + text[first_nl + 1 :].lstrip()
    write(path, text)


def update_localized() -> None:
    old_identity = "Version identity: **1.3.0 accepted/stable**."
    new_identity = "Version identity: **1.4.0 accepted/stable implementation milestone**."
    for filename, section in LOCALE_SECTIONS.items():
        text = read(filename)
        if "## THM 1.4" in text or "## État stable actuel de THM 1.4" in text or "## Aktueller stabiler Stand von THM 1.4" in text:
            # Regeneration is intended to be idempotent only on a clean pre-sync tree.
            raise RuntimeError(f"unexpected existing 1.4 locale section in {filename}")
        if old_identity not in text:
            raise RuntimeError(f"missing old version identity in {filename}")
        text = text.replace(old_identity, section.rstrip() + "\n\n" + new_identity, 1)
        write(filename, text)


def update_english_homepage() -> None:
    text = read("README.md")
    marker = "## Evidence boundaries"
    if marker not in text:
        raise RuntimeError("missing English evidence-boundary anchor")
    if "## THM 1.4 current stable status" in text:
        raise RuntimeError("unexpected existing English 1.4 section")
    text = text.replace(marker, ENGLISH_14.rstrip() + "\n\n" + marker, 1)
    write("README.md", text)


def main() -> None:
    for path in FOUNDATION_DOCS:
        replace_managed_after_title(path, GENERIC_STATUS)

    replace_managed_after_title("docs/13-hardware-inspired-adaptive-residency.md", STATUS_13)
    replace_managed_after_title("docs/14-residency-control-plane.md", STATUS_14)
    replace_managed_after_title("docs/15-hermes-warm-directory.md", STATUS_15)

    p13 = "docs/13-hardware-inspired-adaptive-residency.md"
    text = read(p13)
    text = text.replace(
        "状态：**研究/影子测量扩展；不改变当前 THM 1.1.1 residency、activity、validity 或索引写入语义。**",
        "状态：**THM 1.4 已实现并完成 accepted/stable 工程验收；控制面保持 shadow/advisory，不自动修改 T0–T3、budget、activity、validity 或原生记忆。**",
    )
    text = text.replace("最值得进入下一阶段的组合：", "THM 1.4 已实现并冻结为 shadow/control surface 的组合：")
    write(p13, text)

    p11 = "docs/11-harness-adapters.md"
    text = read(p11).replace(
        "# THM 1.3 — Harness adapters",
        "# THM harness adapters — 1.3 foundation and 1.4 current integration",
        1,
    )
    write(p11, text)

    p09 = "docs/09-retrieval-and-measurement.md"
    text = read(p09).replace(
        "# THM 1.2: retrieval, observation, decay and measurement",
        "# THM retrieval, observation, decay and measurement — 1.2 foundation, current in 1.4",
        1,
    )
    write(p09, text)

    p10 = "docs/10-recall-integration-review.md"
    text = read(p10).replace(
        "# THM 1.2 召回扩展：复核、性能补修与评测勘误",
        "# THM 召回扩展：1.2 复核基础与 1.4 当前边界",
        1,
    )
    write(p10, text)

    changelog = read("CHANGELOG.md")
    changelog = changelog.replace(
        "## 1.4.0 development — shadow residency control",
        "## 1.4.0 accepted/stable — shadow residency control",
        1,
    )
    heading = "## 1.4.0 accepted/stable — shadow residency control\n"
    if heading in changelog and "Stable code/content milestone:" not in changelog.split(heading, 1)[1][:500]:
        changelog = changelog.replace(
            heading,
            heading + f"\nStable code/content milestone: `{MILESTONE}`. Recovery pointer: `{ARCHIVE}`. Acceptance record: [human](reports/2026-09-07-v1.4-closeout.md) · [JSON](reports/2026-09-07-v1.4-closeout.json).\n",
            1,
        )
    write("CHANGELOG.md", changelog)

    docs_index = read("docs/README.md")
    if START not in docs_index:
        first_nl = docs_index.find("\n")
        docs_index = docs_index[: first_nl + 1].rstrip() + "\n\n" + GENERIC_STATUS + "\n\n" + docs_index[first_nl + 1 :].lstrip()
    docs_index = docs_index.replace("1.4 development", "1.4 accepted/stable")
    write("docs/README.md", docs_index)

    update_localized()
    # Root locale panels are generated from the standalone localized files.
    import subprocess
    subprocess.run(["python", "scripts/sync_readme_locales.py"], cwd=ROOT, check=True)
    update_english_homepage()

    # Runtime/plugin version metadata that must match the installed 1.4 package.
    plugin = read("plugins/thm/plugin.yaml")
    plugin = plugin.replace("version: 1.3.0", "version: 1.4.0", 1)
    plugin = plugin.replace(
        'description: "Local THM retrieval provider with explicit scope, context budget, and harness adapters."',
        'description: "Local THM retrieval provider with explicit scope/budget, harness adapters, shadow residency control, and opt-in Hermes T1 locator snapshot."',
        1,
    )
    write("plugins/thm/plugin.yaml", plugin)

    legacy = read("thm/mcp_legacy_server.py")
    legacy = legacy.replace('return "1.3.0"', 'return "1.4.0"', 1)
    write("thm/mcp_legacy_server.py", legacy)

    checker = read("scripts/check_docs.py")
    checker = checker.replace(
        "for marker in ('1.3.0', 'Claude Code', 'Codex CLI', 'Gemini CLI',\n                           'MCP v2', 'accepted/stable'):",
        "for marker in ('1.3.0', '1.4.0', 'archive/v1.4.0-stable', 'Claude Code',\n                           'Codex CLI', 'Gemini CLI', 'MCP v2', 'accepted/stable'):",
        1,
    )
    checker = checker.replace(
        "errors.append(f'{localized}: missing 1.3 parity marker {marker}')",
        "errors.append(f'{localized}: missing localized release parity marker {marker}')",
        1,
    )
    old = """            if not match or match.group(1).strip() != expected_body:\n                errors.append(f'{localized}: homepage language panel is missing or stale')\n"""
    new = old + """        homepage = texts.get('README.md', '')\n        for marker in ('1.4.0 accepted/stable implementation milestone',\n                       'archive/v1.4.0-stable',\n                       'docs/14-residency-control-plane.md',\n                       'docs/15-hermes-warm-directory.md'):\n            if marker not in homepage:\n                errors.append(f'README.md: missing current 1.4 homepage marker {marker}')\n"""
    if old not in checker:
        raise RuntimeError("check_docs homepage parity anchor changed")
    checker = checker.replace(old, new, 1)
    write("scripts/check_docs.py", checker)

    # Guard that all current-facing surfaces now expose 1.4 while historical evidence remains intact.
    required = {
        "README.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE, "THM 1.4 current stable status"],
        "README.zh-CN.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.zh-TW.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.ja.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.ko.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.es.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.fr.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "README.de.md": ["1.4.0 accepted/stable implementation milestone", ARCHIVE],
        "docs/13-hardware-inspired-adaptive-residency.md": ["THM 1.4 已实现", ARCHIVE],
        "docs/14-residency-control-plane.md": ["accepted/stable implementation", ARCHIVE],
        "docs/15-hermes-warm-directory.md": ["accepted/stable opt-in runtime surface", ARCHIVE],
        "plugins/thm/plugin.yaml": ["version: 1.4.0"],
        "thm/mcp_legacy_server.py": ['return "1.4.0"'],
    }
    for path, markers in required.items():
        body = read(path)
        for marker in markers:
            if marker not in body:
                raise RuntimeError(f"{path}: missing generated marker {marker}")


if __name__ == "__main__":
    main()
