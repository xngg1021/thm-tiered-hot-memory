#!/usr/bin/env python3
"""One-shot generator for the THM 1.4 localized README status section."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECTIONS = {
    "README.zh-CN.md": """## THM 1.4 当前稳定里程碑

**THM 1.4.0 已在实现/集成层面收口。** 稳定代码里程碑为 `e6e4dda5835e3cb345207457d5491131c6959b2c`，恢复指针为 `archive/v1.4.0-stable`。1.4 保持 T0–T3 四层定义不变，新增严格的 miss/prefetch telemetry、T1 locator-only 温层目录、基于可避免 miss 成本的 shadow T0 驻留建议、受限 co-demand 预取和 shadow 驻留预算反馈。自动晋升/降级与自动预算修改仍然关闭，必须等真实留出任务 A/B 证明收益后才会考虑启用。

Hermes 可选 T1 目录默认关闭（`warm_directory_budget=0`）；启用后只注入经过路径与文件存在性验证的 locator，在 session 边界重建快照，当前 session 内的记忆写入不会偷偷刷新 prompt。1.4 接受证据和精确版本边界见 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) 与 [版本历史](docs/12-version-history.md)。
""",
    "README.zh-TW.md": """## THM 1.4 目前穩定里程碑

**THM 1.4.0 已在實作／整合層面收口。** 穩定程式碼里程碑為 `e6e4dda5835e3cb345207457d5491131c6959b2c`，恢復指標為 `archive/v1.4.0-stable`。1.4 保持 T0–T3 四層定義不變，新增嚴格的 miss/prefetch telemetry、T1 locator-only 溫層目錄、基於可避免 miss 成本的 shadow T0 駐留建議、受限 co-demand 預取與 shadow 駐留預算回饋。自動晉升／降級與自動預算修改仍然關閉，必須等真實留出任務 A/B 證明收益後才會考慮啟用。

Hermes 可選 T1 目錄預設關閉（`warm_directory_budget=0`）；啟用後只注入經過路徑與檔案存在性驗證的 locator，在 session 邊界重建快照，當前 session 內的記憶寫入不會偷偷刷新 prompt。1.4 接受證據與精確版本邊界見 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) 與 [版本歷史](docs/12-version-history.md)。
""",
    "README.ja.md": """## THM 1.4 現在の安定マイルストーン

**THM 1.4.0 は実装／統合レベルでクローズしました。** 安定コード・マイルストーンは `e6e4dda5835e3cb345207457d5491131c6959b2c`、復旧ポインタは `archive/v1.4.0-stable` です。1.4 は T0–T3 の4階層定義を変更せず、厳密な miss/prefetch telemetry、T1 locator-only ウォームディレクトリ、回避可能な miss コストに基づく shadow T0 residency 推奨、制限付き co-demand prefetch、shadow residency budget feedback を追加します。自動昇格／降格と自動予算変更は引き続き無効で、実際のホールドアウト・タスク A/B で利益が確認されるまで有効化しません。

Hermes のオプション T1 ディレクトリは既定で無効（`warm_directory_budget=0`）です。有効化した場合も、パスと実在ファイルを検証済みの locator だけを注入し、session 境界でのみスナップショットを再構築します。現在の session 中の memory write は prompt を暗黙に更新しません。1.4 の受入証拠と正確な版境界は [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) と [version history](docs/12-version-history.md) を参照してください。
""",
    "README.ko.md": """## THM 1.4 현재 안정 마일스톤

**THM 1.4.0은 구현/통합 수준에서 마감되었습니다.** 안정 코드 마일스톤은 `e6e4dda5835e3cb345207457d5491131c6959b2c`, 복구 포인터는 `archive/v1.4.0-stable`입니다. 1.4는 T0–T3 네 계층 정의를 유지하면서 엄격한 miss/prefetch telemetry, T1 locator-only warm directory, 회피 가능한 miss 비용 기반 shadow T0 residency 추천, 제한된 co-demand prefetch, shadow residency budget feedback을 추가합니다. 자동 승격/강등과 자동 예산 변경은 계속 비활성화되며 실제 holdout task A/B에서 이득이 입증되기 전에는 활성화하지 않습니다.

Hermes의 선택적 T1 directory는 기본적으로 비활성화(`warm_directory_budget=0`)됩니다. 활성화해도 경로와 실제 파일 존재를 검증한 locator만 주입하며 session 경계에서만 snapshot을 다시 만듭니다. 현재 session 중 memory write는 prompt를 암묵적으로 새로 고치지 않습니다. 1.4 승인 증거와 정확한 버전 경계는 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) 및 [version history](docs/12-version-history.md)를 참조하십시오.
""",
    "README.es.md": """## Hito estable actual de THM 1.4

