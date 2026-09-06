# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

THM es una herramienta local-first de memoria en cuatro niveles para Hermes Agent. T0 es `MEMORY.md` / `USER.md` en el snapshot de sesión; T1 es Markdown temático bajo demanda; T2 recupera historial con presupuesto explícito; T3 conserva referencias externas.

Separa actividad, validez, relevancia para la tarea y pin explícito. Una mención no es un hit, retrieval no demuestra utilidad y una escritura no es un evento de uso. La versión 1.2 implementa FTS5 sparse retrieval, vectores semánticos locales opcionales, RRF, packing con presupuesto, `mention_observed` de peso cero, comparación de decay y un provider Hermes read-only.

En el LoCoMo histórico protocol 1, con 600 evidence-tokens `cl100k_base` y 1.532 preguntas no adversariales completamente resolubles, any-gold coverage fue **literal 56,85% / sparse 69,58% / dense 51,11% / hybrid 70,04%**. No es precisión final de respuesta. Protocol 2 corrige categorías, aísla IDF por conversación y añade MRR / nDCG / p99.

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Tras instalarlo, THM expone `thm` mediante el entry-point Hermes `hermes_agent.memory_providers`. Un workflow E2E contra un upstream fijado verifica discovery y provider lifecycle reales.

THM no afirma haber demostrado aún precisión end-to-end con usuarios reales, un decay universalmente óptimo, movimiento/borrado automático entre niveles ni mejoras de latencia percibida. La calibración individual del decay requiere un historial cronológico real de hits.

Documentación: [índice](docs/README.md) · [guía del motor](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
