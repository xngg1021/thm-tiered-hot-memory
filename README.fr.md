# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

THM est un outil de mémoire local-first à quatre niveaux pour Hermes Agent. Il cible un problème limité : quelles informations méritent d'occuper le contexte permanent, lesquelles doivent être chargées à la demande, comment rappeler l'historique sous un budget fixe et comment mesurer ces décisions sans fabriquer de signaux d'« utilisation ».

## Quatre niveaux

- **T0 — hot :** `MEMORY.md` / `USER.md` natifs injectés dans l'instantané au début de la session.
- **T1 — warm :** Markdown thématique chargé à la demande.
- **T2 — cold :** sessions historiques et archives recherchées sous un budget explicite de preuves.
- **T3 — external :** emplacements et références externes revisités si nécessaire.

THM sépare activité, validité, pertinence pour la tâche et épinglage explicite. Une mention n'est pas un hit ; une récupération ne prouve pas l'utilité ; une écriture n'est pas un événement d'utilisation.

## Implémentation actuelle

Le CLI 1.1.1 maintient un index lié au profil, des identités d'événements strictes, des aperçus de migration, pin/unpin et des écritures protégées contre les échecs. Le paquet 1.2 ajoute la recherche FTS5 par scope, des embeddings locaux optionnels, la fusion RRF, le packing sous budget, des `mention_observed` de poids nul, plusieurs politiques de décroissance, un adaptateur Hermes en lecture seule et des scripts d'évaluation reproductibles.

Les chemins retrieval et scan ne réécrivent ni les fichiers mémoire natifs ni le `state.db` de Hermes. Les bases SQLite dérivées refusent une base étrangère avant de créer les tables THM.

## Résultats mesurés

Le benchmark historique LoCoMo protocol 1 a utilisé 10 conversations et 1 986 questions. Avec un budget de 600 tokens `cl100k_base` et 1 532 questions non adversariales entièrement résolubles, la couverture any-gold était de **56,85 % literal**, **69,58 % sparse**, **51,11 % MiniLM dense** et **70,04 % hybrid**. Il s'agit de métriques de récupération de preuves, pas de précision finale des réponses ni d'un classement concurrentiel.

Protocol 2 corrige les étiquettes de catégorie, isole les statistiques FTS5 IDF par conversation et ajoute MRR, nDCG et p99. L'exécution complète est réalisée par le workflow benchmark du dépôt.

## Installation

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Dépendances optionnelles tokenizer / semantic : `python -m pip install -e '.[tokenizer,semantic]'`.

Après installation, THM expose le provider `thm` via l'entry-point Hermes `hermes_agent.memory_providers`. Un workflow d'intégration sur un checkout upstream épinglé vérifie la découverte et le cycle de vie réels du provider.

## Limites des preuves

THM ne prétend pas encore avoir démontré la précision end-to-end pour un utilisateur réel, une courbe de décroissance universellement optimale, le déplacement automatique entre niveaux, la propagation automatique des suppressions, ni un gain de prompt-cache ou de latence perçue. `scan` ne produit que de faibles `mention_observed` avec un poids d'activité nul. La calibration individuelle exige un historique chronologique réel d'utilisation.

Documentation : [index](docs/README.md) · [guide moteur](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [revue d'intégration](docs/10-recall-integration-review.md) · [protocole benchmark](research/recall/README.md)