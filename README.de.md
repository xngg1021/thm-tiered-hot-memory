# THM — Tiered Hot Memory

**Local-first, deterministische, gestufte Memory-Infrastruktur für AI Agents.** THM trennt die Frage, was dauerhaft hot resident bleiben sollte, von dem, was bei Bedarf wiederbeschafft werden kann, und bewertet diese Entscheidungen anhand beobachtbarer Kosten und Evidenz statt standardmäßig ein weiteres LLM zum Umschreiben von Memory einzusetzen.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | Deutsch | [Français](README.fr.md) | [Español](README.es.md)

Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

<!-- section:architecture -->
## Architektur mit drei Ebenen

THM trennt logischen Speicher, Rechenausführung und physischen Speicher. Evaluation Fabric misst diese Ebenen ohne einen neuen Gedächtnisalgorithmus. Quellidentität und Scope bleiben für jede Darstellung maßgeblich.

Architektur- und Evidenzverträge

Stabiles Package und Archiv bleiben bei 1.4.0. Runtime, Physical Storage Fabric und Evaluation Fabric bleiben Unreleased. Vorhandene Messungen behalten Protokoll, Quell-SHA und Geltungsbereich; nicht ausgeführte Benchmarks und Hardware gelten nicht als accepted evidence.

<!-- section:philosophy -->
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

<!-- section:logical -->
## Logische Speicherebene

Scope-begrenzter SearchIndex, Evidenzpackung unter Budget und Shadow-Residenzsteuerung nutzen denselben Kern. T0–T3 bezeichnen logische Residenz und Zugriff. Aktivität, Gültigkeit, Fixierung und Retrieval bleiben getrennt; automatische Hochstufung und Budgetrückschreiben bleiben deaktiviert.

<!-- section:tiers -->
## T0–T3 Memory Tiers

| Tier | Rolle | Typischer Einsatz |
| --- | --- | --- |
| **T0 — Hot** | Vom Host bereits getragene resident memory | Kleine High-Value-Kontexte, die ihre Residency wiederholt rechtfertigen |
| **T1 — Warm** | Locator-orientierte Inhalte, die bei Bedarf expandiert werden | Topic/File/Source Locators und bounded warm references |
| **T2 — Cold** | Durchsuchbare lokale History und Archive | Scoped FTS/Dense Retrieval unter festem Evidence-Budget |
| **T3 — External** | Wiederbeschaffbare Source Locations | Dateien, URLs und externe Systeme |

T0–T3 sind **THM Memory Tiers**. Sie sind nicht die L0–L6 Layers des separaten Context-Economics-Projekts.

<!-- section:compute -->
## Rechenausführung

RuntimeProfile bindet Encoder/Backend, Präzision, Gerät, Scorer, Batchgrößen und Threads. Optionaler Scheduler und begrenztes AutoTune wählen explizite Betriebspunkte. CPU/CUDA-Beschreibungen benötigen eigene Laufzeitevidenz; erfolgreiche Fixtures belegen weder Dispatch noch Beschleunigung.

[Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## Physische Speicherebene

StorageProfile beschreibt gemessene Zugriffskosten; Placement bindet eine Darstellung an ein Ziel. PhysicalTelemetry erfasst tatsächliche Extent-I/O. Verifizierte lokale buffered/mmap-Dateisystempfade sind implementiert. CXL, DAX, SPDK, GDS und Ferntransporte bleiben Erweiterungsbeschreibungen ohne validierte Hardwareleistung.

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Adapter normalisieren native Eingaben zu Task, evaluator-exklusiver GroundTruth, Result und SHA-gebundenem Receipt. LoCoMo Protocol 2 und LongMemEval-S teilen Dataplane-Metriken, behalten aber Dokument- und Sitzungsevidenz getrennt. LongMemEval-V2 unterstützt öffentliche trajectory states und insert/query; BEAM native batches/turns und probing questions; MemoryArena native Teilaufgaben und sitzungsübergreifendes add/wrap_user_prompt.

Fixtures prüfen nur Schnittstellen und deterministisches Retrieval. V2 arbeitet textbasiert und lehnt Bildanfragen ab. Ohne Gold-Locators ist Recall null. MemoryArena-Parsing führt keine Umgebung aus. Antworten und Rubrics gelangen nie in Retrieval-Dokumente.

| Evidenzebene | Receipt-Vertrag |
| --- | --- |
| memory-dataplane | any/all-gold, Makro-/Mikro-Recall, Parent-Abdeckung, Budget, Latenz |
| systems-runtime | Rechenprofil, StorageProfile, Placement, I/O-Telemetrie |
| LLM-agent-outcome | Generierungs-/Judge-Aufrufe, Antwortgenauigkeit, Umgebungserfolg; standardmäßig not-run |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

<!-- section:evidence -->
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

<!-- section:harness -->
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

<!-- section:quickstart -->
## Quick start

```bash
python -m pip install -e .
python -m thm --help

python -m thm import-files ./notes \
  --db ./state/recall.sqlite3 \
  --scope demo

python -m thm search \
  --db ./state/recall.sqlite3 \
  --scope demo \
  "Which database port?" \
  --budget 600
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

<!-- section:acceptance -->
## Begrenzte lokale Abnahme

Im Repository-Stamm mit Python 3.10 oder neuer ausführen. Keine Modell- oder Datensatzdownloads und keine Provider-Schlüssel sind nötig. Die Prozessbaumfrist beträgt 3300 Sekunden und lässt Bereinigungszeit unter 60 Minuten. Zeitüberschreitung oder Fehler erzeugen einen unvollständigen Receipt und einen Fehlercode.

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

Vollständige Kampagnen werden separat mit --mode full-research --full-research --benchmark NAME --dataset FILE aktiviert. Sie benötigen extern vorbereitete native Eingaben und separat konfigurierte Agenten, Umgebungen und Judges. Dieser Befehl misst nur Retrieval und startet weder Live-Agenten noch eine automatische Benchmark-Abnahme.

<!-- section:invariants -->
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

<!-- section:boundary -->
## Evidence boundary

THM unterstützt starke deterministic/local retrieval- und shadow-control Experimente, behauptet aber keine universelle Answer-Quality-Steigerung, keine universell optimale Decay Curve, keine production-ready automatische T0–T3-Bewegung, keine sichere automatische Delete Propagation, keine automatisch aus Retrieval-Metriken abgeleiteten Prompt-Cache-/User-Latency-Gewinne und keine garantierte Model-Nutzung eines retrievten Evidence Items.

Unit/invariant evidence, retrieval benchmark, harness lifecycle und real task outcome sind getrennte Evidence Classes.

<!-- section:documentation -->
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
