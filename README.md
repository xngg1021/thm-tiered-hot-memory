# THM — Tiered Hot Memory

<!-- in-page-locales:start -->

**Language / 语言 / 言語 / 언어 / Idioma / Langue / Sprache**

<details id="readme-zh-CN">
<summary><strong>简体中文</strong></summary>

<!-- locale:zh-CN:start -->
作者：Junfu Shi（SJF，xngg1021）· 许可证：[MIT](LICENSE)

THM 是面向 agent harness 的本地优先四层记忆工具。它从 Hermes Agent 起步，现已将检索逻辑与 harness 接线分离：判断哪些内容值得进入永久上下文，在固定预算内加载较冷的证据，并在不伪造“使用”信号的前提下测量这些决策。

## 四个层级

- **T0——热层：** 由宿主注入的原生永久上下文记忆。
- **T1——温层：** 按需加载的主题材料。
- **T2——冷层：** 在明确证据预算内检索的历史会话和档案。
- **T3——外部层：** 需要时可重新访问的来源位置和引用。

THM 将活跃度、有效性、任务相关性与显式固定分开。提及不等于 hit，检索不证明有用，写入也不等于使用事件。

## 已实现内容

加固后的 1.1.1 索引 CLI 维护 profile 绑定的记忆元数据、精确事件身份、迁移预览、pin/unpin 语义和故障安全写入。1.2 检索包加入按 scope 隔离的 FTS5、可选本地句向量、倒数排名融合、计入预算的上下文装载、零权重 mention observation、多种衰减策略比较及可复现实验脚本。

**THM 1.3 加入 harness-neutral 只读召回层。** 它提供独立 Hermes `MemoryProvider`、OpenAI Agents SDK `FunctionTool`、LangChain/LangGraph `BaseRetriever` 和标准 MCP v2 stdio 服务。OpenClaw 2026.9.x、Claude Code、Codex CLI 与 Gemini CLI 通过独立的只读 MCP 兼容桥验证，因此不会为了旧一代客户端削弱 MCP v2 主服务契约。参见 [Harness 适配](docs/11-harness-adapters.md)。

检索或 scan 不会改写原生来源记忆。Harness 适配器以只读方式打开派生 THM 召回数据库，除非显式启用了宿主专属 live-session cache 刷新。派生 SQLite 数据库会在创建 THM 表之前拒绝无关或原生数据库目标。

## 召回测量证据

完整 **Protocol 2** LoCoMo 实验覆盖全部 10 段对话和 1,986 道题。主分母包含 1,532 道证据完全解析的非对抗问题。在固定 600 个 `cl100k_base` 证据 token 下，any-gold coverage 为 **literal 56.79%、sparse 69.39%、MiniLM dense 51.11%、hybrid 71.34%**；all-gold coverage 分别为 **46.61% / 56.53% / 40.01% / 57.64%**。这些是证据检索指标，不是回答正确率，也不是竞品排行榜。

Protocol 2 修正了 LoCoMo 类别映射，每段对话使用独立 FTS 数据库，避免 BM25/IDF 统计跨对话泄漏，并报告 MRR、nDCG 和 p99。在 600 token 下，sparse 的 p95 检索加装载延迟为 **34.55 ms**，hybrid 为 **57.88 ms**。本工作负载中 hybrid 的 any-gold 比 sparse 高 **1.96 个百分点**，这是实测权衡，不是普适默认建议。完整证据：[Protocol 2 报告](reports/2026-09-06-recall-protocol2.md) · [机器可读摘要](reports/2026-09-06-recall-protocol2-summary.json)。

Sparse 预算扫描在 300 / 600 / 1200 证据 token 下的 any-gold coverage 为 **60.57% / 69.39% / 76.17%**，p95 检索加装载延迟为 **20.39 / 34.55 / 61.78 ms**。

## Harness 集成界面

| 界面 | THM 1.3 集成 |
| --- | --- |
| Hermes Agent | 通过 pip 发现的独立 `MemoryProvider`；覆盖 setup schema/config、当前查询预取、可选派生 `sync_turn`、session boundary hooks 与 write≠hit |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool`——单个只读 `FunctionTool` |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp` / `python -m thm.mcp_server`，公开有类型的 `thm_recall` 与 `thm_status` 结构化输出 |
| OpenClaw 2026.9.x | `thm-mcp-legacy` / `python -m thm.mcp_legacy_server`；真实 OpenClaw MCP probe，使用同一只读召回核心 |
| Claude Code / Codex CLI / Gemini CLI | 固定版本真实 CLI 配置，通过只读兼容桥完成精确命令的 tool discovery/call lifecycle；零模型调用 |

早期针对 `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` 的 Hermes E2E 仍作为历史证据。THM 1.3 CI 还检查经审阅的当前 Hermes 快照和新增多 harness 界面；应查看精确 commit 对应的 workflow/report，不能把旧结果转移到新代码。

## 安装与运行

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

可选依赖按用途拆分：

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP 示例：

