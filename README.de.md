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

Version identity: **1.3.0 accepted/stable**.
