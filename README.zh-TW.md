# THM — Tiered Hot Memory

[English](README.md) | 簡體中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi（SJF，xngg1021）· 授權條款：[MIT](LICENSE)

THM 是面向 agent harness 的本地優先四層記憶工具。它從 Hermes Agent 起步，現已將檢索邏輯與 harness 接線分離：判斷哪些內容值得進入永久上下文，在固定預算內載入較冷的證據，並在不偽造“使用”訊號的前提下測量這些決策。

## 四個層級

- **T0——熱層：** 由宿主注入的原生永久上下文記憶。
- **T1——溫層：** 按需載入的主題材料。
- **T2——冷層：** 在明確證據預算內檢索的歷史會話和檔案。
- **T3——外部層：** 需要時可重新訪問的來源位置和引用。

THM 將活躍度、有效性、任務相關性與顯式固定分開。提及不等於 hit，檢索不證明有用，寫入也不等於使用事件。

## 已實現內容

加固後的 1.1.1 索引 CLI 維護 profile 繫結的記憶後設資料、精確事件身份、遷移預覽、pin/unpin 語義和故障安全寫入。1.2 檢索包加入按 scope 隔離的 FTS5、可選本地句向量、倒數排名融合、計入預算的上下文裝載、零權重 mention observation、多種衰減策略比較及可復現實驗指令碼。

**THM 1.3 加入 harness-neutral 只讀召回層。** 它提供獨立 Hermes `MemoryProvider`、OpenAI Agents SDK `FunctionTool`、LangChain/LangGraph `BaseRetriever` 和標準 MCP v2 stdio 服務。OpenClaw 2026.9.x、Claude Code、Codex CLI 與 Gemini CLI 透過獨立的只讀 MCP 相容橋驗證，因此不會為了舊一代客戶端削弱 MCP v2 主服務契約。參見 [Harness 適配](docs/11-harness-adapters.md)。

檢索或 scan 不會改寫原生來源記憶。Harness 介面卡以只讀方式開啟派生 THM 召回資料庫，除非顯式啟用了宿主專屬 live-session cache 重新整理。派生 SQLite 資料庫會在建立 THM 表之前拒絕無關或原生資料庫目標。

## 召回測量證據

完整 **Protocol 2** LoCoMo 實驗覆蓋全部 10 段對話和 1,986 道題。主分母包含 1,532 道證據完全解析的非對抗問題。在固定 600 個 `cl100k_base` 證據 token 下，any-gold coverage 為 **literal 56.79%、sparse 69.39%、MiniLM dense 51.11%、hybrid 71.34%**；all-gold coverage 分別為 **46.61% / 56.53% / 40.01% / 57.64%**。這些是證據檢索指標，不是回答正確率，也不是競品排行榜。

Protocol 2 修正了 LoCoMo 類別對映，每段對話使用獨立 FTS 資料庫，避免 BM25/IDF 統計跨對話洩漏，並報告 MRR、nDCG 和 p99。在 600 token 下，sparse 的 p95 檢索加裝載延遲為 **34.55 ms**，hybrid 為 **57.88 ms**。本工作負載中 hybrid 的 any-gold 比 sparse 高 **1.96 個百分點**，這是實測權衡，不是普適預設建議。完整證據：[Protocol 2 報告](reports/2026-09-06-recall-protocol2.md) · [機器可讀摘要](reports/2026-09-06-recall-protocol2-summary.json)。

Sparse 預算掃描在 300 / 600 / 1200 證據 token 下的 any-gold coverage 為 **60.57% / 69.39% / 76.17%**，p95 檢索加裝載延遲為 **20.39 / 34.55 / 61.78 ms**。

## Harness 整合介面

| 介面 | THM 1.3 整合 |
| --- | --- |
| Hermes Agent | 透過 pip 發現的獨立 `MemoryProvider`；覆蓋 setup schema/config、當前查詢預取、可選派生 `sync_turn`、session boundary hooks 與 write≠hit |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool`——單個只讀 `FunctionTool` |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp` / `python -m thm.mcp_server`，公開有型別的 `thm_recall` 與 `thm_status` 結構化輸出 |
| OpenClaw 2026.9.x | `thm-mcp-legacy` / `python -m thm.mcp_legacy_server`；真實 OpenClaw MCP probe，使用同一只讀召回核心 |
| Claude Code / Codex CLI / Gemini CLI | 固定版本真實 CLI 配置，透過只讀相容橋完成精確命令的 tool discovery/call lifecycle；零模型呼叫 |

