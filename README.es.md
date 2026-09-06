# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

THM es un sistema de memoria local-first de cuatro niveles para Hermes Agent. Se centra en un problema acotado: qué información merece ocupar contexto permanente, qué debe cargarse bajo demanda, cómo recuperar historial con un presupuesto fijo y cómo medir esas decisiones sin inventar señales de “uso”.

## Cuatro niveles

- **T0 — hot:** `MEMORY.md` / `USER.md` nativos inyectados en la instantánea al inicio de la sesión.
- **T1 — warm:** Markdown temático cargado bajo demanda.
- **T2 — cold:** sesiones históricas y archivos recuperados con un presupuesto explícito de evidencia.
- **T3 — external:** ubicaciones y referencias externas que pueden revisitarse cuando sea necesario.

THM separa actividad, validez, relevancia para la tarea y fijación explícita. Una mención no es un hit; una recuperación no prueba utilidad; una escritura no es un evento de uso.

## Implementado

El CLI 1.1.1 mantiene un índice ligado al perfil, identidades estrictas de eventos, vistas previas de migración, pin/unpin y escrituras protegidas ante fallos. El paquete 1.2 añade recuperación FTS5 por ámbito, embeddings locales opcionales, fusión RRF, empaquetado con presupuesto, observaciones `mention_observed` de peso cero, comparación de políticas de decaimiento, un adaptador read-only para Hermes y scripts de evaluación reproducibles.

Las rutas de retrieval y scan no reescriben los archivos nativos de memoria ni `state.db` de Hermes. Las bases SQLite derivadas rechazan objetivos ajenos antes de crear tablas THM.

## Evidencia medida

El benchmark histórico protocol 1 de LoCoMo usó 10 conversaciones y 1.986 preguntas. Con 600 tokens `cl100k_base` de evidencia y 1.532 preguntas no adversariales completamente resolubles, la cobertura any-gold fue **56,85% literal**, **69,58% sparse**, **51,11% MiniLM dense** y **70,04% hybrid**. Son métricas de recuperación de evidencia, no precisión final de respuesta ni ranking de competidores.

Protocol 2 corrige las etiquetas de categoría, aísla las estadísticas FTS5 IDF por conversación y añade MRR, nDCG y p99. La ejecución completa se realiza en el workflow de benchmark del repositorio.

## Instalación y uso

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Dependencias opcionales tokenizer / semantic: `python -m pip install -e '.[tokenizer,semantic]'`.

Tras instalarlo, THM expone el provider `thm` mediante el entry-point `hermes_agent.memory_providers` de Hermes. Un workflow de integración contra un checkout upstream fijado verifica discovery y ciclo de vida reales del provider.

## Límites de evidencia

THM no afirma haber demostrado todavía precisión end-to-end con usuarios reales, una curva de decaimiento universalmente óptima, movimiento automático entre niveles, propagación automática de borrados ni mejoras de prompt-cache o latencia percibida. `scan` sólo registra `mention_observed` débiles con peso de actividad cero. La calibración personal del decaimiento requiere un historial cronológico real de uso.

Documentación: [índice](docs/README.md) · [guía del motor](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [revisión de integración](docs/10-recall-integration-review.md) · [protocolo benchmark](research/recall/README.md)