#!/usr/bin/env python3
"""No-model E2E for THM's direct and standard-protocol harness adapters."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import tempfile

from thm.harness import HarnessConfig
from thm.retrieval import Document, SearchIndex


def build_db(path: Path) -> None:
    index = SearchIndex(path)
    try:
        index.replace_scope("harness-e2e", [
            Document(
                "e2e-port", "harness-e2e", "synthetic", 0,
                "The harness integration database port is 5439.",
                speaker="user", timestamp="2026-09-06T00:00:00+00:00",
                source="file:synthetic-harness-e2e", tier="T2",
            )
        ])
    finally:
        index.close()


def openai_agents_check(config):
    from thm.adapters.openai_agents import OpenAIAgentsTHM
    bundle = OpenAIAgentsTHM(config)
    try:
        tool = bundle.tool
        if getattr(tool, "name", None) != "thm_recall":
            raise RuntimeError("OpenAI Agents tool name mismatch")
        wrapped = getattr(tool, "__wrapped__", None)
        if not callable(wrapped):
            raise RuntimeError("decorated FunctionTool did not expose test callable")
        payload = json.loads(wrapped("Which database port?"))
        if "5439" not in payload.get("context", ""):
            raise RuntimeError("OpenAI Agents adapter lost THM context")
        return {"tool_name": tool.name, "source_ids": payload.get("source_ids", [])}
    finally:
        bundle.close()


def langchain_check(config):
    from thm.adapters.langchain import THMLangChainRetriever
    retriever = THMLangChainRetriever(
        index_path=config.db, scope=config.scope, budget=config.budget,
        counter=config.counter, mode=config.mode, neighbors=config.neighbors,
    )
    try:
        docs = retriever.invoke("Which database port?")
        if not docs or "5439" not in docs[0].page_content:
            raise RuntimeError("LangChain retriever lost THM context")
        if docs[0].metadata.get("thm_usefulness") != "unverified":
            raise RuntimeError("LangChain adapter promoted retrieval to usefulness")
        return {"documents": len(docs), "first_id": getattr(docs[0], "id", None)}
    finally:
        retriever.close()


def graph_check(config):
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END
    from thm.adapters.langgraph import THMGraphNode, deep_agents_tools
    from deepagents import create_deep_agent
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    class State(TypedDict):
        query: str
        memory_evidence: dict
        thm_runtime_status: dict
    node = THMGraphNode(config)
    tools, lifecycle = deep_agents_tools(config)
    try:
        graph = StateGraph(State)
        graph.add_node('recall', node); graph.add_edge(START, 'recall'); graph.add_edge('recall', END)
        result = graph.compile().invoke({'query': 'Which database port?'})
        if '5439' not in result['memory_evidence']['context']:
            raise RuntimeError('LangGraph lost canonical evidence')
        output = tools[0].invoke({'query': 'Which database port?'})
        if '5439' not in output['context']:
            raise RuntimeError('Deep Agents tool adapter lost canonical evidence')
        # Construct a real Deep Agents graph with a non-network model. Invoking
        # the tools above validates memory plumbing without claiming model outcome.
        class LocalModel(FakeListChatModel):
            def bind_tools(self, tools, **kwargs):
                return self
        agent = create_deep_agent(model=LocalModel(responses=['fixture']), tools=tools)
        if not callable(getattr(agent, 'invoke', None)):
            raise RuntimeError('Deep Agents graph construction failed')
        return {'langgraph': 'executed', 'deepagents': 'graph-constructed-and-tools-executed',
                'generation_calls': 0, 'agent_outcome': 'not-run'}
    finally:
        lifecycle.close(); node.close()


async def mcp_check(config):
    from mcp import Client
    from thm.mcp_server import build_server
    server, adapter = build_server(config)
    try:
        async with Client(server) as client:
            listed = await client.list_tools()
            names = sorted(tool.name for tool in listed.tools)
            if names != ["thm_recall", "thm_status"]:
                raise RuntimeError(f"unexpected MCP tool surface: {names}")
            result = await client.call_tool("thm_recall", {"query": "Which database port?"})
            payload = result.structured_content
            if not isinstance(payload, dict):
                raise RuntimeError("MCP structured result missing")
            data = payload.get("result", payload)
            if "5439" not in data.get("context", ""):
                raise RuntimeError("MCP adapter lost THM context")
            status = await client.call_tool("thm_status", {})
            status_payload = status.structured_content
            status_data = status_payload.get("result", status_payload) if isinstance(status_payload, dict) else {}
            if status_data.get("source_writes") is not False:
                raise RuntimeError("MCP status did not preserve read-only boundary")
            return {"tools": names, "source_writes": False}
    finally:
        adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--db-output")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        path = Path(args.db_output) if args.db_output else Path(temp) / "recall.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        build_db(path)
        config = HarnessConfig(db=str(path), scope="harness-e2e", budget=600)
        result = {
            "status": "PASS",
            "openai_agents": openai_agents_check(config),
            "langchain": langchain_check(config),
            "langgraph_deepagents": graph_check(config),
            "mcp_v2": asyncio.run(mcp_check(config)),
            "model_calls": 0,
            "source_memory_writes": 0,
            "scope": "synthetic local recall; harness plumbing only",
        }
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
