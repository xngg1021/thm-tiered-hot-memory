# THM — Tiered Hot Memory

**Local-first, deterministische, gestufte Memory-Infrastruktur für AI Agents.** THM trennt die Frage, was dauerhaft hot resident bleiben sollte, von dem, was bei Bedarf wiederbeschafft werden kann, und bewertet diese Entscheidungen anhand beobachtbarer Kosten und Evidenz statt standardmäßig ein weiteres LLM zum Umschreiben von Memory einzusetzen.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | Deutsch | [Français](README.fr.md) | [Español](README.es.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

## Warum THM existiert

Lang laufende Agents sammeln mehr Zustand an, als sinnvoll in jedem Prompt resident sein kann. Alles permanent mitzuschleppen erzeugt wiederkehrende Carry-Kosten; alles zu verwerfen erzeugt wiederkehrende Search-, Retrieval- und Reacquisition-Kosten. THM behandelt das als **Residency-, Retrieval- und Budget-Allokationsproblem**.

Die zentrale Frage lautet:

> **Wie weit kann Agent Memory kommen, ohne einen weiteren LLM-Aufruf zu benötigen?**

Darum bevorzugt THM deterministische Signale, lokale Indizes, explizite Provenance, begrenzte Evidence-Budgets und reproduzierbare Control Rules. Generative Extraction, Summaries oder Memory-Rewriting sind keine Voraussetzung für den Core Dataplane.

## Design philosophy

### 1. Die Quelle bleibt autoritativ

Native Memory-Dateien, Session-Transkripte und externe Quellen sind die Authority. SQLite/FTS, lokale Embeddings, Locators und andere THM-Strukturen sind **abgeleitete Indizes oder Projektionen**. Retrieval darf die Quelle, die es erinnern soll, nicht stillschweigend umschreiben.

### 2. Residency ist nicht gleich Relevance oder Activity

THM trennt:

- **tier** — wo ein Item resident ist und wie es erreicht wird;
- **activity** — ob der Agent es tatsächlich benutzt hat;
- **validity** — ob es noch aktuell und vertrauenswürdig ist;
- **pinning** — eine explizite Operator-Vorgabe;
- **retrieval evidence** — ob ein Retrieval-Pfad das Item in einer Aufgabe sichtbar gemacht hat.

Mention ist kein hit. Retrieval beweist keine Nützlichkeit. Prefetch ist keine Demand. Ein Write ist kein Activity Event.

### 3. Cold Memory soll billig bleiben

Der Hot Prompt ist knapp. THM nutzt Locators und bounded retrieval, damit kältere Inhalte außerhalb des resident context bleiben können, bis eine Aufgabe sie wirklich benötigt. Ein kurzer Locator kann es wert sein, resident zu bleiben, obwohl der Full Source es nicht ist.

### 4. Fixed Budgets gehören zur Correctness

Es reicht nicht, wenn ein Gold-Item irgendwo in einem großen Candidate Pool vorkommt. THM misst, ob relevante Evidenz tatsächlich in ein festes Token-Budget gepackt wird. Oversized Sources, Duplikate und Packing Waste sind reale Verluste.

### 5. Keine selbstverstärkenden Retrieval-Loops

Ein Item darf nicht allein deshalb wichtiger werden, weil das System es selbst prefetched oder retrieved hat. Control-Plane-Signale lernen nur aus expliziter Demand-Evidenz und bewahren die Anti-Self-Training-Grenze.

### 6. Automation folgt Evidenz

THM kann Shadow-Empfehlungen für Residency, Prefetch und Budget erzeugen. Automatic promote/demote und automatic budget write-back bleiben jedoch deaktiviert, bis held-out task evidence einen Netto-Gewinn bei Qualität, Kosten, Latenz und Reacquisition zeigt.

### 7. Ein Memory Core, mehrere Harness Surfaces

Retrieval-Semantik liegt im THM Core. Hermes hat die tiefste Lifecycle-Integration; OpenAI Agents und LangChain nutzen native SDK-Adapter; MCP stellt eine standardisierte Protokollfläche für mehrere CLI-/Harness-Integrationen bereit.

## T0–T3 Memory Tiers

| Tier | Rolle | Typischer Einsatz |
| --- | --- | --- |
| **T0 — Hot** | Vom Host bereits getragene resident memory | Kleine High-Value-Kontexte, die ihre Residency wiederholt rechtfertigen |
| **T1 — Warm** | Locator-orientierte Inhalte, die bei Bedarf expandiert werden | Topic/File/Source Locators und bounded warm references |
| **T2 — Cold** | Durchsuchbare lokale History und Archive | Scoped FTS/Dense Retrieval unter festem Evidence-Budget |
| **T3 — External** | Wiederbeschaffbare Source Locations | Dateien, URLs und externe Systeme |

T0–T3 sind **THM Memory Tiers**. Sie sind nicht die L0–L6 Layers des separaten Context-Economics-Projekts.

## Was implementiert ist

THM bietet derzeit:

- profile-/scope-isolierte lokale Indizes mit fail-closed Source-/Database-Checks;
- SQLite FTS5 Sparse Retrieval, optionale lokale Sentence Embeddings und deterministische Rank Fusion;
- token-budgeted evidence packing mit Source Traceability;
- explizite Activity-/Validity-/Pin-Semantik und reproduzierbare Decay Diagnostics;
- einen harness-neutralen read-only recall core;
- Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 sowie eine pinned compatibility bridge für ausgewählte CLI Hosts;
- resident/hard-miss und planned-retrieval telemetry;
- ein locator-only T1 warm directory plus opt-in session-frozen Hermes locator snapshot;
- Shadow-T0-Recommendations aus Miss Cost und Resident Carry Cost mit bounded exact 0/1 packing;
- bounded anti-self-training prefetch und shadow resident-budget feedback;
- eine opt-in zero-generative-LLM entity projection, die nur bestehende sparse/hybrid candidates re-rankt und das kanonische T0–T3-Modell nicht verändert.

Die stabile Package-Linie bleibt **1.4.0**. Die zero-LLM entity projection ist als opt-in research successor in main gemerged, aber **nicht als 1.5 stable bezeichnet**. Historische Versionen, PRs, Reviews und Implementierungs-Chronologie gehören in [CHANGELOG.md](CHANGELOG.md) und die [Version History](docs/12-version-history.md), nicht auf die Homepage.

## Gemessene Retrieval-Evidenz

THM trennt Retrieval-Evidenz von Answer-Generation-Claims.

Der kanonische LoCoMo Protocol 2 verwendet 1.532 vollständig aufgelöste non-adversarial questions und einen festen Slice von 600 `cl100k_base` Evidence Tokens.

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

Die aktuelle opt-in deterministic entity projection erhöht full-set sparse any-gold von **69.39% auf 72.52%** und den eingefrorenen 1.301-Fragen-Holdout von **69.56% auf 72.33%**, ohne die Candidate Coverage zu verändern. Der Gewinn entsteht also dadurch, **bereits vorhandene Kandidaten besser in den 600-Token-Slice zu bringen**, nicht durch einen weiteren Modellaufruf zur Erweiterung des Candidate Pools.

Diese Werte messen packed retrieval evidence, nicht finale Antwortgenauigkeit, User Satisfaction oder universelle Überlegenheit. Siehe [Protocol 2](reports/2026-09-06-recall-protocol2.md) und [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md).

## Harness Integration

| Surface | Integrationstiefe |
| --- | --- |
| **Hermes Agent** | Native `MemoryProvider`; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | Native read-only `FunctionTool` |
| **LangChain / LangGraph / Deep Agents** | Native `BaseRetriever` surface |
| **MCP v2** | Typed read-only `thm_recall` und `thm_status` über stdio |
| **OpenClaw** | Pinned compatibility probe über die legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle über denselben read-only recall core |

Multi-Harness-Support macht THM nicht zu einer universellen Memory Database. Die Lifecycle-Tiefe unterscheidet sich je Host; Hermes bleibt die tiefste native Integration.

## Quick start

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Optionale Dependencies:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP:

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Wichtige Invarianten

- read-only retrieval mutiert native memory nicht;
- retrieval/display/scan erzeugen keine erfundene usage activity;
- `planned_retrieval` ist kein miss;
- prefetch erzeugt keine demand-, hit-, renewal- oder promotion-evidence;
- nur explizite `avoidable=true` misses dürfen Residency Benefit erzeugen;
- T1 `pinned` bedeutet keine automatic promotion;
- locator projections bleiben locator-only und müssen innerhalb des vorgesehenen Scope auflösen;
- ordinary mid-session memory writes rebuilden keinen eingefrorenen Hermes prompt snapshot;
- automatic tier movement und budget write-back bleiben ohne held-out task evidence deaktiviert.

## Evidence boundary

THM unterstützt starke deterministic/local retrieval- und shadow-control Experimente, behauptet aber keine universelle Answer-Quality-Steigerung, keine universell optimale Decay Curve, keine production-ready automatische T0–T3-Bewegung, keine sichere automatische Delete Propagation, keine automatisch aus Retrieval-Metriken abgeleiteten Prompt-Cache-/User-Latency-Gewinne und keine garantierte Model-Nutzung eines retrievten Evidence Items.

Unit/invariant evidence, retrieval benchmark, harness lifecycle und real task outcome sind getrennte Evidence Classes.

## Dokumentation

- [Documentation index](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [Version history and recovery](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM bleibt Research Software. 1.4.0 ist der accepted/stable implementation milestone; der folgende retrieval frontier bleibt ausdrücklich unreleased. Eine Versionsnummer ersetzt niemals eine Evidence Class.
