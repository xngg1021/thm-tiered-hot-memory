# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 授權：[MIT](LICENSE)

THM 是為 Hermes Agent 設計的本地優先四層記憶工具：T0 是會話快照中的原生 `MEMORY.md` / `USER.md`，T1 是按需主題 Markdown，T2 是受預算約束的歷史會話檢索，T3 是外部來源指標。

它將活躍度、有效性、任務相關性與明確固定分開：提及不等於 hit，檢索不等於有用，寫入也不等於使用事件。1.2 已實作 FTS5 稀疏召回、可選本地語意向量、RRF 融合、預算裝載、零權重 `mention_observed`、衰減策略比較與唯讀 Hermes provider。

歷史 LoCoMo protocol 1 在 600 `cl100k_base` 證據 token、1,532 道完整可解析非對抗題上，any-gold coverage 為 **literal 56.85% / sparse 69.58% / dense 51.11% / hybrid 70.04%**。這不是回答正確率。Protocol 2 修正類別標籤、按對話隔離 IDF，並增加 MRR、nDCG 與 p99，由倉庫 workflow 獨立執行。

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

安裝後，THM 透過 Hermes 的 `hermes_agent.memory_providers` entry-point 暴露 `thm` provider。固定上游版本的 E2E workflow 驗證真實 Hermes discovery 與 provider 生命週期。

THM 目前不宣稱已證明真實使用者端到端回答正確率、普適最優衰減曲線、自動換層/刪除傳播或使用者感知延遲收益。使用者專屬 decay 標定必須使用真實時間序列 hit 記錄，不能以合成軌跡冒充。

文件：[專案目錄](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回 / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
