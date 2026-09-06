# THM 1.3 — Harness adapters

THM 1.3 separates the retrieval engine from harness plumbing. `thm.harness.THMHarnessAdapter` opens an existing derived THM index read-only and returns only budget-packed evidence plus source identity. Harness adapters do not become the owner of native memory files and do not promote retrieval into verified usefulness.

## Supported integration surfaces

| Harness / protocol | THM surface | Validation level |
| --- | --- | --- |
| Hermes Agent | standalone `MemoryProvider` through `hermes_agent.memory_providers` | real pinned Hermes discovery/lifecycle CI; setup, prefetch, background `sync_turn`, session boundary and write≠hit semantics are exercised |
| OpenAI Agents SDK | `OpenAIAgentsTHM.tool` (`FunctionTool`) | pinned SDK contract E2E, no model call |
| LangChain / LangGraph / Deep Agents | `THMLangChainRetriever(BaseRetriever)` | pinned `langchain-core` `invoke()` E2E, no model call |
| MCP v2 | `python -m thm.mcp_server` / `thm-mcp` stdio server | real MCP v2 client lists and calls `thm_recall` / `thm_status`; structured output schema is exercised |
| OpenClaw 2026.9.x | `python -m thm.mcp_legacy_server` / `thm-mcp-legacy` compatibility bridge | pinned OpenClaw registry health check plus live `mcp probe --json` tool discovery; bridge delegates to the same read-only THM recall core |
| Claude Code | THM MCP v2 stdio server | supported by Claude Code's documented local-stdio MCP surface; configuration recipe below, not yet a pinned Claude runtime E2E |
| Codex CLI | THM MCP v2 stdio server | supported by Codex MCP configuration; configuration recipe below, not yet a pinned Codex runtime E2E |
| Gemini CLI | THM MCP v2 stdio server | supported by Gemini CLI's documented `mcpServers` / `gemini mcp add` surface; configuration recipe below, not yet a pinned Gemini runtime E2E |

The distinction matters: “MCP-compatible” is not reported as the same evidence level as a harness-specific runtime test. THM also does not force an older client onto the MCP v2 server: the legacy bridge is a separate compatibility surface so the primary `thm-mcp` contract can remain MCP v2.

## Install

Core THM remains lightweight. Install only the adapter dependencies you use:

```bash
python -m pip install -e '.[openai]'
python -m pip install -e '.[langchain]'
python -m pip install -e '.[mcp]'
# or all Python harness integrations
python -m pip install -e '.[harnesses]'
```

The OpenClaw legacy bridge itself uses the THM core plus the Python standard library; it does not require installing a second MCP Python SDK generation.

Create or refresh a THM retrieval index first. The examples below assume:

```text
DB=/absolute/path/recall.sqlite3
SCOPE=demo
```

## OpenAI Agents SDK

```python
from agents import Agent
from thm.adapters.openai_agents import OpenAIAgentsTHM

memory = OpenAIAgentsTHM({"db": DB, "scope": "demo", "budget": 600})
agent = Agent(name="assistant", instructions="Use recalled evidence when relevant.", tools=[memory.tool])
# close memory when the host shuts down
```

`thm_recall` returns a JSON string containing the budget-packed context, selected source IDs and `usefulness: "unverified"`. THM does not call a second model.

## LangChain / LangGraph

```python
from thm.adapters.langchain import THMLangChainRetriever

retriever = THMLangChainRetriever(index_path=DB, scope="demo", budget=600)
docs = retriever.invoke("Which database port?")
```

Returned `Document` objects contain only selected source text. Metadata carries THM scope/generation, budget, source hash and `thm_usefulness="unverified"`.

## MCP v2

Start THM as a local stdio MCP v2 server:

```bash
thm-mcp --db "$DB" --scope "$SCOPE" --budget 600
# equivalent:
python -m thm.mcp_server --db "$DB" --scope "$SCOPE" --budget 600
```

The server deliberately exposes two read-only tools:

- `thm_recall(query)` — budget-packed evidence and source identities;
- `thm_status()` — configuration/status without memory text.

Both tools publish typed structured-output contracts. The server exposes no remember/delete/write tool.

## OpenClaw

The pinned OpenClaw 2026.9.x integration is validated through THM's separate legacy stdio compatibility bridge. The bridge implements the older MCP lifecycle expected by that client generation while delegating actual recall to the same `THMHarnessAdapter` used by the MCP v2 and Python surfaces.

```bash
openclaw mcp set thm '{"command":"python","args":["-m","thm.mcp_legacy_server","--db","/absolute/path/recall.sqlite3","--scope","demo"]}'
openclaw mcp doctor thm --probe --json
openclaw mcp probe thm --json
```

`doctor --probe` is used as the registry/startup health check. `probe --json` is the capability proof that lists the live tools; CI asserts that its catalog contains `thm_recall` and `thm_status`. Unit tests independently exercise initialize, `tools/list`, `tools/call`, structured content and unknown-tool failure semantics. The bridge remains read-only and is not a second memory implementation.

## Claude Code

Claude Code supports local stdio MCP servers. Put options before the server name and the server command after `--`:

```bash
claude mcp add --transport stdio thm -- \
  python -m thm.mcp_server --db /absolute/path/recall.sqlite3 --scope demo
claude mcp get thm
```

This is a documented MCP compatibility recipe. THM does not currently claim a pinned Claude Code runtime E2E.

## Codex CLI

Codex supports MCP server configuration. Configure THM as a local stdio server using the Codex MCP configuration surface available in the installed Codex version, with the server command:

```text
python -m thm.mcp_server --db /absolute/path/recall.sqlite3 --scope demo
```

Keep THM tool approval/read-only policy visible to the host. This is MCP compatibility, not a pinned Codex runtime E2E in this repository.

## Gemini CLI

Gemini CLI supports local stdio MCP servers through `gemini mcp add` or `mcpServers` in settings:

```bash
gemini mcp add --scope user thm python -- \
  -m thm.mcp_server --db /absolute/path/recall.sqlite3 --scope demo
gemini mcp list
```

Do not use `--trust` merely to make setup easier; host approval policy is separate from THM's read-only server design. This recipe is MCP compatibility, not a pinned Gemini runtime E2E.

## Hermes lifecycle completion

The Hermes adapter now has a setup schema and profile-scoped private config, validates semantic-mode dependencies, supports the host's serialized `sync_turn` path when `sync_turns` is explicitly enabled, reconciles current-session user/assistant text into a separate derived live T2 scope, filters compressed summaries/system rows, handles session-end and best-effort v1 pre-compress hooks, and keeps `on_memory_write` as a refresh signal rather than a hit.

`queue_prefetch` is intentionally a no-op: Hermes calls it with the just-completed user turn, while THM's local search is already low-latency and the next query is unknown. Prewarming the previous query would consume resources without establishing relevance to the next turn.

THM does **not** advertise Hermes pre-compress checkpoint API v2. A v2 provider must durably archive evidence before returning and fail closed when checkpoint enforcement is enabled. THM's optional live-session scope is a derived recall cache, not the canonical transcript owner, so claiming that durability contract would be false.

## Boundaries

Harness support does not change THM into a universal memory database. Native memory/source ownership remains outside the adapters. Automatic tier movement remains separate from retrieval. Source imports still require explicit refresh unless a harness-specific derived live scope is enabled. No adapter turns `mention_observed`, retrieval, or a source write into a `hit`. Current integration CI intentionally makes zero model calls, so provider/tool plumbing is measured separately from generated-answer quality.
