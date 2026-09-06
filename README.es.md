# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | Español | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

THM es un sistema de memoria local de cuatro niveles para agent harnesses. Nació para Hermes Agent y ahora separa la recuperación de la conexión con cada harness: decide qué merece contexto permanente, carga evidencia fría bajo un presupuesto fijo y mide el resultado sin fabricar señales de «uso».

## Cuatro niveles

- **T0, caliente:** memoria permanente nativa inyectada por el host.
- **T1, templado:** material temático cargado cuando se necesita.
- **T2, frío:** sesiones históricas y archivos buscados con un presupuesto explícito.
- **T3, externo:** ubicaciones y referencias que pueden revisitarse.

THM separa actividad, validez, relevancia para la tarea y fijación explícita. Una mención no es un hit; recuperar no demuestra utilidad; escribir no equivale a usar.

## Qué está implementado

El CLI 1.1.1 mantiene metadatos ligados al perfil, identidades exactas de eventos, vista previa de migración, pin/unpin y escrituras resistentes a fallos. La versión 1.2 añade FTS5 por scope, embeddings locales opcionales, RRF, empaquetado con presupuesto, observaciones de mención con peso cero, comparación de políticas de decay y evaluación reproducible.

**THM 1.3 añade una capa de recall de solo lectura e independiente del harness:** Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` y servidor MCP v2 stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI y Gemini CLI se validan mediante un puente MCP de compatibilidad separado y de solo lectura, sin debilitar el contrato MCP v2 principal. Véase [adaptadores](docs/11-harness-adapters.md).

Recall y scan no reescriben la memoria fuente. Los adaptadores abren las bases derivadas en modo de solo lectura, salvo la actualización explícita de una caché de sesión del host. Antes de crear tablas, THM rechaza bases SQLite nativas o ajenas.

## Evidencia medida de recuperación

Protocol 2 procesó las 10 conversaciones y 1.986 preguntas de LoCoMo. El denominador principal contiene 1.532 preguntas no adversariales con evidencia completamente resuelta. Con 600 tokens `cl100k_base`, la cobertura any-gold fue **56,79 % literal, 69,39 % sparse, 51,11 % MiniLM dense y 71,34 % hybrid**; all-gold fue **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Son métricas de recuperación de evidencia, no exactitud de respuestas ni un ranking competitivo.

Protocol 2 corrige las categorías, usa una base FTS por conversación para impedir fugas BM25/IDF y publica MRR, nDCG y p99. Con 600 tokens, la latencia p95 de recuperación+packing fue **34,55 ms sparse** y **57,88 ms hybrid**. Hybrid ganó **1,96 puntos porcentuales** de any-gold en esta carga; es un trade-off medido, no una recomendación universal. [Informe](reports/2026-09-06-recall-protocol2.md) · [resumen JSON](reports/2026-09-06-recall-protocol2-summary.json).

El barrido sparse de 300 / 600 / 1200 tokens obtuvo **60,57 % / 69,39 % / 76,17 %** any-gold y latencias p95 de **20,39 / 34,55 / 61,78 ms**.

## Superficies de integración

| Superficie | Integración THM 1.3 |
| --- | --- |
| Hermes Agent | `MemoryProvider` descubierto por pip; setup/config, prefetch, `sync_turn` opcional, límites de sesión y write≠hit |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool`, un `FunctionTool` de solo lectura |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp`; salidas tipadas `thm_recall` y `thm_status` |
| OpenClaw 2026.9.x | `thm-mcp-legacy`; prueba MCP real sobre el mismo núcleo |
| Claude Code / Codex CLI / Gemini CLI | CLI reales fijados, comando exacto, discovery/call lifecycle y cero llamadas de modelo |

La E2E histórica de Hermes sigue fijada a `NousResearch/hermes-agent@77915e...`; CI 1.3 también prueba un snapshot actual revisado. La autoridad es siempre el workflow del commit exacto.

## Instalación y uso

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Extras: `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]` y `.[harnesses]`.

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Ciclo de vida de Hermes

Setup guarda scope/mode/budget y la sincronización opcional en configuración privada por perfil. `sync_turns` está desactivado por defecto. Si se activa, concilia texto user/assistant en un scope T2 derivado por sesión; excluye filas system y resúmenes de compresión. `on_memory_write` solo refresca y nunca cuenta como hit. THM permanece en pre-compress API v1 porque la caché derivada no es propietaria del transcript canónico y no puede prometer durabilidad fail-closed de checkpoint v2.

## Calibración del decay

Los barridos sintéticos son diagnósticos. `decay_from_index.py` exporta una cronología minimizada con IDs, costes y fechas de hit, sin texto, resúmenes, claves ni evidencia de confirmación; `decay_replay.py` la reproduce en privado. Sin una traza real no se afirma una curva o semivida óptima personal.

## Límites de la evidencia

THM no afirma exactitud E2E real, decay universalmente óptimo, movimiento automático entre niveles, propagación automática de borrado ni mejora de prompt-cache o latencia percibida. `scan` registra `mention_observed` débil con peso cero. Cobertura, plumbing, uso de evidencia por el modelo y calidad final son capas separadas.

Correctness CI corre en Linux, macOS y Windows; LoCoMo/modelos y las integraciones son trabajos separados. [Índice](docs/README.md) · [guía](docs/06-engine-guide.md) · [recall](docs/09-retrieval-and-measurement.md) · [adaptadores](docs/11-harness-adapters.md) · [versiones](docs/12-version-history.md) · [cambios](CHANGELOG.md).

Proyecto relacionado: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).

Version identity: **1.3.0 accepted/stable**.