**THM 1.4.0 queda cerrado a nivel de implementación e integración.** El hito estable de código es `e6e4dda5835e3cb345207457d5491131c6959b2c` y el puntero de recuperación es `archive/v1.4.0-stable`. La versión 1.4 mantiene intactos los cuatro tiers T0–T3 y añade telemetría estricta de miss/prefetch, un directorio T1 solo de locators, recomendaciones shadow de residencia T0 basadas en el coste de misses evitables, prefetch co-demand acotado y feedback shadow del presupuesto de residencia. La promoción/degradación automática y los cambios automáticos de presupuesto siguen desactivados hasta que pruebas A/B con tareas reales reservadas demuestren una ventaja.

El directorio T1 opcional de Hermes está desactivado por defecto (`warm_directory_budget=0`). Al activarlo solo se inyectan locators cuyo path y archivo real hayan sido verificados, y el snapshot se reconstruye únicamente en límites de session; una escritura de memoria dentro de la session actual no refresca el prompt de forma implícita. Véanse [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) y [version history](docs/12-version-history.md) para la evidencia de aceptación y los límites exactos de versión.
""",
    "README.fr.md": """## Jalon stable actuel de THM 1.4

**THM 1.4.0 est clôturé au niveau implémentation/intégration.** Le jalon de code stable est `e6e4dda5835e3cb345207457d5491131c6959b2c` et le pointeur de restauration est `archive/v1.4.0-stable`. La version 1.4 conserve les quatre tiers T0–T3 et ajoute une télémétrie stricte des miss/prefetch, un répertoire T1 locator-only, des recommandations shadow de résidence T0 fondées sur le coût des misses évitables, un prefetch co-demand borné et un feedback shadow du budget de résidence. La promotion/rétrogradation automatique et la modification automatique du budget restent désactivées jusqu'à ce que des tests A/B sur des tâches réelles réservées démontrent un gain.

Le répertoire T1 optionnel de Hermes est désactivé par défaut (`warm_directory_budget=0`). Lorsqu'il est activé, seuls des locators dont le chemin et le fichier réel ont été vérifiés sont injectés, et le snapshot n'est reconstruit qu'aux frontières de session ; une écriture mémoire pendant la session courante ne rafraîchit pas implicitement le prompt. Voir [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) et [version history](docs/12-version-history.md) pour les preuves d'acceptation et les limites de version exactes.
""",
    "README.de.md": """## Aktueller stabiler Meilenstein THM 1.4

**THM 1.4.0 ist auf Implementierungs-/Integrationsebene abgeschlossen.** Der stabile Code-Meilenstein ist `e6e4dda5835e3cb345207457d5491131c6959b2c`, der Wiederherstellungszeiger `archive/v1.4.0-stable`. 1.4 lässt die vier T0–T3-Tiers unverändert und ergänzt strikte Miss/Prefetch-Telemetrie, ein T1-Locator-only-Warmverzeichnis, Shadow-T0-Residency-Empfehlungen auf Basis vermeidbarer Miss-Kosten, begrenztes Co-Demand-Prefetching und Shadow-Feedback für das Residency-Budget. Automatische Promotion/Demotion und automatische Budgetänderungen bleiben deaktiviert, bis A/B-Tests mit zurückgehaltenen realen Aufgaben einen Vorteil belegen.

Das optionale Hermes-T1-Verzeichnis ist standardmäßig deaktiviert (`warm_directory_budget=0`). Bei Aktivierung werden nur Locators injiziert, deren Pfad und tatsächliche Datei geprüft wurden; der Snapshot wird nur an Session-Grenzen neu aufgebaut. Ein Memory-Write in der laufenden Session aktualisiert den Prompt nicht heimlich. Siehe [1.4 closeout](reports/2026-09-07-v1.4-closeout.md) und [version history](docs/12-version-history.md) für Abnahmebelege und exakte Versionsgrenzen.
""",
}

OLD = "Version identity: **1.3.0 accepted/stable**."
NEW = "Version identity: **1.4.0 accepted/stable implementation milestone**."
MARKER = "## THM 1.4"


def update(path: Path, section: str) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER not in text:
        lines = text.splitlines()
        anchor = next(
            (i for i, line in enumerate(lines) if "**THM 1.3" in line),
            None,
        )
        if anchor is None:
            raise RuntimeError(f"missing THM 1.3 anchor in {path.name}")
        insert = anchor + 1
        while insert < len(lines) and lines[insert].strip():
            insert += 1
        lines[insert:insert] = ["", *section.strip().splitlines()]
        text = "\n".join(lines) + "\n"
    if OLD not in text:
        if NEW not in text:
            raise RuntimeError(f"missing version identity in {path.name}")
    else:
        text = text.replace(OLD, NEW, 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    for filename, section in SECTIONS.items():
        update(ROOT / filename, section)


if __name__ == "__main__":
    main()
