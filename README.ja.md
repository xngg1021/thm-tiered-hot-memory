# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者: Junfu Shi (SJF, xngg1021) · ライセンス: [MIT](LICENSE)

THM は Hermes Agent 向けのローカルファーストな4層メモリーツールです。対象を限定し、常時コンテキストを占有すべき情報、必要時だけ読む情報、固定予算内で履歴を再取得する方法、そして「使用」を捏造せずにそれらを評価する方法を扱います。

## 4つの層

- **T0 — hot:** セッション開始時のスナップショットに注入される `MEMORY.md` / `USER.md`。
- **T1 — warm:** テーマ別の Markdown を必要時に読み込みます。
- **T2 — cold:** 明示した証拠予算の範囲で履歴セッションやアーカイブを検索します。
- **T3 — external:** 必要時に再訪する外部ソースの位置・参照です。

THM は activity、validity、現在タスクとの関連性、明示的 pin を分離します。言及は hit ではなく、取得は有用性の証明ではなく、書き込みも使用イベントではありません。

## 実装済み

1.1.1 の索引 CLI は profile 単位の索引、厳密なイベント ID、移行プレビュー、pin/unpin、失敗時に元データを守る書き込みを提供します。1.2 パッケージでは、スコープ付き FTS5 検索、任意のローカル文埋め込み、RRF 融合、予算付きコンテキスト packing、重み0の `mention_observed`、複数の減衰方針比較、読み取り専用 Hermes provider、再現可能な評価スクリプトを追加しました。

検索と scan はネイティブのメモリーファイルや Hermes `state.db` を書き換えません。派生 SQLite DB は THM テーブル作成前に無関係な DB やネイティブ DB を拒否します。

## 測定済みの証拠

過去の protocol 1 LoCoMo 実験は10会話、1,986問を使用しました。600 `cl100k_base` evidence-token、完全に解決可能な非対抗問題1,532問では any-gold coverage が **literal 56.85%**、**sparse 69.58%**、**MiniLM dense 51.11%**、**hybrid 70.04%** でした。これは証拠検索指標であり、回答正解率や競合ランキングではありません。

Protocol 2 はカテゴリ名を修正し、会話ごとに FTS5 IDF を分離し、MRR / nDCG / p99 を追加します。完全な protocol 2 はリポジトリの benchmark workflow で独立実行されます。

## インストール

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

任意の tokenizer / semantic 依存関係: `python -m pip install -e '.[tokenizer,semantic]'`。

インストール後、THM は Hermes の `hermes_agent.memory_providers` entry-point から `thm` provider として利用できます。固定した Hermes upstream checkout を使う統合 workflow が discovery と provider lifecycle を検証します。

## 証拠の境界

THM は現時点で、実ユーザーの end-to-end 回答正解率、普遍的に最適な減衰曲線、自動 tier 移動、自動削除伝播、prompt-cache や体感レイテンシの改善を証明したとは主張しません。`scan` は activity weight 0 の弱い `mention_observed` だけを記録します。ユーザー固有の減衰校正には実際の時系列使用履歴が必要です。

ドキュメント: [一覧](docs/README.md) · [エンジンガイド](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [統合レビュー](docs/10-recall-integration-review.md) · [benchmark protocol](research/recall/README.md)