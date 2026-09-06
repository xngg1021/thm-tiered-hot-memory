# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

THM ist ein local-first Speicherwerkzeug mit vier Ebenen für Hermes Agent. T0 ist `MEMORY.md` / `USER.md` im Session-Snapshot, T1 thematisches Markdown auf Abruf, T2 budgetierte Verlaufssuche und T3 externe Referenzen.

THM trennt Aktivität, Gültigkeit, Aufgabenrelevanz und explizites Pinning. Eine Erwähnung ist kein hit, Retrieval beweist keine Nützlichkeit und ein Write ist kein Nutzungsereignis. Version 1.2 implementiert FTS5 sparse retrieval, optionale lokale Semantic-Vektoren, RRF, budgetiertes Packing, `mention_observed` mit Gewicht null, Decay-Vergleiche und einen read-only Hermes Provider.

Im historischen LoCoMo Protocol 1 lag bei 600 `cl100k_base` Evidence-Tokens und 1.532 vollständig auflösbaren nicht-adversarialen Fragen die any-gold coverage bei **literal 56,85 % / sparse 69,58 % / dense 51,11 % / hybrid 70,04 %**. Das ist keine endgültige Antwortgenauigkeit. Protocol 2 korrigiert Kategorien, isoliert IDF pro Gespräch und ergänzt MRR / nDCG / p99.

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Nach der Installation stellt THM `thm` über Hermes' Entry-Point `hermes_agent.memory_providers` bereit. Ein E2E-Workflow gegen einen gepinnten Upstream prüft echte Discovery und Provider-Lifecycle.

THM behauptet derzeit nicht, End-to-End-Antwortgenauigkeit für reale Nutzer, einen universell optimalen Decay, automatisches Tier-Movement/Löschweitergabe oder wahrgenommene Latenzgewinne bewiesen zu haben. Nutzerspezifische Decay-Kalibrierung benötigt eine reale chronologische Hit-Historie.

Dokumentation: [Index](docs/README.md) · [Engine Guide](docs/06-engine-guide.md) · [Retrieval / Scan / Decay](docs/09-retrieval-and-measurement.md) · [Benchmark](research/recall/README.md)
