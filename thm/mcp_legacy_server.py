"""Legacy MCP 2025-06-18 stdio bridge for clients that have not migrated to MCP v2.

The primary THM MCP surface is :mod:`thm.mcp_server`, which targets the
stateless MCP v2 Python SDK.  OpenClaw 2026.9.x still uses the legacy
``@modelcontextprotocol/sdk`` 1.x lifecycle, so this tiny bridge implements the
2025-06-18 JSON-RPC/stdin/stdout contract directly and delegates every recall
to the same read-only :class:`THMHarnessAdapter`.

It intentionally exposes only ``thm_recall`` and ``thm_status`` and has no
write surface.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Mapping

from .harness import HarnessConfig, THMHarnessAdapter, mcp_source

LEGACY_PROTOCOL = "2025-06-18"
SUPPORTED_LEGACY_PROTOCOLS = {"2025-06-18", "2025-03-26", "2024-11-05"}


def _server_version() -> str:
    try:
        return package_version("thm-local-memory")
    except PackageNotFoundError:
        return "1.4.0"


def _json_schema_string(description: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "string"}
    if description:
        result["description"] = description
    return result


RECALL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "context": _json_schema_string("Budget-limited evidence context."),
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _json_schema_string(),
                    "source": _json_schema_string(),
                    "sha256": _json_schema_string(),
                    "complete":{"type":"boolean"},"parent_id":_json_schema_string(),
                    "span_start":{"type":["integer","null"]},"span_end":{"type":["integer","null"]},
                    "locator_kind":_json_schema_string(),
                },
                "required": ["id", "source", "sha256", "complete", "parent_id", "span_start", "span_end", "locator_kind"],
                "additionalProperties": False,
            },
        },
        "budget": {"type": "integer"},
        "budget_used": {"type": "integer"},
        "mode": _json_schema_string(),
        "usefulness": _json_schema_string(),
    },
    "required": ["context", "sources", "budget", "budget_used", "mode", "usefulness"],
    "additionalProperties": False,
}

STATUS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scope": _json_schema_string(),
        "budget": {"type": "integer"},
        "counter": _json_schema_string(),
        "mode": _json_schema_string(),
        "neighbors": {"type": "integer"},
        "semantic": {"type": "boolean"},
        "source_writes": {"type": "boolean"},
    },
    "required": ["scope", "budget", "counter", "mode", "neighbors", "semantic", "source_writes"],
    "additionalProperties": False,
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "thm_recall",
        "title": "THM Recall",
        "description": "Recall budget-limited evidence from a local read-only THM index.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": _json_schema_string("Question or retrieval query.")},
            "required": ["query"],
            "additionalProperties": False,
        },
        "outputSchema": RECALL_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "thm_status",
        "title": "THM Status",
        "description": "Describe this THM recall surface without returning memory text.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "outputSchema": STATUS_OUTPUT_SCHEMA,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]


class LegacyMCPServer:
    """Minimal newline-delimited MCP 2025-06-18 server."""

    def __init__(self, config: HarnessConfig | Mapping[str, Any]):
        self.adapter = THMHarnessAdapter(config)
        self.initialized = False

    def close(self) -> None:
        self.adapter.close()

    @staticmethod
    def _response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    @staticmethod
    def _tool_result(payload: Mapping[str, Any]) -> dict[str, Any]:
        serialised = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return {
            "content": [{"type": "text", "text": serialised}],
            "structuredContent": dict(payload),
            "isError": False,
        }

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "thm_recall":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("thm_recall requires a non-empty string query")
            if set(arguments) != {"query"}:
                raise ValueError("thm_recall accepts only the query argument")
            result = self.adapter.recall(query)
            payload = {
                "context": result["context"],
                "sources": [
                    mcp_source(row)
                    for row in result["sources"]
                ],
                "budget": result["budget"],
                "budget_used": result["budget_used"],
                "mode": result["mode"],
                "usefulness": "unverified",
            }
            return self._tool_result(payload)

        if name == "thm_status":
            if arguments:
                raise ValueError("thm_status accepts no arguments")
            cfg = self.adapter.config
            payload = {
                "scope": cfg.scope,
                "budget": cfg.budget,
                "counter": cfg.counter,
                "mode": cfg.mode,
                "neighbors": cfg.neighbors,
                "semantic": cfg.mode in ("dense", "hybrid"),
                "source_writes": False,
                "runtime": self.adapter.runtime_status(),
            }
            return self._tool_result(payload)

        raise KeyError(name)

    def handle(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        if message.get("jsonrpc") != "2.0":
            return self._error(message.get("id"), -32600, "Invalid JSON-RPC version")
        method = message.get("method")
        request_id = message.get("id")

        if method == "notifications/initialized":
            self.initialized = True
            return None
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if request_id is None:
            return None

        if method == "initialize":
            params = message.get("params")
            if not isinstance(params, Mapping):
                return self._error(request_id, -32602, "initialize params must be an object")
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                return self._error(request_id, -32602, "protocolVersion must be a string")
            negotiated = requested if requested in SUPPORTED_LEGACY_PROTOCOLS else LEGACY_PROTOCOL
            return self._response(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "THM legacy bridge", "version": _server_version()},
                    "instructions": "Read-only THM recall compatibility bridge for MCP 1.x clients.",
                },
            )

        if method == "ping":
            return self._response(request_id, {})
        if method == "tools/list":
            return self._response(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, Mapping):
                return self._error(request_id, -32602, "tools/call params must be an object")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                return self._error(request_id, -32602, "tools/call requires name and object arguments")
            try:
                return self._response(request_id, self._call_tool(name, arguments))
            except KeyError:
                return self._error(request_id, -32601, f"Unknown tool: {name}")
            except (ValueError, TypeError) as exc:
                return self._error(request_id, -32602, str(exc))
            except Exception as exc:  # Keep the protocol alive while surfacing a tool-local failure.
                payload = {
                    "content": [{"type": "text", "text": f"THM tool failed: {type(exc).__name__}: {exc}"}],
                    "isError": True,
                }
                return self._response(request_id, payload)

        return self._error(request_id, -32601, f"Method not found: {method}")

    def serve(self) -> int:
        try:
            for raw in sys.stdin.buffer:
                if not raw.strip():
                    continue
                try:
                    decoded = json.loads(raw.decode("utf-8"))
                    if not isinstance(decoded, Mapping):
                        response = self._error(None, -32600, "JSON-RPC message must be an object")
                    else:
                        response = self.handle(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    response = self._error(None, -32700, "Parse error", str(exc))
                if response is not None:
                    out = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
                    sys.stdout.write(out + "\n")
                    sys.stdout.flush()
        finally:
            self.close()
        return 0


def main(argv: list[str] | None = None) -> int:
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
    server = LegacyMCPServer(
        HarnessConfig(
            db=args.db,
            scope=args.scope,
            budget=args.budget,
            counter=args.counter,
            mode=args.mode,
            neighbors=args.neighbors,
            model_path=args.model_path,
            model_id=args.model_id, features=json.loads(args.features_json),
        )
    )
    return server.serve()


if __name__ == "__main__":
    raise SystemExit(main())
