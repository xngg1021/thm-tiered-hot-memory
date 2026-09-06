# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 授權：[MIT](LICENSE)

THM 是為 Hermes Agent 設計的本地優先四層記憶工具。它聚焦一個有限問題：哪些內容值得永久佔用上下文、哪些應按需載入、歷史材料如何在固定預算內召回，以及如何量測這些決策而不捏造「使用」訊號。

## 四層結構

- **T0 熱層：** 會話開始時注入快照的原生 `MEMORY.md` / `USER.md`。
- **T1 溫層：** 按主題組織、按需讀取的 Markdown。
- **T2 冷層：** 在明確證據預算內檢索的歷史會話與檔案。
- **T3 外部層：** 需要時重新存取的來源位置與引用。

THM 將活躍度、有效性、目前任務相關性與明確固定分開處理。提及不等於 hit，檢索不等於有用，寫入也不等於使用事件。

## 已實作

1.1.1 索引 CLI 提供 profile 綁定索引、嚴格事件身分、遷移預覽、pin/unpin 與失敗保護寫入。1.2 套件加入 FTS5 分範圍召回、可選本地句向量、RRF 融合、預算計量的上下文裝載、零權重 `mention_observed`、多種衰減策略比較、唯讀 Hermes provider 適配器與可重現實驗腳本。

召回與 scan 路徑不會改寫原生記憶檔案或 Hermes `state.db`。派生 SQLite 資料庫在建立 THM 表前會拒絕無關或原生資料庫目標。

## 已測證據

歷史 protocol 1 的 LoCoMo 實驗覆蓋 10 段對話、1,986 道題。在 600 個 `cl100k_base` 證據 token、1,532 道完整可解析非對抗題的主分母上，任一證據命中率為：**literal 56.85%**、**sparse 69.58%**、**MiniLM dense 51.11%**、**hybrid 70.04%**。這些是證據召回指標，不是回答正確率，也不是競品排行榜。

Protocol 2 修正類別標籤、按對話隔離 FTS5 IDF，並增加 MRR、nDCG 與 p99。完整 protocol 2 由倉庫 benchmark workflow 獨立執行；歷史 protocol 1 數字僅保留作舊版本證據。

## 安裝與執行

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

可選 tokenizer / semantic 依賴：`python -m pip install -e '.[tokenizer,semantic]'`。

安裝後，THM 透過 Hermes 的 `hermes_agent.memory_providers` entry-point 暴露 `thm` provider。固定上游版本的整合 workflow 會驗證真實 Hermes checkout 中的發現與 provider 生命週期。

## 證據邊界

THM 目前**不**宣稱已證明真實使用者端到端回答正確率、存在普適最優衰減曲線、能自動換層或自動傳播刪除，也不宣稱已證明 prompt-cache 或使用者感知延遲收益。`scan` 只記錄零活躍度權重的弱 `mention_observed`。使用者專屬衰減標定必須使用真實時間序列使用記錄。

文件：[專案目錄](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回 / scan / 衰減](docs/09-retrieval-and-measurement.md) · [整合複核](docs/10-recall-integration-review.md) · [benchmark 協議](research/recall/README.md)