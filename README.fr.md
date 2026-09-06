# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

THM est un outil de mémoire local-first à quatre niveaux pour Hermes Agent. T0 correspond à `MEMORY.md` / `USER.md` dans le snapshot de session ; T1 aux Markdown thématiques à la demande ; T2 à la recherche historique sous budget explicite ; T3 aux références externes.

THM sépare activité, validité, pertinence de tâche et pin explicite. Une mention n'est pas un hit, un retrieval ne prouve pas l'utilité et une écriture n'est pas un événement d'usage. La version 1.2 implémente FTS5 sparse retrieval, des vecteurs sémantiques locaux optionnels, RRF, le packing sous budget, `mention_observed` de poids nul, plusieurs politiques de decay et un provider Hermes read-only.

Le LoCoMo **Protocol 2** terminé, avec 600 evidence-tokens `cl100k_base` et 1 532 questions non adversariales entièrement résolubles, obtient une any-gold coverage de **literal 56,79 % / sparse 69,39 % / dense 51,11 % / hybrid 71,34 %** et une all-gold coverage de **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Ce n'est pas la précision finale des réponses. Protocol 2 corrige les catégories, isole IDF par conversation et ajoute MRR / nDCG / p99. Résultats complets : [Protocol 2 report](reports/2026-09-06-recall-protocol2.md).

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Après installation, THM expose `thm` via l'entry-point Hermes `hermes_agent.memory_providers`. Un E2E sur un upstream épinglé a vérifié la discovery Hermes réelle, l'admission MemoryProvider/MemoryManager, prefetch, memory-context fencing, session switch, ainsi que le fait que `on_memory_write` n'est pas compté comme hit et ne modifie pas la base de recall dérivée. Cet E2E utilise des données synthétiques et zéro appel modèle : il valide le cycle de vie du provider, pas la génération de réponses. Voir [Hermes E2E report](reports/2026-09-06-hermes-e2e.md).

La calibration individuelle du decay peut exporter depuis un index THM v2 local une trace privée ne contenant que les entry IDs, les coûts unitaires et les dates explicites de hit via `research/recall/decay_from_index.py`. Sans historique réel de hits, THM ne revendique pas un half-life ou une courbe optimale pour l'utilisateur.

THM ne prétend pas encore avoir démontré la précision end-to-end pour un utilisateur réel, un decay universellement optimal, le déplacement/suppression automatique entre niveaux ni un gain de latence perçue. Le `mention_observed` de `scan` conserve un poids nul.

Documentation : [index](docs/README.md) · [guide moteur](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