早期針對 `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` 的 Hermes E2E 仍作為歷史證據。THM 1.3 CI 還檢查經審閱的當前 Hermes 快照和新增多 harness 介面；應檢視精確 commit 對應的 workflow/report，不能把舊結果轉移到新程式碼。

## 安裝與執行

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

可選依賴按用途拆分：

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP 示例：

```bash
# MCP v2 主服務
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600

# 固定 OpenClaw/CLI 客戶端代際使用的相容橋
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Hermes 生命週期行為

Hermes setup 可將 THM scope/mode/budget 及可選 live-turn synchronization 儲存到 profile 隔離的私有配置中。`sync_turns` 預設關閉。為 primary agent 顯式啟用後，THM 會把 user/assistant transcript 文字協調進單獨的派生 per-session T2 scope；system rows 和標記的壓縮摘要不會複製。`on_memory_write` 仍只是重新整理訊號，絕不是 hit。THM 有意停留在 Hermes best-effort pre-compress API v1，因為派生 live cache 不是 canonical transcript owner，無法誠實承諾 fail-closed checkpoint-v2 durability。

## 衰減標定

合成 decay sweep 只用於診斷。真實使用者標定可用 `research/recall/decay_from_index.py` 匯出隱私最小化時間序列，其中僅含 entry ID、單位成本和顯式 `hit` 日期，不包含記憶文字、摘要、key 或 confirmation evidence；隨後可用 `decay_replay.py` 私下回放。沒有真實按時間排序的 hit trace 時，THM 不宣稱存在使用者專屬最優半衰期或曲線。

## 證據邊界

THM 當前不宣稱真實使用者端到端回答正確率、普適最優衰減曲線、自動換層、自動刪除傳播或 prompt-cache／使用者感知延遲改善。`scan` 記錄的是活動權重為零的弱 `mention_observed` 證據。Harness 整合刻意不進行第二次模型呼叫：召回覆蓋、宿主接線、模型是否使用證據以及最終回答質量是四個獨立證據層。

常規 correctness CI 在 Linux、macOS 和 Windows 上執行。重型 LoCoMo／模型下載與 harness 整合任務相互獨立。文件：[專案目錄](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回／scan／decay](docs/09-retrieval-and-measurement.md) · [Harness 適配](docs/11-harness-adapters.md) · [版本歷史](docs/12-version-history.md) · [更新日誌](CHANGELOG.md) · [benchmark protocol](research/recall/README.md)。

相關專案：[hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills)。

## THM 1.4 目前穩定狀態

THM 1.4 已完成並凍結為 **accepted/stable implementation milestone**。穩定程式碼/內容里程碑為 `e6e4dda5835e3cb345207457d5491131c6959b2c`，恢復指標為 `archive/v1.4.0-stable`。T0–T3 四層模型保持不變。

1.4 在既有 1.3 harness-neutral 召回層之上新增：顯式 resident/hard miss 與 planned retrieval telemetry、嚴格 locator-only 的 T1 溫層目錄、基於 avoidable-miss penalty 與 resident carry cost 的 shadow T0 recommendation、精確有界 0/1 packing、只由真實 demand co-occurrence 訓練的 bounded prefetch，以及只提供建議而不自動改預算的 resident-budget feedback。Hermes 另提供預設關閉的 session-frozen T1 locator snapshot。

這些能力已通過 1.4 correctness、Hermes 與 multi-harness 驗收；1.4 沒有修改 retrieval path，因此沒有宣稱產生新的 LoCoMo/Protocol 2 數字。自動 T0–T3 換層和自動預算修改仍保持關閉，直到真實留出任務 A/B 能同時證明品質、成本、延遲和 reacquisition 改善。詳見 [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md) 與 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)。

Version identity: **1.4.0 accepted/stable implementation milestone**.

## 零生成式 LLM 檢索擴充（未發布）

明確啟用 Python API 參數 `entity_projection=True`，可用來源中的精確說話人姓名和識別符調整既有候選的排序。固定 600 tokens 的 Protocol 2 全量 any-gold 從 69.39% 提高到 72.52%；1301 道保留測試題從 69.56% 提高到 72.33%。候選覆蓋率維持不變。沒有生成式模型呼叫，也沒有使用嵌入模型；T0–T3 與原生記憶維持不變。時間、分段、關聯和大小排序實驗未進入正式執行路徑。此擴充尚未登記為 1.5 穩定版本。

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