```bash
# MCP v2 主服务
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600

# 固定 OpenClaw/CLI 客户端代际使用的兼容桥
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Hermes 生命周期行为

Hermes setup 可将 THM scope/mode/budget 及可选 live-turn synchronization 保存到 profile 隔离的私有配置中。`sync_turns` 默认关闭。为 primary agent 显式启用后，THM 会把 user/assistant transcript 文本协调进单独的派生 per-session T2 scope；system rows 和标记的压缩摘要不会复制。`on_memory_write` 仍只是刷新信号，绝不是 hit。THM 有意停留在 Hermes best-effort pre-compress API v1，因为派生 live cache 不是 canonical transcript owner，无法诚实承诺 fail-closed checkpoint-v2 durability。

## 衰减标定

合成 decay sweep 只用于诊断。真实用户标定可用 `research/recall/decay_from_index.py` 导出隐私最小化时间序列，其中仅含 entry ID、单位成本和显式 `hit` 日期，不包含记忆文本、摘要、key 或 confirmation evidence；随后可用 `decay_replay.py` 私下回放。没有真实按时间排序的 hit trace 时，THM 不宣称存在用户专属最优半衰期或曲线。

## 证据边界

THM 当前不宣称真实用户端到端回答正确率、普适最优衰减曲线、自动换层、自动删除传播或 prompt-cache／用户感知延迟改善。`scan` 记录的是活动权重为零的弱 `mention_observed` 证据。Harness 集成刻意不进行第二次模型调用：召回覆盖、宿主接线、模型是否使用证据以及最终回答质量是四个独立证据层。

常规 correctness CI 在 Linux、macOS 和 Windows 上运行。重型 LoCoMo／模型下载与 harness 集成任务相互独立。文档：[项目目录](docs/README.md) · [引擎指南](docs/06-engine-guide.md) · [召回／scan／decay](docs/09-retrieval-and-measurement.md) · [Harness 适配](docs/11-harness-adapters.md) · [版本历史](docs/12-version-history.md) · [更新日志](CHANGELOG.md) · [benchmark protocol](research/recall/README.md)。

相关项目：[hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills)。

## THM 1.4 当前稳定状态

THM 1.4 已完成并冻结为 **accepted/stable implementation milestone**。稳定代码/内容里程碑为 `e6e4dda5835e3cb345207457d5491131c6959b2c`，恢复指针为 `archive/v1.4.0-stable`。T0–T3 四层模型保持不变。

1.4 在既有 1.3 harness-neutral 召回层之上新增：显式 resident/hard miss 与 planned retrieval telemetry、严格 locator-only 的 T1 温层目录、基于 avoidable-miss penalty 与 resident carry cost 的 shadow T0 recommendation、精确有界 0/1 packing、只由真实 demand co-occurrence 训练的 bounded prefetch、以及只给出建议而不自动改预算的 resident-budget feedback。Hermes 另提供默认关闭的 session-frozen T1 locator snapshot。

这些能力已经通过 1.4 的 correctness、Hermes 与 multi-harness 验收；1.4 没有修改 retrieval path，因此没有冒充产生新的 LoCoMo/Protocol 2 数字。自动 T0–T3 换层和自动预算修改仍保持关闭，直到真实留出任务 A/B 能同时证明质量、成本、延迟和 reacquisition 改善。详见 [1.4 control plane](docs/14-residency-control-plane.md)、[Hermes T1 directory](docs/15-hermes-warm-directory.md) 与 [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)。

Version identity: **1.4.0 accepted/stable implementation milestone**.

## 零生成式 LLM 检索扩展（未发布）

显式启用 Python API 参数 `entity_projection=True`，可用来源中的精确说话人姓名和标识符调整已有候选的排序。固定 600 tokens 的 Protocol 2 全量 any-gold 从 69.39% 提高到 72.52%；1301 道留出题从 69.56% 提高到 72.33%。候选覆盖率保持不变。没有生成式模型调用，也没有使用嵌入模型；T0–T3 与原生记忆保持不变。时间、分段、关联和大小排序实验未进入生产路径。此扩展尚未登记为 1.5 稳定版本。

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:zh-CN:end -->

</details>

<details id="readme-zh-TW">
<summary><strong>繁體中文</strong></summary>

<!-- locale:zh-TW:start -->
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
<!-- locale:zh-TW:end -->

</details>

<details id="readme-ja">
<summary><strong>日本語</strong></summary>

<!-- locale:ja:start -->
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

## 生成 LLM 呼び出しゼロの検索拡張（未リリース）

Python API の `entity_projection=True` を明示すると、出典の正確な話者名と識別子で既存候補を並べ替えます。600 tokens の Protocol 2 全体 any-gold は 69.39% から 72.52%、留保した1301問は 69.56% から 72.33% になりました。候補カバレッジは不変です。生成モデル呼び出しも埋め込みモデル使用もなく、T0–T3 と元の記憶は変わりません。時間・分割・関連展開・サイズ順位の実験は本番経路に入りません。1.5 安定版としてはまだ登録していません。

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:ja:end -->

</details>

<details id="readme-ko">
<summary><strong>한국어</strong></summary>

<!-- locale:ko:start -->
작성자: Junfu Shi (SJF, xngg1021) · 라이선스: [MIT](LICENSE)

## 4개 계층

THM은 agent harness용 로컬 우선 4계층 메모리입니다. T0는 호스트가 주입한 영구 컨텍스트, T1은 필요할 때 읽는 주제 자료, T2는 명시적 증거 예산으로 검색하는 기록, T3는 다시 방문할 수 있는 외부 소스입니다. 활동성, 유효성, 작업 관련성, pin을 분리하며 mention·retrieval·write를 유용한 hit로 간주하지 않습니다.

## 구현 범위

1.1.1은 강화된 index CLI를, 1.2는 scope 분리 FTS5, 선택적 로컬 embedding, RRF, 예산 기반 packing, 가중치 0 mention observation, decay 비교와 재현 가능한 평가를 제공합니다. **1.3은 harness-neutral 읽기 전용 recall 계층**으로 Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever`, MCP v2 stdio를 추가합니다. OpenClaw 2026.9.x, Claude Code, Codex CLI, Gemini CLI는 별도 읽기 전용 MCP compatibility bridge와 고정된 실제 CLI로 검증합니다. 원본 메모리를 수정하거나 모델을 추가 호출하지 않습니다.

## LoCoMo 측정

