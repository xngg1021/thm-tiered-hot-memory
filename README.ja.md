# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者: Junfu Shi (SJF, xngg1021) · ライセンス: [MIT](LICENSE) · 安定版: **1.3.0**

THM は agent harness 向けのローカル優先4階層メモリです。1.3 は harness-neutral な読み取り専用 recall 層として Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2 stdio、OpenClaw 2026.9.x 用の独立 legacy MCP bridge を提供します。Claude Code、Codex CLI、Gemini CLI は固定バージョンの実 CLI 設定と同一 server command lifecycle E2E で検証されます。元のメモリを書き換えず、追加のモデル呼び出しも行いません。

LoCoMo Protocol 2 は全10会話・1,986問、主分母1,532問です。600 evidence token で literal / sparse / dense / hybrid の any-gold coverage は **56.79% / 69.39% / 51.11% / 71.34%**。これは回答精度ではなく証拠検索の指標です。[完全なレポート](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

1.3.0 accepted/stable は correctness、Hermes、harness の全 matrix を通過した正確な Git SHA を指す正式 version ref のみで確定します。実ユーザー E2E 回答精度、普遍的な最適減衰、自動 tier 移動／削除伝播、体感遅延改善は未主張です。

文書: [目次](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [バージョン履歴](docs/12-version-history.md) · [変更履歴](CHANGELOG.md)
