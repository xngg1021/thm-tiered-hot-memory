# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

THM ist ein local-first Speicherwerkzeug mit vier Ebenen für Hermes Agent. Es konzentriert sich auf ein enges Problem: Welche Informationen dauerhaft Kontext belegen sollen, was nur bei Bedarf geladen wird, wie Historie unter einem festen Budget abgerufen wird und wie diese Entscheidungen gemessen werden können, ohne „Nutzung“ zu erfinden.

## Vier Ebenen

- **T0 — hot:** native `MEMORY.md` / `USER.md`, die beim Sitzungsstart in den Snapshot injiziert werden.
- **T1 — warm:** thematische Markdown-Dateien, die bei Bedarf geladen werden.
- **T2 — cold:** historische Sitzungen und Archive, die unter einem expliziten Evidenzbudget durchsucht werden.
- **T3 — external:** externe Quellenorte und Referenzen, die bei Bedarf erneut aufgerufen werden.

THM trennt Aktivität, Gültigkeit, Aufgabenrelevanz und explizites Pinning. Eine Erwähnung ist kein hit; ein Retrieval beweist keine Nützlichkeit; ein Write ist kein Nutzungsereignis.

## Implementiert

Die 1.1.1-Index-CLI bietet profilgebundene Indizes, strikte Ereignisidentitäten, Migrationsvorschauen, pin/unpin und fehlersichere Schreibvorgänge. Das 1.2-Paket ergänzt scoped FTS5-Retrieval, optionale lokale Sentence Embeddings, RRF-Fusion, budgetiertes Context Packing, `mention_observed` mit Gewicht null, Vergleiche mehrerer Decay-Strategien, einen read-only Hermes-Provider-Adapter und reproduzierbare Evaluationsskripte.

Retrieval und Scan schreiben weder native Memory-Dateien noch Hermes `state.db` um. Abgeleitete SQLite-Datenbanken lehnen fremde/native Datenbanken ab, bevor THM-Tabellen angelegt werden.

## Gemessene Evidenz

Der historische LoCoMo-Lauf mit Protocol 1 nutzte 10 Gespräche und 1.986 Fragen. Bei 600 `cl100k_base` Evidenz-Tokens und 1.532 vollständig auflösbaren nicht-adversarialen Fragen lag die any-gold coverage bei **56,85 % literal**, **69,58 % sparse**, **51,11 % MiniLM dense** und **70,04 % hybrid**. Das sind Evidenz-Retrieval-Metriken, keine Antwortgenauigkeit und kein Wettbewerber-Ranking.

Protocol 2 korrigiert Kategorien, isoliert FTS5-IDF-Statistiken pro Gespräch und ergänzt MRR, nDCG und p99. Der vollständige Lauf wird durch den Benchmark-Workflow des Repositories ausgeführt.

## Installation und Nutzung

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Optionale tokenizer-/semantic-Abhängigkeiten: `python -m pip install -e '.[tokenizer,semantic]'`.

Nach der Installation stellt THM den Provider `thm` über Hermes' Entry-Point `hermes_agent.memory_providers` bereit. Ein Integrationsworkflow gegen einen gepinnten Hermes-Upstream-Checkout prüft Discovery und Provider-Lifecycle mit dem realen Upstream-Code.

## Evidenzgrenzen

THM behauptet derzeit **nicht**, End-to-End-Antwortgenauigkeit für reale Nutzer, eine universell optimale Decay-Kurve, automatisches Tier-Movement, automatische Löschweitergabe oder Verbesserungen bei Prompt-Cache bzw. wahrgenommener Latenz bewiesen zu haben. `scan` erzeugt nur schwache `mention_observed` mit Aktivitätsgewicht null. Eine nutzerspezifische Decay-Kalibrierung benötigt eine reale chronologische Nutzungshistorie.

Dokumentation: [Index](docs/README.md) · [Engine Guide](docs/06-engine-guide.md) · [Retrieval / Scan / Decay](docs/09-retrieval-and-measurement.md) · [Integrationsreview](docs/10-recall-integration-review.md) · [Benchmark-Protokoll](research/recall/README.md)