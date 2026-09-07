# THM — Tiered Hot Memory

**Infrastructure de mémoire hiérarchisée, locale et déterministe pour les agents IA.** THM sépare ce qui mérite de rester hot/resident de ce qui peut être récupéré à la demande, puis évalue ces décisions par des coûts et des preuves observables au lieu de dépendre par défaut d’un autre LLM pour réécrire la mémoire.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | Français | [Español](README.es.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

## Pourquoi THM existe

Un agent qui fonctionne longtemps accumule plus d’état qu’il n’est raisonnable d’injecter dans chaque prompt. Garder tout le contexte résident impose un carry cost répété ; tout supprimer impose des coûts répétés de search, retrieval et reacquisition. THM traite donc la mémoire comme un problème de **residency, retrieval et allocation de budget bornée**.

La question centrale est :

> **Jusqu’où peut aller une mémoire d’agent sans appeler un autre LLM ?**

THM privilégie donc les signaux déterministes, les index locaux, une provenance explicite, des budgets d’evidence bornés et des règles de contrôle rejouables. L’extraction générative, le résumé et la réécriture de mémoire ne sont pas des prérequis du core dataplane.

## Philosophie de conception

### 1. La source reste autoritative

Les fichiers de mémoire natifs, les transcripts de session et les sources externes sont l’autorité. SQLite/FTS, embeddings locaux, locators et autres structures THM sont des **index ou projections dérivés**. Le retrieval ne doit pas réécrire silencieusement la source qu’il cherche à mémoriser.

### 2. Residency, relevance et activity restent séparés

THM distingue :

- **tier** — où l’item réside et comment il est accédé ;
- **activity** — si l’agent l’a réellement utilisé ;
- **validity** — s’il reste valide et digne de confiance ;
- **pinning** — une contrainte explicite de l’opérateur ;
- **retrieval evidence** — si un chemin de recherche l’a exposé pendant une tâche.

Une mention n’est pas un hit. Le retrieval ne prouve pas l’utilité. Le prefetch n’est pas une demande. Un write n’est pas un activity event.

### 3. La mémoire froide doit rester peu coûteuse

Le hot prompt est une ressource rare. THM utilise des locators et un retrieval borné pour laisser les contenus froids hors du resident context jusqu’à ce qu’une tâche en ait réellement besoin. Un locator court peut mériter de rester résident alors que la source complète ne le mérite pas.

### 4. Les budgets fixes font partie de la correctness

La présence d’un gold item quelque part dans un grand candidate pool ne suffit pas. THM mesure si l’evidence utile est réellement empaquetée dans un budget de tokens fixe. Oversized sources, doublons et packing waste sont donc des pertes réelles.

### 5. Pas de boucle de retrieval auto-renforcée

Un item ne doit pas devenir plus important simplement parce que le système l’a lui-même prefetched ou retrieved. Le control plane apprend uniquement à partir d’une demande explicite et conserve une frontière anti-self-training.

### 6. L’automatisation vient après l’evidence

THM peut produire des recommandations shadow de residency, prefetch et budget, mais automatic promote/demote et automatic budget write-back restent désactivés tant qu’un held-out task evidence ne démontre pas un gain net de qualité, coût, latence et reacquisition.

### 7. Un seul memory core, plusieurs surfaces de Harness

La sémantique de retrieval reste dans le core THM. Hermes possède l’intégration lifecycle la plus profonde ; OpenAI Agents et LangChain utilisent des adapters SDK natifs ; MCP fournit une surface de protocole partagée par plusieurs CLI/harnesses.

## Les Tiers T0–T3

| Tier | Rôle | Usage typique |
| --- | --- | --- |
| **T0 — Hot** | Mémoire résidente déjà portée par le host | Petit contexte de forte valeur qui justifie régulièrement sa résidence |
| **T1 — Warm** | Mémoire orientée locator, développée à la demande | Locators topic/file/source et références warm bornées |
| **T2 — Cold** | Historique et archives locales interrogeables | Retrieval FTS/dense scoped sous budget d’evidence explicite |
| **T3 — External** | Emplacements de source reacquérables | Fichiers, URLs ou systèmes externes revisités au besoin |

T0–T3 sont les **memory Tiers de THM**. Ils sont indépendants des L0–L6 Layers du projet séparé Context Economics.

## Capacités actuellement implémentées

THM fournit aujourd’hui :

- index local isolé par profile/scope avec contrôles fail-closed de source/database ;
- retrieval sparse SQLite FTS5, embeddings locaux optionnels et fusion de rang déterministe ;
- evidence packing sous budget de tokens avec source traceability ;
- sémantiques explicites activity / validity / pin et diagnostics de decay reproductibles ;
- un recall core read-only indépendant du harness ;
- Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 et une pinned compatibility bridge pour certains CLI hosts ;
- telemetry resident/hard-miss et planned-retrieval ;
- T1 warm directory locator-only et snapshot Hermes session-frozen opt-in ;
- shadow T0 recommendation fondée sur miss cost et resident carry cost avec bounded exact 0/1 packing ;
- bounded anti-self-training prefetch et shadow resident-budget feedback ;
- opt-in zero-generative-LLM entity projection qui rerank uniquement les candidates sparse/hybrid existants sans changer le modèle canonique T0–T3.

La ligne stable du package reste **1.4.0**. La zero-LLM entity projection est mergée dans main comme opt-in research successor, mais **n’est pas déclarée 1.5 stable**. Les anciennes versions, PR, reviews et chronologies de développement sont conservées dans [CHANGELOG.md](CHANGELOG.md) et [version history](docs/12-version-history.md), pas sur la homepage.

## Evidence de retrieval mesurée

THM sépare toujours retrieval evidence et claims sur la génération de réponse.

Le LoCoMo Protocol 2 canonique utilise 1 532 questions non adversariales entièrement résolues et une tranche fixe de 600 tokens `cl100k_base`.

| Retrieval mode | Any-gold packed evidence | All-gold packed evidence | p95 retrieval + packing |
| --- | ---: | ---: | ---: |
| Literal | 56.79% | 46.61% | — |
| Sparse | **69.39%** | **56.53%** | **34.55 ms** |
| Local dense | 51.11% | 40.01% | — |
| Hybrid | **71.34%** | **57.64%** | **57.88 ms** |

L’opt-in deterministic entity projection actuelle fait passer le sparse any-gold full-set de **69.39% à 72.52%** et le holdout figé de 1 301 questions de **69.56% à 72.33%**, sans modifier la candidate coverage. Le gain vient donc du fait de **mieux placer des candidates déjà disponibles dans la tranche de 600 tokens**, et non d’élargir le pool avec un autre modèle.

Ces nombres mesurent la **packed retrieval evidence**, pas la précision finale des réponses, la satisfaction utilisateur ou une supériorité universelle. Voir [Protocol 2](reports/2026-09-06-recall-protocol2.md) et [zero-LLM frontier](docs/16-zero-llm-retrieval-frontier.md).

## Intégration Harness

| Surface | Profondeur d’intégration |
| --- | --- |
| **Hermes Agent** | `MemoryProvider` natif ; setup/config, prefetch, live-turn sync optionnel, session boundary hooks, memory-write refresh semantics |
| **OpenAI Agents SDK** | `FunctionTool` natif read-only |
| **LangChain / LangGraph / Deep Agents** | Surface native `BaseRetriever` |
| **MCP v2** | `thm_recall` et `thm_status` typés en read-only via stdio |
| **OpenClaw** | Pinned compatibility probe via legacy MCP bridge |
| **Claude Code / Codex CLI / Gemini CLI** | Pinned real-CLI discovery/call lifecycle via le même read-only recall core |

Le support multi-harness ne fait pas de THM une memory database universelle. La profondeur lifecycle varie selon le host ; Hermes reste l’intégration native la plus profonde.

## Quick start

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Dépendances optionnelles :

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP :

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Invariants importants

- le read-only retrieval ne modifie pas la native memory ;
- retrieval/display/scan ne fabriquent pas de usage activity ;
- `planned_retrieval` n’est pas un miss ;
- le prefetch ne crée ni demand, ni hit, ni renewal, ni promotion evidence ;
- seuls les misses explicitement `avoidable=true` peuvent contribuer au residency benefit ;
- T1 `pinned` n’implique pas automatic promotion ;
- les projections locator restent locator-only et doivent résoudre dans le bon scope ;
- un ordinary mid-session memory write ne rebuild pas silencieusement le frozen Hermes prompt snapshot ;
- automatic tier movement et budget write-back restent désactivés sans held-out task evidence.

## Evidence boundary

THM prend en charge des expériences de deterministic/local retrieval et shadow control, mais ne revendique pas une amélioration universelle de la qualité finale, une decay curve optimale pour tous, un automatic T0–T3 movement production-ready, une propagation automatique des suppressions sûre, des gains prompt-cache/user-latency déduits de métriques de retrieval, ni l’usage garanti d’un evidence item par le modèle hôte.

Unit/invariant evidence, retrieval benchmark, harness lifecycle et real task outcome sont des classes de preuve différentes.

## Documentation

- [Documentation index](docs/README.md)
- [Engine guide](docs/06-engine-guide.md)
- [Retrieval and measurement](docs/09-retrieval-and-measurement.md)
- [Harness adapters](docs/11-harness-adapters.md)
- [Version history and recovery](docs/12-version-history.md)
- [1.4 residency control plane](docs/14-residency-control-plane.md)
- [Hermes warm directory](docs/15-hermes-warm-directory.md)
- [Zero-LLM retrieval frontier](docs/16-zero-llm-retrieval-frontier.md)
- [Changelog](CHANGELOG.md)

THM reste un logiciel de recherche. 1.4.0 est l’accepted/stable implementation milestone ; le retrieval frontier suivant reste explicitement unreleased. Une version ne remplace jamais une evidence class.
