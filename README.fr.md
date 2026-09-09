# THM — Tiered Hot Memory

**Infrastructure de mémoire hiérarchisée, locale et déterministe pour les agents IA.** THM sépare ce qui mérite de rester hot/resident de ce qui peut être récupéré à la demande, puis évalue ces décisions par des coûts et des preuves observables au lieu de dépendre par défaut d’un autre LLM pour réécrire la mémoire.

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | Français | [Español](README.es.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

<!-- section:architecture -->
## Architecture à trois plans

THM sépare mémoire logique, exécution du calcul et stockage physique. Evaluation Fabric mesure ces plans sans ajouter un nouvel algorithme de mémoire. L’identité de la source et le scope restent la référence pour toute représentation.

Contrats d’architecture et de preuve

Le package stable et l’archive restent en 1.4.0. Runtime, Physical Storage Fabric et Evaluation Fabric restent Unreleased. Les mesures existantes conservent protocole, SHA source et périmètre ; aucun benchmark non exécuté ou matériel non mesuré ne devient accepted evidence.

<!-- section:machine-corrective -->
## Mesures Z6 et politique corrigée

Le Z6 G4 a exécuté CPU reference, RTX 3080 CUDA et auto-throughput sur `b1f8119`, avec mesure des coûts StorageProfile NTFS/NVMe locaux. Les plongements de documents sur GPU étaient nettement plus rapides et le sous-ensemble LME borné améliorait le temps total. La qualité agrégée LoCoMo était équivalente, mais CUDA présentait 23 lignes strictement différentes, dont 3 changements d’ensemble sélectionné. L’ancien auto-safe a échoué. La politique corrigée sépare la borne numérique FP32 de l’identité exacte de la structure de recherche et autorise un repli explicite vers la référence sans prétendre à une accélération. La validation matérielle après correction, le dispatch AVX/VNNI observé et LME complet restent en attente.

[2026-09-09 evidence](reports/2026-09-09-local-acceptance-b1f8119.md) · [Corrective contract / short retest](docs/19-post-local-corrective.md)

<!-- section:philosophy -->
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

<!-- section:logical -->
## Plan de mémoire logique

SearchIndex limité au scope, assemblage des preuves sous budget et contrôle de résidence en observation partagent le même noyau. T0–T3 décrivent la résidence et l’accès logiques. Activité, validité, épinglage et recherche restent distincts ; promotion automatique et réécriture du budget restent désactivées.

<!-- section:tiers -->
## Les Tiers T0–T3

| Tier | Rôle | Usage typique |
| --- | --- | --- |
| **T0 — Hot** | Mémoire résidente déjà portée par le host | Petit contexte de forte valeur qui justifie régulièrement sa résidence |
| **T1 — Warm** | Mémoire orientée locator, développée à la demande | Locators topic/file/source et références warm bornées |
| **T2 — Cold** | Historique et archives locales interrogeables | Retrieval FTS/dense scoped sous budget d’evidence explicite |
| **T3 — External** | Emplacements de source reacquérables | Fichiers, URLs ou systèmes externes revisités au besoin |

T0–T3 sont les **memory Tiers de THM**. Ils sont indépendants des L0–L6 Layers du projet séparé Context Economics.

<!-- section:compute -->
## Plan d’exécution du calcul

RuntimeProfile lie encodeur/backend, précision, appareil, scorer, tailles de lots et threads. Le scheduler optionnel et AutoTune borné choisissent des configurations explicites. Les descriptions CPU/CUDA exigent des preuves runtime distinctes ; une fixture réussie ne démontre ni dispatch ni accélération.

[Runtime](docs/17-zero-llm-heterogeneous-runtime.md)

<!-- section:physical -->
## Plan de stockage physique

StorageProfile décrit les coûts d’accès mesurés ; placement lie une représentation à une cible. PhysicalTelemetry enregistre les I/O réelles des extents. Les chemins buffered/mmap du système de fichiers local sont implémentés et vérifiés. CXL, DAX, SPDK, GDS et transports distants restent des descriptions d’extension sans performance matérielle validée.

[Physical Storage Fabric](docs/physical-storage-fabric.md)

<!-- section:evaluation -->
## Evaluation Fabric

Les adapters normalisent les entrées natives en Task, GroundTruth réservée à l’évaluateur, Result et Receipt lié par SHA. LoCoMo Protocol 2 et LongMemEval-S partagent les métriques dataplane en conservant les unités document et session. LongMemEval-V2 prend en charge les trajectory states publics et insert/query ; BEAM les batches/turns et probing questions natifs ; MemoryArena les sous-tâches natives et add/wrap_user_prompt entre sessions.

Les fixtures vérifient uniquement les interfaces et la recherche déterministe. V2 utilise le texte seul et refuse les requêtes image. Sans gold locator, le rappel vaut null. Le parsing MemoryArena n’exécute pas l’environnement. Réponses et rubrics ne sont jamais indexées.

| Couche de preuve | Contrat du receipt |
| --- | --- |
| memory-dataplane | any/all-gold, rappel macro/micro, couverture parent, budget, latence |
| systems-runtime | Profil de calcul, StorageProfile, placement, télémétrie I/O |
| LLM-agent-outcome | Appels génération/judge, exactitude, succès environnement ; not-run par défaut |

[Evaluation Fabric](docs/18-evaluation-fabric.md)

<!-- section:evidence -->
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

<!-- section:harness -->
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

<!-- section:acceptance -->
## Validation locale bornée

Exécuter à la racine du dépôt avec Python 3.10 ou plus récent. Aucun téléchargement de modèle ou de jeu de données, ni clé provider, n’est nécessaire. La limite de l’arbre de processus est de 3300 secondes, avec une marge de nettoyage sous 60 minutes. Un dépassement ou échec produit un receipt incomplet et un code non nul.

```powershell
python -m thm.evaluation --mode acceptance --wall-seconds 3300 --output .thm-evaluation/acceptance-01
```

Les campagnes complètes sont activées séparément avec --mode full-research --full-research --benchmark NAME --dataset FILE. Elles demandent des entrées natives préparées extérieurement et des agents, environnements et judges configurés séparément. Cette commande mesure uniquement la recherche, sans lancer d’agent réel ni accepter automatiquement le benchmark.

<!-- section:invariants -->
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

<!-- section:boundary -->
## Evidence boundary

THM prend en charge des expériences de deterministic/local retrieval et shadow control, mais ne revendique pas une amélioration universelle de la qualité finale, une decay curve optimale pour tous, un automatic T0–T3 movement production-ready, une propagation automatique des suppressions sûre, des gains prompt-cache/user-latency déduits de métriques de retrieval, ni l’usage garanti d’un evidence item par le modèle hôte.

Unit/invariant evidence, retrieval benchmark, harness lifecycle et real task outcome sont des classes de preuve différentes.

<!-- section:documentation -->
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
