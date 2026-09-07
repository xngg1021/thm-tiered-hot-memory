# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | Français | [Deutsch](README.de.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

## Quatre niveaux

THM est une mémoire locale à quatre niveaux pour les agent harnesses : T0 contexte permanent natif, T1 dossiers thématiques à la demande, T2 historique recherché sous budget explicite, T3 références externes revisitées au besoin. Activité, validité, pertinence et pin sont distincts : mention, retrieval et write ne prouvent pas un hit utile.

## Fonctionnalités

1.1.1 fournit un index CLI robuste ; 1.2 ajoute FTS5 par scope, embeddings locaux facultatifs, RRF, packing budgété, observations de poids nul, comparaisons de decay et évaluations reproductibles. **1.3 ajoute une couche de recall en lecture seule et indépendante du harness** : Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` et MCP v2 stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI et Gemini CLI utilisent un pont MCP séparé en lecture seule, testé avec des versions réelles figées. Les sources natives ne sont jamais réécrites et aucun appel modèle supplémentaire n'est effectué.

## Mesures LoCoMo

Protocol 2 couvre 10 conversations, 1 986 questions et un dénominateur principal de 1 532 questions. À 600 tokens, any-gold vaut **56,79 % literal / 69,39 % sparse / 51,11 % dense / 71,34 % hybrid** ; all-gold vaut **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Ce sont des métriques de preuve, pas d'exactitude des réponses. Le p95 retrieval+packing est **34,55 ms sparse / 57,88 ms hybrid**. À 300/600/1200 tokens, sparse atteint **60,57/69,39/76,17 %** avec **20,39/34,55/61,78 ms**. [Rapport](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## Intégrations

| Surface | THM 1.3 |
| --- | --- |
| Hermes | provider pip, setup/config, prefetch, `sync_turn` optionnel, session hooks, write≠hit |
| OpenAI Agents | `OpenAIAgentsTHM.tool` en lecture seule |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, `thm_recall` et `thm_status` typés |
| OpenClaw | `thm-mcp-legacy`, probe réel |
| Claude/Codex/Gemini | CLI réels figés, commande exacte, discovery/call lifecycle, zéro appel modèle |

## Installation

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras : `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`. Le pont compatible est `thm-mcp-legacy`.

## Cycle Hermes

`sync_turns` est désactivé par défaut. Activé explicitement, il copie seulement les textes user/assistant vers un scope T2 dérivé par session ; lignes system et résumés de compression sont exclus. `on_memory_write` reste un signal de refresh. THM conserve pre-compress API v1 car la cache dérivée n'est pas propriétaire du transcript canonique et ne peut promettre checkpoint-v2 fail-closed.

## Calibration du decay

`decay_from_index.py` exporte uniquement IDs, coûts et dates de hit, sans texte, résumés, clés ni confirmations ; `decay_replay.py` rejoue cette trace en privé. Sans trace réelle, aucune demi-vie optimale personnelle n'est revendiquée.

## Limites de preuve

THM ne revendique pas encore exactitude E2E réelle, decay universellement optimal, déplacement automatique de niveaux, propagation de suppression, gain de prompt-cache ou latence perçue. Coverage, plumbing, usage de la preuve et qualité finale restent quatre couches distinctes. Correctness CI couvre Linux, macOS et Windows ; LoCoMo et les intégrations sont séparés.

[Index](docs/README.md) · [Guide](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [Versions](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## État stable actuel de THM 1.4

THM 1.4 est terminé et figé comme **accepted/stable implementation milestone**. Le jalon stable code/contenu est `e6e4dda5835e3cb345207457d5491131c6959b2c` et le pointeur de restauration est `archive/v1.4.0-stable`. Le modèle à quatre niveaux T0–T3 reste inchangé.

Au-dessus du recall harness-neutral de 1.3, la 1.4 ajoute une telemetry explicite resident/hard miss et planned retrieval, un répertoire T1 strictement locator-only, une recommandation shadow T0 fondée sur avoidable-miss penalty face au resident carry cost, un packing 0/1 exact et borné, un prefetch borné entraîné uniquement par la co-occurrence de demande réelle, et un resident-budget feedback qui ne modifie jamais automatiquement le budget. Hermes dispose aussi d'un T1 locator snapshot session-frozen, désactivé par défaut.

Ces surfaces ont passé l'acceptation correctness, Hermes et multi-harness de la 1.4. La 1.4 n'ayant pas modifié le retrieval path, aucun nouveau chiffre LoCoMo/Protocol 2 n'est revendiqué. Le mouvement automatique T0–T3 et la modification automatique du budget restent désactivés jusqu'à ce qu'un A/B held-out runtime/tâches démontre simultanément des gains de qualité, coût, latence et reacquisition. Voir [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) et [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.
