# THM — Tiered Hot Memory

**Infraestructura de memoria jerarquizada, local-first y determinista para agentes de IA.** THM separa qué merece permanecer hot/resident de qué puede recuperarse bajo demanda, y evalúa esas decisiones con coste y evidencia observables en lugar de depender por defecto de otro LLM para reescribir la memoria.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | Español

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

## Por qué existe THM

Un agente de larga duración acumula más estado del que conviene inyectar en cada prompt. Mantenerlo todo residente genera un carry cost repetido; descartarlo todo genera costes repetidos de search, retrieval y reacquisition. THM trata el problema como **residency, retrieval y asignación de presupuesto acotado**.

La pregunta central es:

> **¿Hasta dónde puede llegar la memoria de un agente sin otra llamada a un LLM?**

Por eso THM prioriza señales deterministas, índices locales, provenance explícita, evidence budgets acotados y reglas de control reproducibles. Generative extraction, summary o memory rewriting no son requisitos del core dataplane.

## Filosofía de diseño

### 1. La fuente sigue siendo autoritativa

Los archivos de memoria nativos, transcripts de sesión y fuentes externas son la autoridad. SQLite/FTS, embeddings locales, locators y otras estructuras de THM son **índices o proyecciones derivadas**. El retrieval no debe reescribir silenciosamente la fuente que pretende recordar.

### 2. Residency, relevance y activity son cosas distintas

THM separa:

- **tier** — dónde reside un item y cómo se accede a él;
- **activity** — si el agente realmente lo usó;
- **validity** — si sigue siendo válido y confiable;
- **pinning** — una restricción explícita del operador;
- **retrieval evidence** — si una ruta de búsqueda expuso el item durante una tarea.

Una mención no es un hit. Retrieval no demuestra utilidad. Prefetch no es demand. Un write no es un activity event.

### 3. La memoria fría debe seguir siendo barata

El hot prompt es escaso. THM usa locators y bounded retrieval para mantener material frío fuera del resident context hasta que una tarea realmente lo necesita. Un locator corto puede justificar su residencia aunque la fuente completa no lo haga.

### 4. Los presupuestos fijos forman parte de la correctness

No basta con que un gold item aparezca en algún lugar de un candidate pool grande. THM mide si la evidencia útil entra realmente en un presupuesto fijo de tokens. Oversized sources, duplicados y packing waste son pérdidas reales.

### 5. Sin bucles de retrieval auto-reforzados

Un item no debe volverse más importante solo porque el propio sistema lo haya prefetched o retrieved. El control plane aprende únicamente de evidencia explícita de demand y mantiene un límite anti-self-training.

### 6. La automatización viene después de la evidencia

THM puede producir recomendaciones shadow de residency, prefetch y budget, pero automatic promote/demote y automatic budget write-back permanecen desactivados hasta que held-out task evidence demuestre una mejora neta en quality, cost, latency y reacquisition.

### 7. Un memory core, múltiples superficies de Harness

La semántica de retrieval vive en el core de THM. Hermes tiene la integración lifecycle más profunda; OpenAI Agents y LangChain usan adapters SDK nativos; MCP ofrece una superficie de protocolo reutilizada por varios CLI/harnesses.

## T0–T3 Memory Tiers

| Tier | Rol | Uso típico |
| --- | --- | --- |
| **T0 — Hot** | Memoria residente que el host ya transporta | Contexto pequeño de alto valor que justifica repetidamente su residencia |
| **T1 — Warm** | Memoria orientada a locator que se expande bajo demanda | Locators de topic/file/source y bounded warm references |
| **T2 — Cold** | Historial y archivos locales consultables | Scoped FTS/dense retrieval con evidence budget explícito |
| **T3 — External** | Ubicaciones de fuente que pueden reacquirirse | Archivos, URLs o sistemas externos |

T0–T3 son **Memory Tiers de THM**. Son independientes de las L0–L6 Layers del proyecto separado Context Economics.

## Qué está implementado

THM ofrece actualmente:

