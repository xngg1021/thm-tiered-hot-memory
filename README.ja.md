# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者: Junfu Shi (SJF, xngg1021) · ライセンス: [MIT](LICENSE)

THM は Hermes Agent 向けのローカルファーストな4層メモリーツールです。T0 はセッション snapshot の `MEMORY.md` / `USER.md`、T1 はオンデマンドのテーマ別 Markdown、T2 は明示的な予算内で検索する履歴、T3 は外部ソースへの参照です。

activity、validity、task relevance、明示的 pin を分離します。言及は hit ではなく、retrieval は有用性の証明ではなく、write も使用イベントではありません。1.2 は FTS5 sparse retrieval、任意のローカル semantic vector、RRF、budget packing、重み0の `mention_observed`、複数の decay 比較、read-only Hermes provider を実装しています。

完了した LoCoMo **Protocol 2** では、600 `cl100k_base` evidence-token、完全に解決可能な非対抗問題1,532問で any-gold coverage が **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**、all-gold が **46.61% / 56.53% / 40.01% / 57.64%** でした。これは回答正解率ではありません。Protocol 2 はカテゴリを修正し、会話ごとに IDF を隔離し、MRR / nDCG / p99 を追加しています。詳細は [Protocol 2 report](reports/2026-09-06-recall-protocol2.md) を参照してください。

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

インストール後、THM は Hermes の `hermes_agent.memory_providers` entry-point から `thm` provider として利用できます。固定 upstream を使う E2E で、実際の Hermes discovery、MemoryProvider/MemoryManager admission、prefetch、memory-context fencing、session switch、さらに `on_memory_write` が hit にならず派生 recall DB を変更しないことを検証しました。これは合成 evidence・モデル呼び出し0回の provider-lifecycle E2E で、回答生成 benchmark ではありません。詳細は [Hermes E2E report](reports/2026-09-06-hermes-e2e.md) を参照してください。

ユーザー固有の decay 校正には、`research/recall/decay_from_index.py` でローカル THM v2 index から entry ID、unit cost、明示的 hit 日付だけを含む private trace を出力できます。実際の hit 履歴がない場合、THM はユーザー固有の最適 half-life / curve を主張しません。

THM は現時点で、実ユーザーの end-to-end 回答正解率、普遍的な最適 decay、自動 tier 移動/削除伝播、体感 latency 改善を証明したとは主張しません。`scan` の `mention_observed` は引き続き重み0です。

ドキュメント: [一覧](docs/README.md) · [エンジンガイド](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
