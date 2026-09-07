# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | Deutsch

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

## Vier Ebenen

THM ist ein lokales Vier-Ebenen-Gedächtnis für Agent-Harnesses: T0 nativer permanenter Kontext, T1 thematisches Material auf Abruf, T2 budgetierte Suche in Historie und Archiven, T3 erneut abrufbare externe Quellen. Aktivität, Gültigkeit, Aufgabenrelevanz und Pinning bleiben getrennt; Erwähnung, Retrieval und Write beweisen keinen nützlichen Hit.

## Implementierter Umfang

1.1.1 liefert eine robuste Index-CLI; 1.2 ergänzt scope-getrenntes FTS5, optionale lokale Embeddings, RRF, budgetiertes Packing, gewichtungsfreie Mention-Observations, Decay-Vergleiche und reproduzierbare Evaluation. **1.3 ergänzt eine harness-neutrale Read-only-Recall-Schicht**: Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` und MCP-v2-stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI und Gemini CLI verwenden eine getrennte, schreibgeschützte MCP-Kompatibilitätsbrücke und werden mit fixierten echten CLI-Versionen geprüft. Native Quellen werden nicht umgeschrieben; zusätzliche Modellaufrufe gibt es nicht.

## LoCoMo-Messwerte

Protocol 2 umfasst 10 Gespräche, 1.986 Fragen und 1.532 vollständig aufgelöste nicht-adversariale Fragen im Hauptnenner. Bei 600 Tokens beträgt any-gold **56,79 % literal / 69,39 % sparse / 51,11 % dense / 71,34 % hybrid**, all-gold **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Dies misst Evidenz-Retrieval, nicht Antwortgenauigkeit. p95 Retrieval+Packing: **34,55 ms sparse / 57,88 ms hybrid**. Sparse erreicht bei 300/600/1200 Tokens **60,57/69,39/76,17 %** bei **20,39/34,55/61,78 ms**. [Bericht](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## Integrationen

| Oberfläche | THM 1.3 |
| --- | --- |
| Hermes | pip-Provider, Setup/Config, Prefetch, optionales `sync_turn`, Session Hooks, write≠hit |
| OpenAI Agents | schreibgeschütztes `OpenAIAgentsTHM.tool` |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, typisierte `thm_recall`/`thm_status` |
| OpenClaw | `thm-mcp-legacy`, echter Probe |
| Claude/Codex/Gemini | echte fixierte CLIs, exakter Befehl, Discovery/Call-Lifecycle, null Modellaufrufe |

## Installation

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras: `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`. Die Kompatibilitätsbrücke heißt `thm-mcp-legacy`.

## Hermes-Lifecycle

`sync_turns` ist standardmäßig aus. Explizit aktiviert übernimmt es nur User/Assistant-Text in einen abgeleiteten T2-Session-Scope; Systemzeilen und Kompressionszusammenfassungen bleiben draußen. `on_memory_write` ist nur Refresh. THM bleibt bei pre-compress API v1, da der Cache nicht Eigentümer des kanonischen Transkripts ist und keine fail-closed Checkpoint-v2-Dauerhaftigkeit versprechen kann.

## Decay-Kalibrierung

`decay_from_index.py` exportiert nur IDs, Kosten und Hit-Daten, ohne Texte, Zusammenfassungen, Keys oder Bestätigungen; `decay_replay.py` spielt privat nach. Ohne reale Chronologie wird keine persönliche optimale Halbwertszeit behauptet.

## Evidenzgrenzen

THM behauptet derzeit keine reale E2E-Antwortgenauigkeit, universell optimale Decay-Kurve, automatische Ebenenbewegung/Löschweitergabe oder Verbesserung von Prompt-Cache und wahrgenommener Latenz. Coverage, Plumbing, Modellnutzung und Endqualität sind getrennte Evidenzschichten. Correctness CI läuft unter Linux, macOS und Windows; LoCoMo und Integrationstests sind separat.

[Index](docs/README.md) · [Guide](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [Versionen](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## Aktueller stabiler Stand von THM 1.4

THM 1.4 ist als **accepted/stable implementation milestone** abgeschlossen und eingefroren. Der stabile Code-/Content-Meilenstein ist `e6e4dda5835e3cb345207457d5491131c6959b2c`, der Recovery-Pointer `archive/v1.4.0-stable`. Das Vier-Stufen-Modell T0–T3 bleibt unverändert.

Auf der harness-neutralen Recall-Schicht von 1.3 ergänzt 1.4 explizite resident/hard-miss- und planned-retrieval-Telemetrie, ein strikt locator-only T1-Warmverzeichnis, eine Shadow-T0-Empfehlung aus avoidable-miss penalty gegenüber resident carry cost, exaktes begrenztes 0/1-Packing, begrenztes Prefetching, das nur aus echter Demand-Co-Occurrence lernt, sowie resident-budget feedback ohne automatische Budgetänderung. Hermes erhält zusätzlich einen standardmäßig deaktivierten session-frozen T1 locator snapshot.

Diese Oberflächen haben die 1.4-Akzeptanz für correctness, Hermes und multi-harness bestanden. Da 1.4 den retrieval path nicht geändert hat, werden keine neuen LoCoMo/Protocol-2-Zahlen beansprucht. Automatische T0–T3-Bewegung und automatische Budgetänderung bleiben deaktiviert, bis held-out Runtime-/Task-A/B gemeinsam Verbesserungen bei Qualität, Kosten, Latenz und Reacquisition nachweist. Siehe [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) und [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.

## Retrieval-Erweiterung ohne generative LLM-Aufrufe (unveröffentlicht)

Die explizite Python-Option `entity_projection=True` ordnet vorhandene Kandidaten anhand exakter Sprechernamen und Quellbezeichner neu. Bei 600 tokens steigt Protocol 2 global von 69.39% auf 72.52% any-gold; die 1301 zurückgehaltenen Fragen steigen von 69.56% auf 72.33%. Die Kandidatenabdeckung bleibt gleich. Es gibt keine generativen Aufrufe und kein Embedding-Modell; T0–T3 und native Erinnerungen bleiben unverändert. Zeit-, Segment-, Assoziations- und Größenranking-Experimente gelangen nicht in den Produktionspfad. Version 1.5 ist noch nicht als stabil registriert.

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
