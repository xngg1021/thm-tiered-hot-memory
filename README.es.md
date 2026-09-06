# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE) · Versión estable: **1.3.0**

THM es una memoria local de cuatro niveles para agent harnesses. La versión 1.3 incorpora una capa de recall de solo lectura e independiente del harness: Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 por stdio y un puente legacy MCP separado para OpenClaw 2026.9.x. Claude Code, Codex CLI y Gemini CLI se verifican con versiones fijadas de sus CLI reales y un E2E del ciclo de vida del mismo comando de servidor. THM no reescribe la memoria fuente ni hace llamadas de modelo adicionales.

LoCoMo Protocol 2 cubre 10 conversaciones y 1.986 preguntas; el denominador principal contiene 1.532 preguntas. Con 600 evidence tokens, la cobertura any-gold de literal / sparse / dense / hybrid es **56,79 % / 69,39 % / 51,11 % / 71,34 %**. Es una métrica de recuperación de evidencia, no de exactitud de respuestas. [Informe completo](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

El estado 1.3.0 accepted/stable solo se confirma mediante una referencia formal que apunte al SHA Git exacto que superó las matrices completas de correctness, Hermes y harness. THM no afirma aún exactitud E2E con usuarios reales, una curva de decay universalmente óptima, movimiento o borrado automático entre niveles ni mejoras de latencia percibida.

Documentación: [índice](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [historial](docs/12-version-history.md) · [cambios](CHANGELOG.md)
