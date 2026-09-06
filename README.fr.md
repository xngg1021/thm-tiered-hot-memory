# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE) · Version stable : **1.3.0**

THM est une mémoire locale à quatre niveaux pour les agent harnesses. La version 1.3 ajoute une couche de recall en lecture seule et indépendante du harness : Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 sur stdio et un pont legacy MCP séparé pour OpenClaw 2026.9.x. Claude Code, Codex CLI et Gemini CLI sont vérifiés avec des versions figées de leurs CLI réels et un E2E du cycle de vie de la même commande serveur. THM ne réécrit pas la mémoire source et n'effectue aucun appel de modèle supplémentaire.

LoCoMo Protocol 2 couvre 10 conversations et 1 986 questions ; le dénominateur principal en contient 1 532. Avec 600 evidence tokens, la couverture any-gold de literal / sparse / dense / hybrid est de **56,79 % / 69,39 % / 51,11 % / 71,34 %**. Il s'agit d'une mesure de rappel des preuves, pas de l'exactitude des réponses. [Rapport complet](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Le statut 1.3.0 accepted/stable n'est confirmé que par une référence formelle pointant vers le SHA Git exact ayant réussi les matrices complètes correctness, Hermes et harness. THM ne revendique pas encore une exactitude E2E réelle, une courbe de decay universellement optimale, le déplacement ou la suppression automatique entre niveaux, ni un gain de latence perçue.

Documentation : [index](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [historique](docs/12-version-history.md) · [changements](CHANGELOG.md)
