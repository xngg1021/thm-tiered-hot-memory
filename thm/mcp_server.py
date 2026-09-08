"""Read-only MCP v2 server exposing THM recall to MCP-capable harnesses."""
from __future__ import annotations

import argparse
import json
import atexit

from typing_extensions import TypedDict

from .harness import HarnessConfig, THMHarnessAdapter, mcp_source


class MCPSource(TypedDict):
    """Stable source metadata returned by the MCP recall surface."""

    id: str
    source: str
    sha256: str
    complete: bool
    parent_id: str
    span_start: int | None
    span_end: int | None
    locator_kind: str


class MCPRecallResult(TypedDict):
    """Structured MCP result for one budget-limited THM recall."""

    context: str
    sources: list[MCPSource]
    budget: int
    budget_used: int
    mode: str
    usefulness: str


class MCPStatusResult(TypedDict):
    """Structured MCP status result without memory text."""

    scope: str
    budget: int
    counter: str
    mode: str
    neighbors: int
    semantic: bool
    source_writes: bool


def build_server(config: HarnessConfig | dict):
    from mcp.server import MCPServer

    adapter = THMHarnessAdapter(config)
    server = MCPServer("THM")

    @server.tool()
    def thm_recall(query: str) -> MCPRecallResult:
        """Recall budget-limited evidence from a local THM index."""
        result = adapter.recall(query)
        sources: list[MCPSource] = [
            mcp_source(row)
            for row in result["sources"]
        ]
        return {
            "context": result["context"],
            "sources": sources,
            "budget": result["budget"],
            "budget_used": result["budget_used"],
            "mode": result["mode"],
            "usefulness": "unverified",
        }

    @server.tool()
    def thm_status() -> MCPStatusResult:
        """Describe the configured THM recall surface without returning memory text."""
        cfg = adapter.config
        return {
            "scope": cfg.scope,
            "budget": cfg.budget,
            "counter": cfg.counter,
            "mode": cfg.mode,
            "neighbors": cfg.neighbors,
            "semantic": cfg.mode in ("dense", "hybrid"),
            "source_writes": False,
        }

    atexit.register(adapter.close)
    return server, adapter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--budget", type=int, default=600)
    parser.add_argument("--counter", default="utf8_bytes")
    parser.add_argument("--mode", choices=["literal", "sparse", "dense", "hybrid"], default="sparse")
    parser.add_argument("--neighbors", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--model-path")
    parser.add_argument("--model-id")
    parser.add_argument("--features-json",default="{}")
    args = parser.parse_args(argv)
    server, _adapter = build_server(HarnessConfig(
        db=args.db,
        scope=args.scope,
        budget=args.budget,
        counter=args.counter,
        mode=args.mode,
        neighbors=args.neighbors,
        model_path=args.model_path,
        model_id=args.model_id, features=json.loads(args.features_json),
    ))
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
