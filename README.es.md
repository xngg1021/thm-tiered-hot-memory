# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

THM es una herramienta local-first de memoria en cuatro niveles para Hermes Agent. T0 es `MEMORY.md` / `USER.md` en el snapshot de sesión; T1 es Markdown temático bajo demanda; T2 recupera historial con un presupuesto explícito; T3 conserva referencias externas.

Separa actividad, validez, relevancia para la tarea y pin explícito. Una mención no es un hit, retrieval no demuestra utilidad y una escritura no es un evento de uso. La versión 1.2 implementa FTS5 sparse retrieval, vectores semánticos locales opcionales, RRF, packing con presupuesto, `mention_observed` de peso cero, comparación de varias políticas de decay y un provider Hermes read-only.

El LoCoMo **Protocol 2** ya completado, con 600 evidence-tokens `cl100k_base` y 1.532 preguntas no adversariales completamente resolubles, obtuvo any-gold coverage de **literal 56,79% / sparse 69,39% / dense 51,11% / hybrid 71,34%** y all-gold de **46,61% / 56,53% / 40,01% / 57,64%**. No es precisión final de respuesta. Protocol 2 corrige categorías, aísla IDF por conversación y añade MRR / nDCG / p99. Resultados completos: [Protocol 2 report](reports/2026-09-06-recall-protocol2.md).

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Tras instalarlo, THM expone `thm` mediante el entry-point Hermes `hermes_agent.memory_providers`. Un E2E contra un upstream fijado verificó discovery real de Hermes, admission de MemoryProvider/MemoryManager, prefetch, memory-context fencing, session switch y que `on_memory_write` no se cuenta como hit ni modifica la base derivada de recall. El E2E usa evidencia sintética y cero llamadas de modelo: valida el ciclo de vida del provider, no la generación de respuestas. Véase [Hermes E2E report](reports/2026-09-06-hermes-e2e.md).

La calibración individual del decay puede exportar desde un índice THM v2 local una traza privada con solo entry IDs, costes unitarios y fechas explícitas de hit mediante `research/recall/decay_from_index.py`. Sin un historial real de hits, THM no afirma un half-life o una curva óptimos para el usuario.

THM no afirma haber demostrado aún precisión end-to-end con usuarios reales, un decay universalmente óptimo, movimiento/borrado automático entre niveles ni mejoras de latencia percibida. `mention_observed` de `scan` sigue teniendo peso cero.

Documentación: [índice](docs/README.md) · [guía del motor](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
