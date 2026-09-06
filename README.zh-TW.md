# THM — Tiered Hot Memory

[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Français](README.fr.md) | [Deutsch](README.de.md)

作者：Junfu Shi (SJF, xngg1021) · 授權：[MIT](LICENSE) · 目前穩定版：**1.3.0**

THM 是 agent harness 的本機優先四層記憶工具。1.3 提供 harness-neutral 唯讀召回層：Hermes `MemoryProvider`、OpenAI Agents `FunctionTool`、LangChain/LangGraph `BaseRetriever`、MCP v2 stdio，以及 OpenClaw 2026.9.x 的獨立 legacy MCP 橋。Claude Code、Codex CLI 與 Gemini CLI 均由固定版本真實 CLI 設定及同一服務命令 lifecycle E2E 驗證。原生記憶不會被改寫，也不會額外呼叫模型。

LoCoMo Protocol 2 涵蓋 10 段對話、1,986 題；主口徑 1,532 題。在 600 evidence token 下，literal / sparse / dense / hybrid 的 any-gold coverage 為 **56.79% / 69.39% / 51.11% / 71.34%**，這是證據召回而非回答正確率。[完整報告](reports/2026-09-06-recall-protocol2.md)

```bash
python -m pip install -e .
python -m thm search --db ./state/recall.sqlite3 --scope demo "Which database port?" --budget 600
thm-mcp --db /absolute/path/recall.sqlite3 --scope demo --budget 600
```

1.3.0 accepted/stable 僅由指向已通過 correctness、Hermes、harness 全矩陣之精確 Git SHA 的正式版本引用確認。尚未宣稱真實使用者 E2E 回答正確率、普適最佳衰減、自動換層／刪除傳播或體感延遲改善。

文檔：[目錄](docs/README.md) · [Harness](docs/11-harness-adapters.md) · [版本歷史](docs/12-version-history.md) · [更新日誌](CHANGELOG.md)
