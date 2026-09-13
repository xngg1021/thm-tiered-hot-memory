# THM — Tiered Hot Memory

**Infraestructura de memoria jerarquizada, local-first y determinista para agentes de IA.** THM separa qué merece permanecer hot/resident de qué puede recuperarse bajo demanda, y evalúa esas decisiones con coste y evidencia observables en lugar de depender por defecto de otro LLM para reescribir la memoria.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | Español

Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

<!-- section:architecture -->
## Arquitectura de tres planos

THM separa memoria lógica, ejecución de cómputo y almacenamiento físico. La versión 1.5.0 integra estos planos, Evaluation Fabric, un actuador explícito de residencia y la Context Economics bridge independiente. La identidad y el ámbito de la fuente conservan la autoridad. La evidencia histórica de 1.4.0 mantiene su protocolo y SHA; la estabilidad de implementación no otorga aceptación de hardware ni tareas.

La versión 1.6.0 incorpora un entorno de sistemas opcional para agentes: épocas de topología dinámica, observación térmica y energética, concurrencia acotada, E/S nativa, análisis de fiabilidad, recuperación determinista de memoria extensa y evidencia CE v2. «Hot» abarca estados lógicos, de cómputo, físicos, térmicos, económicos, de demanda y de fiabilidad; no crea niveles nuevos. La ejecución nativa, el rendimiento sostenido y los resultados de los agentes se validan por separado.

[1.6 runtime](docs/24-agent-systems-runtime.md) · [0-LLM ceiling](docs/25-long-tail-ceiling.md) · [1.6 completion](reports/2026-09-13-thm-1.6-full-power-completion.md)

<!-- section:philosophy -->
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

<!-- section:logical -->
## Plano de memoria lógica

SearchIndex limitado por scope, empaquetado de evidencia bajo presupuesto y control de residencia en observación comparten un núcleo. T0–T3 describen residencia y acceso lógicos. Actividad, validez, fijación y búsqueda se registran por separado; promoción automática y escritura de presupuestos siguen desactivadas.

El actuador explícito admite dry-run, reproducción, aprobación del plan exacto, cambios transaccionales de ubicación, reversión y auditoría. La mutación automática sigue en false por defecto; se comprueban validez de fuente, pin, demanda, capacidad y evidencia.

<!-- section:tiers -->
## T0–T3 Memory Tiers

| Tier | Rol | Uso típico |
| --- | --- | --- |
| **T0 — Hot** | Memoria residente que el host ya transporta | Contexto pequeño de alto valor que justifica repetidamente su residencia |
| **T1 — Warm** | Memoria orientada a locator que se expande bajo demanda | Locators de topic/file/source y bounded warm references |
| **T2 — Cold** | Historial y archivos locales consultables | Scoped FTS/dense retrieval con evidence budget explícito |
| **T3 — External** | Ubicaciones de fuente que pueden reacquirirse | Archivos, URLs o sistemas externos |

T0–T3 son **Memory Tiers de THM**. Son independientes de las L0–L6 Layers del proyecto separado Context Economics.

<!-- section:compute -->
## Plano de ejecución de cómputo

El runtime sin ajustes iniciales comienza con una ruta segura disponible, observa solicitudes reales y explora proveedores instalados dentro de límites de recursos en segundo plano. Provider Fabric separa inferencia, índices vectoriales residentes y transferencias en CPU, GPU y NPU. La paridad semántica, una mejora sustancial, la vigencia de los perfiles y los límites de sesión controlan la adopción; el usuario no necesita ejecutar antes un benchmark. Los perfiles y comprobantes muestran la ejecución real y las rutas de respaldo. Los SDK y modelos opcionales nunca se descargan automáticamente; la madurez de implementación se distingue de la validación del hardware.

