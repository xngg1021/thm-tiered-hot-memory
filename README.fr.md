# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

THM est un outil de mémoire local-first à quatre niveaux pour Hermes Agent. T0 correspond à `MEMORY.md` / `USER.md` dans le snapshot de session ; T1 aux Markdown thématiques à la demande ; T2 à la recherche historique sous budget ; T3 aux références externes.

THM sépare activité, validité, pertinence de tâche et pin explicite. Une mention n'est pas un hit, un retrieval ne prouve pas l'utilité et une écriture n'est pas un événement d'usage. La version 1.2 implémente FTS5 sparse retrieval, des vecteurs sémantiques locaux optionnels, RRF, le packing sous budget, `mention_observed` de poids nul, la comparaison de decay et un provider Hermes read-only.

Dans le LoCoMo historique protocol 1, avec 600 evidence-tokens `cl100k_base` et 1 532 questions non adversariales entièrement résolubles, any-gold coverage était **literal 56,85 % / sparse 69,58 % / dense 51,11 % / hybrid 70,04 %**. Ce n'est pas la précision finale des réponses. Protocol 2 corrige les catégories, isole IDF par conversation et ajoute MRR / nDCG / p99.

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

Après installation, THM expose `thm` via l'entry-point Hermes `hermes_agent.memory_providers`. Un workflow E2E sur un upstream épinglé vérifie la discovery et le provider lifecycle réels.

THM ne prétend pas encore avoir démontré la précision end-to-end pour un utilisateur réel, un decay universellement optimal, le déplacement/suppression automatique entre niveaux ni un gain de latence perçue. La calibration individuelle du decay nécessite un historique chronologique réel de hits.

Documentation : [index](docs/README.md) · [guide moteur](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
