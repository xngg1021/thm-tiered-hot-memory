# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE) · Stabile Version: **1.3.0**

THM ist ein lokales Vier-Ebenen-Gedächtnis für Agent-Harnesses. Version 1.3 ergänzt eine harness-neutrale, schreibgeschützte Recall-Schicht: Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 über stdio und eine getrennte Legacy-MCP-Brücke für OpenClaw 2026.9.x. Claude Code, Codex CLI und Gemini CLI werden mit festgelegten Versionen der echten CLIs und einem Lifecycle-E2E desselben Serverbefehls geprüft. THM schreibt Quellspeicher nicht um und führt keine zusätzlichen Modellaufrufe aus.

LoCoMo Protocol 2 umfasst 10 Gespräche und 1.986 Fragen; der Hauptnenner enthält 1.532 Fragen. Bei 600 evidence tokens beträgt die any-gold coverage für literal / sparse / dense / hybrid **56,79 % / 69,39 % / 51,11 % / 71,34 %**. Das misst Evidenzabruf, nicht Antwortgenauigkeit. [Vollständiger Bericht](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

1.3.0 accepted/stable wird ausschließlich durch eine formelle Referenz bestätigt, die auf den exakten Git-SHA zeigt, der die vollständigen Matrizen correctness, Hermes und harness bestanden hat. THM beansprucht derzeit keine reale E2E-Antwortgenauigkeit, universell optimale decay curve, automatische Ebenenverschiebung oder Löschweitergabe und keine Verbesserung der wahrgenommenen Latenz.

Dokumentation: [Index](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [Versionshistorie](docs/12-version-history.md) · [Änderungen](CHANGELOG.md)
