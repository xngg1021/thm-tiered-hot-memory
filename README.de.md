# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

THM ist ein local-first Speicherwerkzeug mit vier Ebenen für Hermes Agent. T0 ist `MEMORY.md` / `USER.md` im Session-Snapshot, T1 thematisches Markdown auf Abruf, T2 budgetierte Verlaufssuche und T3 externe Referenzen.

THM trennt Aktivität, Gültigkeit, Aufgabenrelevanz und explizites Pinning. Eine Erwähnung ist kein hit, Retrieval beweist keine Nützlichkeit und ein Write ist kein Nutzungsereignis. Version 1.2 implementiert FTS5 sparse retrieval, optionale lokale Semantic-Vektoren, RRF, budgetiertes Packing, `mention_observed` mit Gewicht null, mehrere Decay-Vergleiche und einen read-only Hermes Provider.

Der abgeschlossene LoCoMo **Protocol 2** erreicht bei 600 `cl100k_base` Evidence-Tokens und 1.532 vollständig auflösbaren nicht-adversarialen Fragen eine any-gold coverage von **literal 56,79 % / sparse 69,39 % / dense 51,11 % / hybrid 71,34 %** sowie all-gold von **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Das ist keine endgültige Antwortgenauigkeit. Protocol 2 korrigiert Kategorien, isoliert IDF pro Gespräch und ergänzt MRR / nDCG / p99. Vollständige Ergebnisse: [Protocol 2 report](reports/2026-09-06-recall-protocol2.md).

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Nach der Installation stellt THM `thm` über Hermes' Entry-Point `hermes_agent.memory_providers` bereit. Ein E2E-Workflow gegen einen gepinnten Upstream verifizierte echte Hermes-Discovery, MemoryProvider/MemoryManager-Admission, Prefetch, Memory-Context-Fencing, Session-Switch sowie, dass `on_memory_write` nicht als Hit zählt und die abgeleitete Recall-Datenbank nicht verändert. Dieser E2E nutzt synthetische Evidenz und null Modellaufrufe; er prüft den Provider-Lifecycle, nicht die Antwortgenerierung. Siehe [Hermes E2E report](reports/2026-09-06-hermes-e2e.md).

Für nutzerspezifische Decay-Kalibrierung kann `research/recall/decay_from_index.py` aus einem lokalen THM-v2-Index eine private Trace mit nur Entry-IDs, Unit-Kosten und expliziten Hit-Daten exportieren. Ohne reale Hit-Historie behauptet THM keinen nutzerspezifisch optimalen Half-Life oder Curve.

THM behauptet derzeit nicht, End-to-End-Antwortgenauigkeit für reale Nutzer, einen universell optimalen Decay, automatisches Tier-Movement/Löschweitergabe oder wahrgenommene Latenzgewinne bewiesen zu haben. `mention_observed` aus `scan` behält Gewicht null.

Dokumentation: [Index](docs/README.md) · [Engine Guide](docs/06-engine-guide.md) · [Retrieval / Scan / Decay](docs/09-retrieval-and-measurement.md) · [Benchmark](research/recall/README.md)