- índices locales aislados por profile/scope con validaciones fail-closed de source/database;
- sparse retrieval con SQLite FTS5, embeddings locales opcionales y deterministic rank fusion;
- token-budgeted evidence packing con source traceability;
- semántica explícita de activity / validity / pin y reproducible decay diagnostics;
- un recall core read-only independiente del harness;
- Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 y una pinned compatibility bridge para determinados CLI hosts;
- telemetry de resident/hard-miss y planned-retrieval;
- T1 warm directory locator-only y snapshot Hermes session-frozen opt-in;
- shadow T0 recommendation basada en miss cost y resident carry cost con bounded exact 0/1 packing;
- bounded anti-self-training prefetch y shadow resident-budget feedback;
- una opt-in zero-generative-LLM entity projection que solo reordena candidates sparse/hybrid existentes sin cambiar el modelo canónico T0–T3.

La línea estable del paquete sigue siendo **1.4.0**. La zero-LLM entity projection está integrada en main como opt-in research successor, pero **no se declara 1.5 stable**. Las versiones históricas, PRs, reviews y cronología de desarrollo se mantienen en [CHANGELOG.md](CHANGELOG.md) y [version history](docs/12-version-history.md), no en la homepage.

## Evidencia de retrieval medida

THM mantiene separada la retrieval evidence de las afirmaciones sobre generación de respuestas.

El LoCoMo Protocol 2 canónico usa 1.532 preguntas non-adversarial totalmente resueltas y una ventana fija de 600 tokens `cl100k_base` de evidencia.

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

La opt-in deterministic entity projection actual eleva sparse any-gold en el conjunto completo de **69.39% a 72.52%** y el holdout congelado de 1.301 preguntas de **69.56% a 72.33%**, sin cambiar candidate coverage. El beneficio proviene de **colocar mejor candidates ya disponibles dentro del slice de 600 tokens**, no de ampliar el pool con otro modelo.

Estas cifras miden **packed retrieval evidence**, no precisión final de respuesta, satisfacción de usuario ni superioridad universal. Véanse [Protocol 2](reports/2026-09-06-recall-protocol2.md) y [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md).

## Integración con Harness

| Surface | Profundidad de integración |
| --- | --- |
| **Hermes Agent** | `MemoryProvider` nativo; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | `FunctionTool` nativo read-only |
| **LangChain / LangGraph / Deep Agents** | Superficie nativa `BaseRetriever` |
| **MCP v2** | `thm_recall` y `thm_status` typed/read-only por stdio |
| **OpenClaw** | Pinned compatibility probe mediante legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle sobre el mismo read-only recall core |

El soporte multi-harness no convierte THM en una memory database universal. La profundidad del lifecycle depende del host; Hermes sigue siendo la integración nativa más profunda.

## Quick start

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Dependencias opcionales:

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

## Invariantes importantes

- read-only retrieval no modifica native memory;
- retrieval/display/scan no fabrican usage activity;
- `planned_retrieval` no es un miss;
- prefetch no genera demand, hit, renewal ni promotion evidence;
- solo misses explícitamente `avoidable=true` pueden aportar residency benefit;
- T1 `pinned` no implica automatic promotion;
- las locator projections permanecen locator-only y deben resolver dentro del scope previsto;
- ordinary mid-session memory write no rebuild silenciosamente un frozen Hermes prompt snapshot;
- automatic tier movement y budget write-back siguen desactivados sin held-out task evidence.

## Evidence boundary

THM admite experimentos sólidos de deterministic/local retrieval y shadow control, pero no afirma una mejora universal de answer quality, una decay curve óptima para todos, automatic T0–T3 movement production-ready, propagación automática de borrado segura, mejoras de prompt-cache/user-latency deducidas de métricas de retrieval, ni uso garantizado por el modelo de un evidence item recuperado.

Unit/invariant evidence, retrieval benchmark, harness lifecycle y real task outcome son evidence classes diferentes.

## Documentación

- [Documentation index](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [Version history and recovery](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM sigue siendo research software. 1.4.0 es el accepted/stable implementation milestone; el retrieval frontier posterior permanece explícitamente unreleased. Un número de versión nunca sustituye una evidence class.