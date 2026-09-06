# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者: Junfu Shi (SJF, xngg1021) · ライセンス: [MIT](LICENSE)

THM は Hermes Agent 向けのローカルファーストな4層メモリーツールです。T0 はセッション snapshot の `MEMORY.md` / `USER.md`、T1 はオンデマンドのテーマ別 Markdown、T2 は予算付き履歴検索、T3 は外部ソースへの参照です。

activity、validity、task relevance、明示的 pin を分離します。言及は hit ではなく、retrieval は有用性の証明ではなく、write も使用イベントではありません。1.2 は FTS5 sparse retrieval、任意のローカル semantic vector、RRF、budget packing、重み0の `mention_observed`、decay 比較、read-only Hermes provider を実装しています。

過去の LoCoMo protocol 1 では、600 `cl100k_base` evidence-token、完全に解決可能な非対抗問題1,532問で any-gold coverage が **literal 56.85% / sparse 69.58% / dense 51.11% / hybrid 70.04%** でした。これは回答正解率ではありません。Protocol 2 はカテゴリを修正し、会話ごとに IDF を分離し、MRR / nDCG / p99 を追加します。

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

インストール後、THM は Hermes の `hermes_agent.memory_providers` entry-point から `thm` provider として利用できます。固定 upstream を使う E2E workflow が実際の Hermes discovery と provider lifecycle を検証します。

THM は現時点で、実ユーザーの end-to-end 回答正解率、普遍的な最適 decay、自動 tier 移動/削除伝播、体感 latency 改善を証明したとは主張しません。ユーザー固有の decay 校正には実際の時系列 hit 記録が必要です。

ドキュメント: [一覧](docs/README.md) · [エンジンガイド](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
