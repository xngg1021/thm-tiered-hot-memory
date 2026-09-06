# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 授權：[MIT](LICENSE)

THM 是為 Hermes Agent 設計的本地優先四層記憶工具：T0 是會話快照中的原生 `MEMORY.md` / `USER.md`，T1 是按需主題 Markdown，T2 是受預算約束的歷史會話檢索，T3 是外部來源指標。

它把活躍度、有效性、任務相關性與明確固定分開：提及不等於 hit，檢索不等於有用，寫入也不等於使用事件。1.2 已實作 FTS5 稀疏召回、可選本地語意向量、RRF 融合、預算裝載、零權重 `mention_observed`、多種衰減策略比較與唯讀 Hermes provider。

已完成的 LoCoMo **Protocol 2** 在 600 `cl100k_base` 證據 token、1,532 道完整可解析非對抗題上，any-gold coverage 為 **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**；all-gold 為 **46.61% / 56.53% / 40.01% / 57.64%**。這不是回答正確率。Protocol 2 已修正類別標籤、按對話隔離 IDF，並增加 MRR、nDCG 與 p99。完整結果見 [Protocol 2 報告](reports/2026-09-06-recall-protocol2.md)。

```bash
python -m pip install -e .
python -m thm --help
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
```

安裝後，THM 透過 Hermes 的 `hermes_agent.memory_providers` entry-point 暴露 `thm` provider。固定上游 E2E 已驗證真實 Hermes discovery、MemoryProvider/MemoryManager 接入、prefetch、memory-context fencing、session switch，以及 `on_memory_write` 不會被計作 hit，也不會改寫衍生召回庫。該 E2E 使用合成證據且零模型呼叫，不是回答生成 benchmark。詳見 [Hermes E2E 報告](reports/2026-09-06-hermes-e2e.md)。

使用者專屬 decay 標定可用 `research/recall/decay_from_index.py` 從本地 THM v2 索引匯出只包含 entry ID、單位成本與明確 hit 日期的私有時間序列；沒有真實 hit 歷史時，THM 不宣稱存在使用者專屬最優半衰期或曲線。

THM 目前不宣稱已證明真實使用者端到端回答正確率、普適最優衰減曲線、自動換層/刪除傳播或使用者感知延遲收益。`scan` 的 `mention_observed` 權重仍為零。

文件：[專案目錄](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回 / scan / decay](docs/09-retrieval-and-measurement.md) · [benchmark](research/recall/README.md)
