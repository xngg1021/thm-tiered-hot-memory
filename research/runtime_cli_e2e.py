#!/usr/bin/env python3
"""Pinned, no-model E2E through Claude Code, Codex CLI and Gemini CLI MCP config."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from thm.retrieval import Document, SearchIndex


def run(command: list[str], *, env: dict[str, str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=90, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout


async def protocol_probe(command: list[str], cwd: Path) -> dict:
    params = StdioServerParameters(command=command[0], args=command[1:], cwd=str(cwd))
    async with Client(stdio_client(params)) as client:
        listed = await client.list_tools()
        names = sorted(tool.name for tool in listed.tools)
        if names != ["thm_recall", "thm_status"]:
            raise RuntimeError(f"unexpected tool surface: {names}")
        recalled = await client.call_tool("thm_recall", {"query": "Which database port?"})
        payload = recalled.structured_content
        data = payload.get("result", payload) if isinstance(payload, dict) else {}
        if "5439" not in data.get("context", ""):
            raise RuntimeError("runtime command lost THM recall evidence")
        status = await client.call_tool("thm_status", {})
        status_payload = status.structured_content
        status_data = status_payload.get("result", status_payload) if isinstance(status_payload, dict) else {}
        if status_data.get("source_writes") is not False:
            raise RuntimeError("runtime command lost the read-only boundary")
        return {"tools": names, "recall": "5439", "source_writes": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("claude-code", "codex-cli", "gemini-cli"), required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temp_name:
        temp = Path(temp_name)
        db = temp / "runtime.sqlite3"
        index = SearchIndex(db)
        try:
            index.replace_scope("runtime-e2e", [Document(
                "runtime-port", "runtime-e2e", "synthetic", 0,
                "The runtime integration database port is 5439.",
                speaker="user", source="file:synthetic-runtime", tier="T2")])
        finally:
            index.close()
        # The pinned CLIs currently speak the broadly deployed MCP generation;
        # THM keeps that wire contract in its separate read-only compatibility bridge.
        server = [sys.executable, "-m", "thm.mcp_legacy_server", "--db", str(db), "--scope", "runtime-e2e"]
        env = dict(os.environ)
        env["HOME"] = str(temp / "home")
        Path(env["HOME"]).mkdir()
        if args.runtime == "claude-code":
            add = [args.executable, "mcp", "add", "--scope", "user", "thm", "--", *server]
            inspect = [args.executable, "mcp", "get", "thm"]
        elif args.runtime == "codex-cli":
            env["CODEX_HOME"] = str(temp / "codex")
            Path(env["CODEX_HOME"]).mkdir()
            add = [args.executable, "mcp", "add", "thm", "--", *server]
            inspect = [args.executable, "mcp", "get", "thm"]
        else:
            gemini_dir = Path(env["HOME"]) / ".gemini"
            gemini_dir.mkdir()
            (gemini_dir / "settings.json").write_text(
                json.dumps({"security": {"folderTrust": {"enabled": False}}}) + "\n",
                encoding="utf-8",
            )
            add = [args.executable, "mcp", "add", "--scope", "user", "thm", server[0], "--", *server[1:]]
            inspect = [args.executable, "mcp", "list"]
        add_output = run(add, env=env, cwd=root)
        inspect_output = run(inspect, env=env, cwd=root)
        combined = add_output + "\n" + inspect_output
        if "thm" not in combined or str(db) not in combined:
            raise RuntimeError(f"{args.runtime} did not persist the exact THM command\n{combined}")
        if args.runtime in ("claude-code", "gemini-cli") and "Connected" not in combined:
            raise RuntimeError(f"{args.runtime} did not connect to THM\n{combined}")
        probe = asyncio.run(protocol_probe(server, root))
        result = {
            "status": "PASS", "runtime": args.runtime, "package": args.package,
            "configuration_loaded_by_runtime": True, "protocol_probe": probe,
            "model_calls": 0, "source_memory_writes": 0,
            "scope": "pinned real CLI configuration plus exact-command MCP lifecycle",
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