Protocol 2는 10개 대화와 1,986개 질문 전체, 주 분모 1,532개 질문을 사용합니다. 600 `cl100k_base` evidence token에서 any-gold는 **literal 56.79% / sparse 69.39% / dense 51.11% / hybrid 71.34%**, all-gold는 **46.61% / 56.53% / 40.01% / 57.64%**입니다. 답변 정확도가 아닌 증거 검색 지표입니다. p95 retrieval+packing은 **sparse 34.55 ms / hybrid 57.88 ms**입니다. 300/600/1200 token sparse 결과는 **60.57/69.39/76.17%**, p95는 **20.39/34.55/61.78 ms**입니다. [보고서](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## 통합

| Surface | THM 1.3 |
| --- | --- |
| Hermes | pip provider, setup/config, prefetch, 선택적 `sync_turn`, session hooks, write≠hit |
| OpenAI Agents | 읽기 전용 `OpenAIAgentsTHM.tool` |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, typed `thm_recall` / `thm_status` |
| OpenClaw | `thm-mcp-legacy`, 실제 runtime probe |
| Claude/Codex/Gemini | 고정 실제 CLI, 정확한 command, discovery/call lifecycle, 모델 호출 0 |

이전 Hermes E2E는 `NousResearch/hermes-agent@77915e...`에 고정되며 1.3 CI는 검토된 최신 snapshot도 검사합니다. 근거는 항상 같은 commit의 workflow입니다.

## 설치

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras는 `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`이며 compatibility bridge는 `thm-mcp-legacy`입니다.

## Hermes lifecycle

`sync_turns`는 기본 비활성입니다. 명시적으로 활성화하면 user/assistant 텍스트만 session별 파생 T2 scope에 동기화하고 system row와 compression summary는 제외합니다. `on_memory_write`는 refresh 신호이며 hit가 아닙니다. 파생 cache는 canonical transcript owner가 아니므로 THM은 fail-closed checkpoint-v2 durability를 주장하지 않고 pre-compress API v1을 유지합니다.

## Decay calibration

`decay_from_index.py`는 ID, unit cost, 명시적 hit 날짜만 내보내고 본문, summary, key, confirmation evidence를 제외합니다. `decay_replay.py`로 비공개 replay할 수 있습니다. 실제 hit chronology 없이는 개인 최적 half-life를 주장하지 않습니다.

## 증거 경계

실제 사용자 E2E 답변 정확도, 보편적 최적 decay, 자동 tier 이동, 삭제 전파, prompt-cache 또는 체감 latency 개선은 주장하지 않습니다. Coverage, host plumbing, 모델의 증거 사용, 최종 답변 품질은 독립된 증거 계층입니다. Correctness CI는 Linux, macOS, Windows에서 실행하며 LoCoMo와 integration job은 분리합니다.

[목차](docs/README.md) · [가이드](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [버전 기록](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## THM 1.4 현재 안정 상태

THM 1.4는 **accepted/stable implementation milestone**로 완료되어 고정되었습니다. 안정 코드/콘텐츠 마일스톤은 `e6e4dda5835e3cb345207457d5491131c6959b2c`, 복구 포인터는 `archive/v1.4.0-stable`입니다. T0–T3 4계층 모델은 그대로 유지됩니다.

1.4는 기존 1.3 harness-neutral recall 위에 명시적 resident/hard miss 및 planned retrieval telemetry, 엄격한 locator-only T1 warm directory, avoidable-miss penalty와 resident carry cost 기반 shadow T0 recommendation, 경계가 있는 정확한 0/1 packing, 실제 demand co-occurrence만 학습하는 bounded prefetch, 예산을 자동 변경하지 않는 resident-budget feedback을 추가합니다. Hermes에는 기본 비활성화된 session-frozen T1 locator snapshot도 있습니다.

이 기능들은 1.4 correctness, Hermes, multi-harness 승인 검증을 통과했습니다. 1.4는 retrieval path를 변경하지 않았으므로 새로운 LoCoMo/Protocol 2 수치를 주장하지 않습니다. 자동 T0–T3 이동과 자동 예산 변경은 held-out runtime/task A/B가 품질·비용·지연·reacquisition 개선을 입증할 때까지 비활성화 상태입니다. 자세한 내용은 [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md), [1.4 closeout](reports/2026-09-07-v1.4-closeout.md)을 참조하십시오.

Version identity: **1.4.0 accepted/stable implementation milestone**.

## 생성형 LLM 호출 없는 검색 확장（미출시）

Python API에서 `entity_projection=True`를 명시하면 출처의 정확한 화자 이름과 식별자로 기존 후보 순서를 조정합니다. 600 tokens Protocol 2 전체 any-gold는 69.39%에서 72.52%, 별도 보류한 1301문항은 69.56%에서 72.33%로 증가했습니다. 후보 커버리지는 동일합니다. 생성 모델 호출과 임베딩 모델 사용이 없으며 T0–T3와 원본 메모리는 유지됩니다. 시간·분할·연관 확장·크기 순위 실험은 운영 경로에 포함하지 않습니다. 1.5 안정 버전으로 아직 등록하지 않았습니다.

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:ko:end -->

</details>

<details id="readme-es">
<summary><strong>Español</strong></summary>

<!-- locale:es:start -->
Autor: Junfu Shi (SJF, xngg1021) · Licencia: [MIT](LICENSE)

THM es un sistema de memoria local de cuatro niveles para agent harnesses. Nació para Hermes Agent y ahora separa la recuperación de la conexión con cada harness: decide qué merece contexto permanente, carga evidencia fría bajo un presupuesto fijo y mide el resultado sin fabricar señales de «uso».

## Cuatro niveles

- **T0, caliente:** memoria permanente nativa inyectada por el host.
- **T1, templado:** material temático cargado cuando se necesita.
- **T2, frío:** sesiones históricas y archivos buscados con un presupuesto explícito.
- **T3, externo:** ubicaciones y referencias que pueden revisitarse.

THM separa actividad, validez, relevancia para la tarea y fijación explícita. Una mención no es un hit; recuperar no demuestra utilidad; escribir no equivale a usar.

## Qué está implementado

El CLI 1.1.1 mantiene metadatos ligados al perfil, identidades exactas de eventos, vista previa de migración, pin/unpin y escrituras resistentes a fallos. La versión 1.2 añade FTS5 por scope, embeddings locales opcionales, RRF, empaquetado con presupuesto, observaciones de mención con peso cero, comparación de políticas de decay y evaluación reproducible.

**THM 1.3 añade una capa de recall de solo lectura e independiente del harness:** Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` y servidor MCP v2 stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI y Gemini CLI se validan mediante un puente MCP de compatibilidad separado y de solo lectura, sin debilitar el contrato MCP v2 principal. Véase [adaptadores](docs/11-harness-adapters.md).

Recall y scan no reescriben la memoria fuente. Los adaptadores abren las bases derivadas en modo de solo lectura, salvo la actualización explícita de una caché de sesión del host. Antes de crear tablas, THM rechaza bases SQLite nativas o ajenas.

## Evidencia medida de recuperación

Protocol 2 procesó las 10 conversaciones y 1.986 preguntas de LoCoMo. El denominador principal contiene 1.532 preguntas no adversariales con evidencia completamente resuelta. Con 600 tokens `cl100k_base`, la cobertura any-gold fue **56,79 % literal, 69,39 % sparse, 51,11 % MiniLM dense y 71,34 % hybrid**; all-gold fue **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Son métricas de recuperación de evidencia, no exactitud de respuestas ni un ranking competitivo.

Protocol 2 corrige las categorías, usa una base FTS por conversación para impedir fugas BM25/IDF y publica MRR, nDCG y p99. Con 600 tokens, la latencia p95 de recuperación+packing fue **34,55 ms sparse** y **57,88 ms hybrid**. Hybrid ganó **1,96 puntos porcentuales** de any-gold en esta carga; es un trade-off medido, no una recomendación universal. [Informe](reports/2026-09-06-recall-protocol2.md) · [resumen JSON](reports/2026-09-06-recall-protocol2-summary.json).

El barrido sparse de 300 / 600 / 1200 tokens obtuvo **60,57 % / 69,39 % / 76,17 %** any-gold y latencias p95 de **20,39 / 34,55 / 61,78 ms**.

## Superficies de integración

| Superficie | Integración THM 1.3 |
| --- | --- |
| Hermes Agent | `MemoryProvider` descubierto por pip; setup/config, prefetch, `sync_turn` opcional, límites de sesión y write≠hit |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool`, un `FunctionTool` de solo lectura |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp`; salidas tipadas `thm_recall` y `thm_status` |
| OpenClaw 2026.9.x | `thm-mcp-legacy`; prueba MCP real sobre el mismo núcleo |
| Claude Code / Codex CLI / Gemini CLI | CLI reales fijados, comando exacto, discovery/call lifecycle y cero llamadas de modelo |

La E2E histórica de Hermes sigue fijada a `NousResearch/hermes-agent@77915e...`; CI 1.3 también prueba un snapshot actual revisado. La autoridad es siempre el workflow del commit exacto.

## Instalación y uso

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Extras: `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]` y `.[harnesses]`.

```bash
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Ciclo de vida de Hermes

Setup guarda scope/mode/budget y la sincronización opcional en configuración privada por perfil. `sync_turns` está desactivado por defecto. Si se activa, concilia texto user/assistant en un scope T2 derivado por sesión; excluye filas system y resúmenes de compresión. `on_memory_write` solo refresca y nunca cuenta como hit. THM permanece en pre-compress API v1 porque la caché derivada no es propietaria del transcript canónico y no puede prometer durabilidad fail-closed de checkpoint v2.

## Calibración del decay

Los barridos sintéticos son diagnósticos. `decay_from_index.py` exporta una cronología minimizada con IDs, costes y fechas de hit, sin texto, resúmenes, claves ni evidencia de confirmación; `decay_replay.py` la reproduce en privado. Sin una traza real no se afirma una curva o semivida óptima personal.

## Límites de la evidencia

THM no afirma exactitud E2E real, decay universalmente óptimo, movimiento automático entre niveles, propagación automática de borrado ni mejora de prompt-cache o latencia percibida. `scan` registra `mention_observed` débil con peso cero. Cobertura, plumbing, uso de evidencia por el modelo y calidad final son capas separadas.

Correctness CI corre en Linux, macOS y Windows; LoCoMo/modelos y las integraciones son trabajos separados. [Índice](docs/README.md) · [guía](docs/06-engine-guide.md) · [recall](docs/09-retrieval-and-measurement.md) · [adaptadores](docs/11-harness-adapters.md) · [versiones](docs/12-version-history.md) · [cambios](CHANGELOG.md).

Proyecto relacionado: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).

## Estado estable actual de THM 1.4

THM 1.4 está terminado y congelado como **accepted/stable implementation milestone**. El hito estable de código/contenido es `e6e4dda5835e3cb345207457d5491131c6959b2c` y el puntero de recuperación es `archive/v1.4.0-stable`. El modelo de cuatro niveles T0–T3 no cambia.

Sobre la capa de recall harness-neutral de 1.3, 1.4 añade telemetry explícita de resident/hard miss y planned retrieval, un directorio T1 estrictamente locator-only, recomendación shadow de T0 basada en avoidable-miss penalty frente a resident carry cost, packing 0/1 exacto y acotado, prefetch acotado entrenado sólo por co-occurrence de demanda real y feedback de resident budget que nunca modifica el presupuesto automáticamente. Hermes también dispone de un T1 locator snapshot session-frozen y desactivado por defecto.

Estas superficies superaron la aceptación correctness, Hermes y multi-harness de 1.4. Como 1.4 no cambió el retrieval path, no se atribuyen nuevos números LoCoMo/Protocol 2. El movimiento automático T0–T3 y el cambio automático de presupuesto siguen desactivados hasta que A/B held-out de runtime/tareas demuestre mejoras conjuntas de calidad, coste, latencia y reacquisition. Véanse [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) y [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.

## Extensión sin llamadas a LLM generativos (sin publicar)

La opción explícita de Python `entity_projection=True` reordena candidatos existentes mediante nombres exactos de hablantes e identificadores de las fuentes. A 600 tokens, Protocol 2 pasa de 69.39% a 72.52% any-gold global; las 1301 preguntas reservadas pasan de 69.56% a 72.33%. La cobertura de candidatos no cambia. No se usan llamadas generativas ni embeddings; T0–T3 y la memoria nativa se conservan. Los experimentos temporales, de segmentos, asociaciones y ordenación por tamaño no entran en producción. Todavía no es una versión 1.5 estable.

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:es:end -->

</details>

<details id="readme-fr">
<summary><strong>Français</strong></summary>

<!-- locale:fr:start -->
Auteur : Junfu Shi (SJF, xngg1021) · Licence : [MIT](LICENSE)

## Quatre niveaux

THM est une mémoire locale à quatre niveaux pour les agent harnesses : T0 contexte permanent natif, T1 dossiers thématiques à la demande, T2 historique recherché sous budget explicite, T3 références externes revisitées au besoin. Activité, validité, pertinence et pin sont distincts : mention, retrieval et write ne prouvent pas un hit utile.

## Fonctionnalités

1.1.1 fournit un index CLI robuste ; 1.2 ajoute FTS5 par scope, embeddings locaux facultatifs, RRF, packing budgété, observations de poids nul, comparaisons de decay et évaluations reproductibles. **1.3 ajoute une couche de recall en lecture seule et indépendante du harness** : Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` et MCP v2 stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI et Gemini CLI utilisent un pont MCP séparé en lecture seule, testé avec des versions réelles figées. Les sources natives ne sont jamais réécrites et aucun appel modèle supplémentaire n'est effectué.

## Mesures LoCoMo

Protocol 2 couvre 10 conversations, 1 986 questions et un dénominateur principal de 1 532 questions. À 600 tokens, any-gold vaut **56,79 % literal / 69,39 % sparse / 51,11 % dense / 71,34 % hybrid** ; all-gold vaut **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Ce sont des métriques de preuve, pas d'exactitude des réponses. Le p95 retrieval+packing est **34,55 ms sparse / 57,88 ms hybrid**. À 300/600/1200 tokens, sparse atteint **60,57/69,39/76,17 %** avec **20,39/34,55/61,78 ms**. [Rapport](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## Intégrations

| Surface | THM 1.3 |
| --- | --- |
| Hermes | provider pip, setup/config, prefetch, `sync_turn` optionnel, session hooks, write≠hit |
| OpenAI Agents | `OpenAIAgentsTHM.tool` en lecture seule |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, `thm_recall` et `thm_status` typés |
| OpenClaw | `thm-mcp-legacy`, probe réel |
| Claude/Codex/Gemini | CLI réels figés, commande exacte, discovery/call lifecycle, zéro appel modèle |

## Installation

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras : `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`. Le pont compatible est `thm-mcp-legacy`.

## Cycle Hermes

`sync_turns` est désactivé par défaut. Activé explicitement, il copie seulement les textes user/assistant vers un scope T2 dérivé par session ; lignes system et résumés de compression sont exclus. `on_memory_write` reste un signal de refresh. THM conserve pre-compress API v1 car la cache dérivée n'est pas propriétaire du transcript canonique et ne peut promettre checkpoint-v2 fail-closed.

## Calibration du decay

`decay_from_index.py` exporte uniquement IDs, coûts et dates de hit, sans texte, résumés, clés ni confirmations ; `decay_replay.py` rejoue cette trace en privé. Sans trace réelle, aucune demi-vie optimale personnelle n'est revendiquée.

## Limites de preuve

THM ne revendique pas encore exactitude E2E réelle, decay universellement optimal, déplacement automatique de niveaux, propagation de suppression, gain de prompt-cache ou latence perçue. Coverage, plumbing, usage de la preuve et qualité finale restent quatre couches distinctes. Correctness CI couvre Linux, macOS et Windows ; LoCoMo et les intégrations sont séparés.

[Index](docs/README.md) · [Guide](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [Versions](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## État stable actuel de THM 1.4

THM 1.4 est terminé et figé comme **accepted/stable implementation milestone**. Le jalon stable code/contenu est `e6e4dda5835e3cb345207457d5491131c6959b2c` et le pointeur de restauration est `archive/v1.4.0-stable`. Le modèle à quatre niveaux T0–T3 reste inchangé.

Au-dessus du recall harness-neutral de 1.3, la 1.4 ajoute une telemetry explicite resident/hard miss et planned retrieval, un répertoire T1 strictement locator-only, une recommandation shadow T0 fondée sur avoidable-miss penalty face au resident carry cost, un packing 0/1 exact et borné, un prefetch borné entraîné uniquement par la co-occurrence de demande réelle, et un resident-budget feedback qui ne modifie jamais automatiquement le budget. Hermes dispose aussi d'un T1 locator snapshot session-frozen, désactivé par défaut.

Ces surfaces ont passé l'acceptation correctness, Hermes et multi-harness de la 1.4. La 1.4 n'ayant pas modifié le retrieval path, aucun nouveau chiffre LoCoMo/Protocol 2 n'est revendiqué. Le mouvement automatique T0–T3 et la modification automatique du budget restent désactivés jusqu'à ce qu'un A/B held-out runtime/tâches démontre simultanément des gains de qualité, coût, latence et reacquisition. Voir [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) et [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.

## Extension sans appel à un LLM génératif (non publiée)

L’option Python explicite `entity_projection=True` réordonne les candidats existants selon les noms exacts des locuteurs et les identifiants des sources. À 600 tokens, Protocol 2 passe de 69.39% à 72.52% any-gold global ; les 1301 questions réservées passent de 69.56% à 72.33%. La couverture des candidats reste identique. Aucun appel génératif ni modèle d’embedding ; T0–T3 et la mémoire native restent inchangés. Les expériences temporelles, de segmentation, d’association et de classement par taille ne sont pas intégrées en production. Aucune version stable 1.5 n’est encore enregistrée.

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:fr:end -->

</details>

<details id="readme-de">
<summary><strong>Deutsch</strong></summary>

<!-- locale:de:start -->
Autor: Junfu Shi (SJF, xngg1021) · Lizenz: [MIT](LICENSE)

## Vier Ebenen

THM ist ein lokales Vier-Ebenen-Gedächtnis für Agent-Harnesses: T0 nativer permanenter Kontext, T1 thematisches Material auf Abruf, T2 budgetierte Suche in Historie und Archiven, T3 erneut abrufbare externe Quellen. Aktivität, Gültigkeit, Aufgabenrelevanz und Pinning bleiben getrennt; Erwähnung, Retrieval und Write beweisen keinen nützlichen Hit.

## Implementierter Umfang

1.1.1 liefert eine robuste Index-CLI; 1.2 ergänzt scope-getrenntes FTS5, optionale lokale Embeddings, RRF, budgetiertes Packing, gewichtungsfreie Mention-Observations, Decay-Vergleiche und reproduzierbare Evaluation. **1.3 ergänzt eine harness-neutrale Read-only-Recall-Schicht**: Hermes `MemoryProvider`, OpenAI Agents `FunctionTool`, LangChain/LangGraph `BaseRetriever` und MCP-v2-stdio. OpenClaw 2026.9.x, Claude Code, Codex CLI und Gemini CLI verwenden eine getrennte, schreibgeschützte MCP-Kompatibilitätsbrücke und werden mit fixierten echten CLI-Versionen geprüft. Native Quellen werden nicht umgeschrieben; zusätzliche Modellaufrufe gibt es nicht.

## LoCoMo-Messwerte

Protocol 2 umfasst 10 Gespräche, 1.986 Fragen und 1.532 vollständig aufgelöste nicht-adversariale Fragen im Hauptnenner. Bei 600 Tokens beträgt any-gold **56,79 % literal / 69,39 % sparse / 51,11 % dense / 71,34 % hybrid**, all-gold **46,61 % / 56,53 % / 40,01 % / 57,64 %**. Dies misst Evidenz-Retrieval, nicht Antwortgenauigkeit. p95 Retrieval+Packing: **34,55 ms sparse / 57,88 ms hybrid**. Sparse erreicht bei 300/600/1200 Tokens **60,57/69,39/76,17 %** bei **20,39/34,55/61,78 ms**. [Bericht](reports/2026-09-06-recall-protocol2.md) · [JSON](reports/2026-09-06-recall-protocol2-summary.json).

## Integrationen

| Oberfläche | THM 1.3 |
| --- | --- |
| Hermes | pip-Provider, Setup/Config, Prefetch, optionales `sync_turn`, Session Hooks, write≠hit |
| OpenAI Agents | schreibgeschütztes `OpenAIAgentsTHM.tool` |
| LangChain/LangGraph | `THMLangChainRetriever` |
| MCP v2 | `thm-mcp`, typisierte `thm_recall`/`thm_status` |
| OpenClaw | `thm-mcp-legacy`, echter Probe |
| Claude/Codex/Gemini | echte fixierte CLIs, exakter Befehl, Discovery/Call-Lifecycle, null Modellaufrufe |

## Installation

```bash
python -m pip install -e .
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

Extras: `.[tokenizer,semantic]`, `.[openai]`, `.[langchain]`, `.[mcp]`, `.[harnesses]`. Die Kompatibilitätsbrücke heißt `thm-mcp-legacy`.

## Hermes-Lifecycle

`sync_turns` ist standardmäßig aus. Explizit aktiviert übernimmt es nur User/Assistant-Text in einen abgeleiteten T2-Session-Scope; Systemzeilen und Kompressionszusammenfassungen bleiben draußen. `on_memory_write` ist nur Refresh. THM bleibt bei pre-compress API v1, da der Cache nicht Eigentümer des kanonischen Transkripts ist und keine fail-closed Checkpoint-v2-Dauerhaftigkeit versprechen kann.

## Decay-Kalibrierung

`decay_from_index.py` exportiert nur IDs, Kosten und Hit-Daten, ohne Texte, Zusammenfassungen, Keys oder Bestätigungen; `decay_replay.py` spielt privat nach. Ohne reale Chronologie wird keine persönliche optimale Halbwertszeit behauptet.

## Evidenzgrenzen

THM behauptet derzeit keine reale E2E-Antwortgenauigkeit, universell optimale Decay-Kurve, automatische Ebenenbewegung/Löschweitergabe oder Verbesserung von Prompt-Cache und wahrgenommener Latenz. Coverage, Plumbing, Modellnutzung und Endqualität sind getrennte Evidenzschichten. Correctness CI läuft unter Linux, macOS und Windows; LoCoMo und Integrationstests sind separat.

[Index](docs/README.md) · [Guide](docs/06-engine-guide.md) · [Recall](docs/09-retrieval-and-measurement.md) · [Harness](docs/11-harness-adapters.md) · [Versionen](docs/12-version-history.md) · [Changelog](CHANGELOG.md)

## Aktueller stabiler Stand von THM 1.4

THM 1.4 ist als **accepted/stable implementation milestone** abgeschlossen und eingefroren. Der stabile Code-/Content-Meilenstein ist `e6e4dda5835e3cb345207457d5491131c6959b2c`, der Recovery-Pointer `archive/v1.4.0-stable`. Das Vier-Stufen-Modell T0–T3 bleibt unverändert.

Auf der harness-neutralen Recall-Schicht von 1.3 ergänzt 1.4 explizite resident/hard-miss- und planned-retrieval-Telemetrie, ein strikt locator-only T1-Warmverzeichnis, eine Shadow-T0-Empfehlung aus avoidable-miss penalty gegenüber resident carry cost, exaktes begrenztes 0/1-Packing, begrenztes Prefetching, das nur aus echter Demand-Co-Occurrence lernt, sowie resident-budget feedback ohne automatische Budgetänderung. Hermes erhält zusätzlich einen standardmäßig deaktivierten session-frozen T1 locator snapshot.

Diese Oberflächen haben die 1.4-Akzeptanz für correctness, Hermes und multi-harness bestanden. Da 1.4 den retrieval path nicht geändert hat, werden keine neuen LoCoMo/Protocol-2-Zahlen beansprucht. Automatische T0–T3-Bewegung und automatische Budgetänderung bleiben deaktiviert, bis held-out Runtime-/Task-A/B gemeinsam Verbesserungen bei Qualität, Kosten, Latenz und Reacquisition nachweist. Siehe [1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md) und [1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.

## Retrieval-Erweiterung ohne generative LLM-Aufrufe (unveröffentlicht)

Die explizite Python-Option `entity_projection=True` ordnet vorhandene Kandidaten anhand exakter Sprechernamen und Quellbezeichner neu. Bei 600 tokens steigt Protocol 2 global von 69.39% auf 72.52% any-gold; die 1301 zurückgehaltenen Fragen steigen von 69.56% auf 72.33%. Die Kandidatenabdeckung bleibt gleich. Es gibt keine generativen Aufrufe und kein Embedding-Modell; T0–T3 und native Erinnerungen bleiben unverändert. Zeit-, Segment-, Assoziations- und Größenranking-Experimente gelangen nicht in den Produktionspfad. Version 1.5 ist noch nicht als stabil registriert.

[Protocol 2 / evidence](docs/16-zero-llm-retrieval-frontier.md)
<!-- locale:de:end -->

</details>

<!-- in-page-locales:end -->
Author: Junfu Shi (SJF, xngg1021) · License: [MIT](LICENSE)

THM is a local-first, four-tier memory toolkit for agent harnesses. It started from Hermes Agent and now keeps retrieval logic independent from harness plumbing: decide what deserves permanent context, load colder evidence under a fixed budget, and measure those decisions without fabricating “usage” signals.

## Four tiers

- **T0 — hot:** native permanent-context memory injected by the host.
- **T1 — warm:** thematic material loaded on demand.
- **T2 — cold:** historical sessions and archives searched under an explicit evidence budget.
- **T3 — external:** source locations and references that can be revisited when needed.

THM separates activity, validity, task relevance and explicit pinning. A mention is not a hit; retrieval is not proof of usefulness; a write is not a use event.

## What is implemented

The hardened 1.1.1 index CLI maintains profile-bound memory metadata, exact event identities, migration previews, pin/unpin semantics and failure-safe writes. The 1.2 retrieval package adds scoped FTS5 retrieval, optional local sentence embeddings, reciprocal-rank fusion, budget-counted context packing, zero-weight mention observations, multiple decay-policy comparisons and reproducible evaluation scripts.

**THM 1.3 adds a harness-neutral read-only recall layer.** It provides a standalone Hermes `MemoryProvider`, an OpenAI Agents SDK `FunctionTool`, a LangChain/LangGraph `BaseRetriever`, and a standard MCP v2 stdio server. Current OpenClaw 2026.9.x is tested through a separate read-only legacy MCP compatibility bridge, so THM does not weaken the MCP v2 server contract merely to support an older client generation. See [Harness adapters](docs/11-harness-adapters.md).

Native source memory is not rewritten by retrieval or scan. Harness adapters open derived THM recall databases read-only unless an explicitly enabled host-specific live-session cache is being refreshed. Derived SQLite databases reject unrelated/native database targets before THM tables are created.

## Measured retrieval evidence

A completed **Protocol 2** LoCoMo run used all 10 conversations and 1,986 questions. The principal denominator contains 1,532 fully resolved, non-adversarial questions. At a fixed 600 `cl100k_base` evidence-token slice, any-gold coverage was **56.79% literal**, **69.39% sparse**, **51.11% MiniLM dense**, and **71.34% hybrid**. All-gold coverage was **46.61% / 56.53% / 40.01% / 57.64%** respectively. These are evidence-retrieval metrics, not answer accuracy and not a competitor leaderboard.

Protocol 2 corrects the LoCoMo category mapping, uses one FTS database per conversation so BM25/IDF statistics cannot leak across conversations, and reports MRR, nDCG and p99. At 600 tokens, sparse p95 retrieval+packing latency was **34.55 ms** and hybrid was **57.88 ms**. Hybrid gained **1.96 percentage points** of any-gold coverage over sparse in this workload; this is a measured tradeoff, not a universal default recommendation. Full evidence: [Protocol 2 report](reports/2026-09-06-recall-protocol2.md) · [machine-readable summary](reports/2026-09-06-recall-protocol2-summary.json).

The sparse budget sweep reached **60.57% / 69.39% / 76.17%** any-gold coverage at 300 / 600 / 1200 evidence tokens, with p95 retrieval+packing latency **20.39 / 34.55 / 61.78 ms**.

## Harness integration surfaces

| Surface | THM 1.3 integration |
| --- | --- |
| Hermes Agent | pip-discovered standalone `MemoryProvider`; setup schema/config, current-query prefetch, optional derived `sync_turn`, session boundary hooks and write≠hit semantics |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool` — one read-only `FunctionTool` |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` |
| MCP v2 | `thm-mcp` / `python -m thm.mcp_server` exposes typed `thm_recall` and `thm_status` structured outputs |
| OpenClaw 2026.9.x | `thm-mcp-legacy` / `python -m thm.mcp_legacy_server`; live OpenClaw MCP probe, same read-only THM recall core |
| Claude Code / Codex CLI / Gemini CLI | pinned real CLI configuration through the read-only compatibility bridge plus exact-command tool discovery/call lifecycle; zero model calls |

The earlier Hermes E2E against `NousResearch/hermes-agent@77915e344cb0cd8e20661d4a7b393f987a2eef32` remains historical evidence. THM 1.3 CI additionally checks a reviewed current Hermes snapshot and the new multi-harness surfaces; use the exact workflow/commit reports rather than transferring an older result to newer code.

## Install and run

```bash
python -m pip install -e .
python -m thm --help
python -m thm import-files ./notes --db ./state/recall.sqlite3 --scope demo
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
python -m thm curves
```

Optional dependencies are split by function:

```bash
python -m pip install -e '.[tokenizer,semantic]'
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[harnesses]'
```

MCP examples:

```bash
# Primary MCP v2 server
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600

# Compatibility bridge for the pinned OpenClaw 2026.9.x client generation
thm-mcp-legacy --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

## Hermes lifecycle behavior

Hermes setup can save THM scope/mode/budget and optional live-turn synchronization to a profile-scoped private config. `sync_turns` is **off by default**. When explicitly enabled for a primary agent, THM reconciles user/assistant transcript text into a separate derived per-session T2 scope; system rows and marked compression summaries are not copied. `on_memory_write` remains a refresh signal, never a hit. THM deliberately stays on Hermes' best-effort pre-compress API v1 because the derived live cache is not the canonical transcript owner and therefore cannot truthfully promise fail-closed checkpoint-v2 durability.

## Decay calibration

Synthetic decay sweeps remain diagnostic only. For a real-user calibration, `research/recall/decay_from_index.py` exports a privacy-minimized chronology containing entry IDs, unit costs and explicit `hit` dates while excluding memory text, summaries, keys and confirmation evidence. The private trace can then be replayed through `decay_replay.py`. Without an actual chronological hit trace, THM does not claim a user-specific optimal half-life or curve.

## THM 1.4 current stable status

THM 1.4 is complete and frozen as an **accepted/stable implementation milestone**. The stable code/content milestone is `e6e4dda5835e3cb345207457d5491131c6959b2c` and the recovery pointer is `archive/v1.4.0-stable`; the T0–T3 four-tier model is unchanged.

On top of the 1.3 harness-neutral recall layer, 1.4 adds explicit resident/hard-miss and planned-retrieval telemetry, a strict locator-only T1 warm directory, shadow T0 residency recommendations based on avoidable-miss penalty versus resident carry cost, exact bounded 0/1 packing, bounded prefetch trained only from real demand co-occurrence, and resident-budget feedback that never mutates budgets automatically. Hermes also exposes a default-off, session-frozen T1 locator snapshot.

These surfaces passed the accepted 1.4 correctness, Hermes and multi-harness validation. Because 1.4 did not change the retrieval path, it does not claim a new LoCoMo/Protocol 2 result. Automatic T0–T3 movement and automatic budget mutation remain disabled until held-out runtime/task A/B evidence jointly supports quality, cost, latency and reacquisition improvement. See [the 1.4 control plane](docs/14-residency-control-plane.md), [Hermes T1 directory](docs/15-hermes-warm-directory.md), and [the 1.4 closeout](reports/2026-09-07-v1.4-closeout.md).

Version identity: **1.4.0 accepted/stable implementation milestone**.

## Evidence boundaries

THM does **not** currently claim real-user end-to-end answer accuracy, a universally optimal decay curve, automatic tier movement, automatic deletion propagation, or a prompt-cache / perceived-latency improvement. `scan` records weak `mention_observed` evidence with zero activity weight. The harness integrations deliberately make no second model call: retrieval coverage, host plumbing, model use of evidence and final answer quality remain separate evidence layers.

Normal correctness CI runs on Linux, macOS and Windows. Heavy LoCoMo/model downloads and harness integration jobs are separate. Documentation: [project index](docs/README.md) · [engine guide](docs/06-engine-guide.md) · [retrieval / scan / decay](docs/09-retrieval-and-measurement.md) · [Harness adapters](docs/11-harness-adapters.md) · [version history / recovery map](docs/12-version-history.md) · [changelog](CHANGELOG.md) · [benchmark protocol](research/recall/README.md).

Related project: [hermes-academic-skills](https://github.com/xngg1021/hermes-academic-skills).

## Zero-generative-LLM retrieval successor (unreleased)

The explicit Python API option `entity_projection=True` reorders existing candidates using exact source speaker names and identifiers. At 600 tokens, full Protocol 2 any-gold improves from **69.39% to 72.52%**; the 1301 held-out questions improve from **69.56% to 72.33%**. Candidate coverage is unchanged. No generative calls or embedding model are used; T0–T3 and native memory are unchanged. Temporal, segment, association and size-ranking experiments are excluded from the production path. No 1.5 stable release has been registered. See [the experiment and evidence](docs/16-zero-llm-retrieval-frontier.md).
