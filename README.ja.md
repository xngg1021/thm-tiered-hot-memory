# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | 日本語 | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者: Junfu Shi (SJF, xngg1021) · ライセンス: [MIT](LICENSE)

## 4つの階層

THM は agent harness 向けのローカル優先4階層メモリです。T0 はホストが注入する永続コンテキスト、T1 はオンデマンド資料、T2 は明示的な証拠予算内で検索する履歴、T3 は再参照可能な外部ソースです。活動、有効性、タスク関連性、pin を分離し、mention・retrieval・write を有用な hit と同一視しません。

## 実装範囲

1.1.1 は堅牢な index CLI、1.2 は scope 分離 FTS5、任意のローカル embedding、RRF、予算付き packing、ゼロ重み mention observation、decay 比較、再現可能な評価を提供します。**1.3 は harness-neutral な読み取り専用 recall 層**として Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2 stdio を追加します。OpenClaw 2026.9.x、Claude Code、Codex CLI、Gemini CLI は独立した読み取り専用 MCP compatibility bridge と固定した実 CLI で検証します。元のメモリを書き換えず、追加のモデル呼び出しも行いません。

## LoCoMo 測定

Protocol 2 は全10会話・1,986問、主分母1,532問です。600 `cl100k_base` evidence token で any-gold は **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**、all-gold は **46.61% / 56.53% / 40.01% / 57.64%**。回答精度ではなく証拠検索の指標です。p95 retrieval+packing は **sparse 34.55 ms / hybrid 57.88 ms**。300/600/1200 token の sparse は **60.57/69.39/76.17%**、p95 は **20.39/34.55/61.78 ms**です。[報告](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json)。

## 統合

| Surface | THM 1.3 |
| --- | --- |
| Hermes | pip provider、setup/config、prefetch、任意 `sync_turn`、session hooks、write≠hit |
| OpenAI Agents | 読み取り専用 `OpenAIAgentsTHM.tool` |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`、型付き `thm_recall` / `thm_status` |
| OpenClaw | `thm-mcp-legacy`、実 runtime probe |
| Claude/Codex/Gemini | 固定した実 CLI、正確な command、discovery/call lifecycle、モデル呼び出しゼロ |

Hermes の旧 E2E は `NousResearch/hermes-agent@77915e...` に固定され、1.3 CI はレビュー済み現行 snapshot も検査します。根拠は常に同じ commit の workflow です。

## インストール

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras は `.[tokenizer,semantic]`、`.[openai]`、`.[langchain]`、`.[mcp]`、`.[harnesses]`。互換 bridge は `thm-mcp-legacy` です。

## Hermes lifecycle

`sync_turns` は既定で無効です。明示的に有効化すると user/assistant 文だけを session 別の派生 T2 scope に同期し、system row と compression summary は除外します。`on_memory_write` は refresh 信号であり hit ではありません。派生 cache は canonical transcript owner ではないため、THM は fail-closed checkpoint-v2 durability を主張せず pre-compress API v1 を維持します。

## Decay calibration

`decay_from_index.py` は ID、unit cost、明示的 hit 日だけを出力し、本文、summary、key、confirmation evidence を除外します。`decay_replay.py` で非公開 replay が可能です。実 hit chronology がなければ個人最適な半減期を主張しません。

## 証拠の境界

実ユーザー E2E 回答精度、普遍的な最適 decay、自動 tier 移動、削除伝播、prompt-cache／体感 latency 改善は未主張です。Coverage、host plumbing、モデルによる証拠利用、最終回答品質は独立した証拠層です。Correctness CI は Linux、macOS、Windows で実行し、LoCoMo と integration job は分離します。

[目次](docs/README.md) · [ガイド](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [履歴](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## THM 1.4 の現在の安定状態

THM 1.4 は **accepted/stable implementation milestone** として完了・凍結されています。安定コード/コンテンツのマイルストーンは `e6e4dda5835e3cb345207457d5491131c6959b2c`、復旧ポインタは `archive/v1.4.0-stable` です。T0–T3 の4層モデルは変更していません。

1.4 は既存の 1.3 harness-neutral recall に加えて、resident/hard miss と planned retrieval の明示 telemetry、厳密な locator-only T1 warm directory、avoidable-miss penalty と resident carry cost に基づく shadow T0 recommendation、境界付きの正確な 0/1 packing、実 demand の co-occurrence だけで学習する bounded prefetch、予算を自動変更しない resident-budget feedback を追加します。Hermes には既定で無効な session-frozen T1 locator snapshot もあります。

これらは 1.4 correctness、Hermes、multi-harness の受け入れ検証を通過しています。1.4 は retrieval path を変更していないため、新しい LoCoMo/Protocol 2 数値は主張しません。自動 T0–T3 移動と自動予算変更は、held-out runtime/task A/B が品質・コスト・遅延・reacquisition の改善を示すまで無効のままです。詳細は [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md)、[1.4 closeout](reports/2026-09-07-v1.4-closeout.md) を参照してください。

Version identity: **1.4.0 accepted/stable implementation milestone**.