[Zero-touch runtime](docs/20-zero-touch-runtime.md) · [Provider Fabric](docs/21-provider-fabric.md) · [Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## Plano de almacenamiento físico

StorageProfile describe costes de acceso medidos, placement vincula una representación con un destino y PhysicalTelemetry registra E/S por intervalos. Archivos con búfer/mmap, transportes configurados transaccionales, S3, propiedad de asignaciones y ubicación conjunta cuentan con rutas ejecutables y fixtures. CXL, DAX, SPDK, GDS y las familias remotas comparten contratos de ciclo de vida acotados; la ejecución nativa y el rendimiento real requieren evidencia separada.

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Los adapters normalizan entradas nativas como Task, GroundTruth exclusiva del evaluador, Result y Receipt vinculado por SHA. LoCoMo Protocol 2 y LongMemEval-S comparten métricas dataplane conservando unidades de documento y sesión. LongMemEval-V2 admite trajectory states públicos e insert/query; BEAM, batches/turns y probing questions nativos; MemoryArena, subtareas nativas y add/wrap_user_prompt entre sesiones.

Los fixtures solo verifican interfaces y búsqueda determinista. V2 funciona con texto y rechaza consultas con imágenes. Sin gold locators, recall es null. Analizar tareas MemoryArena no ejecuta el entorno. Respuestas y rubrics nunca entran en los documentos de búsqueda.

| Capa de evidencia | Contrato del receipt |
| --- | --- |
| memory-dataplane | any/all-gold, recall macro/micro, cobertura padre, presupuesto, latencia |
| systems-runtime | Perfil de cómputo, StorageProfile, placement, telemetría I/O |
| LLM-agent-outcome | Llamadas generación/judge, exactitud, éxito del entorno; not-run por defecto |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

EnvironmentRunner proporciona un ciclo de entorno acotado y OfficialScorerBridge aísla las respuestas exclusivas del evaluador. Los adjuntos Outcome vinculan las tareas ejecutadas y trace SHA, con cobertura parcial, puntuaciones ausentes, agregados macro/micro y latencia/coste observados. THM exporta evidencia con unidades y denominadores a Context Economics y acepta recomendaciones explícitas de presupuesto y límites. THM T0–T3 y CE L0–L6 siguen siendo independientes.

<!-- section:evidence -->
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

<!-- section:harness -->
## Integración con Harness

| Surface | Profundidad de integración |
| --- | --- |
| **Hermes Agent** | `MemoryProvider` nativo; setup/config, prefetch, optional live-turn sync, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | `FunctionTool` nativo read-only |
| **LangChain / LangGraph / Deep Agents** | BaseRetriever nativo, nodo LangGraph ejecutable, herramientas recall/status de Deep Agents y construcción del grafo |
| **MCP v2** | `thm_recall` y `thm_status` typed/read-only por stdio |
| **OpenClaw** | Pinned compatibility probe mediante legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle sobre el mismo read-only recall core |

El soporte multi-harness no convierte THM en una memory database universal. La profundidad del lifecycle depende del host; Hermes sigue siendo la integración nativa más profunda.

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

Dependencias opcionales:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
# Deep Agents: Python >= 3.11
python -m pip install -e '.[harnesses]'
```

MCP:

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

<!-- section:acceptance -->
## Validación local acotada

Ejecutar desde la raíz del repositorio con Python 3.10 o posterior. No requiere descargar modelos o datasets ni claves provider. El límite del árbol de procesos es 3300 segundos y deja margen de limpieza por debajo de 60 minutos. Un timeout o fallo genera un receipt incompleto y un código distinto de cero.

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

Las campañas completas se habilitan por separado con --mode full-research --full-research --benchmark NAME --dataset FILE. Requieren entradas nativas preparadas externamente y agentes, entornos y judges configurados aparte. Este comando solo mide búsqueda; no inicia agentes reales ni acepta automáticamente benchmarks.

<!-- section:invariants -->
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

<!-- section:boundary -->
## Evidence boundary

THM admite experimentos sólidos de deterministic/local retrieval y shadow control, pero no afirma una mejora universal de answer quality, una decay curve óptima para todos, automatic T0–T3 movement production-ready, propagación automática de borrado segura, mejoras de prompt-cache/user-latency deducidas de métricas de retrieval, ni uso garantizado por el modelo de un evidence item recuperado.

Unit/invariant evidence, retrieval benchmark, harness lifecycle y real task outcome son evidence classes diferentes.

<!-- section:documentation -->
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

THM 1.5.0 es un hito de implementación con evidencia separada de integración, hardware, benchmarks y tareas. Los experimentos de recuperación rechazados siguen siendo reproducibles y desactivados por defecto.
