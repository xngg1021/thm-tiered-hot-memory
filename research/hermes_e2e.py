#!/usr/bin/env python3
"""Pinned-upstream Hermes provider lifecycle E2E for THM.

This uses Hermes' real installed plugin discovery, MemoryProvider ABC and
MemoryManager. It makes no model/API call and uses only a temporary synthetic
THM retrieval database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from thm.retrieval import Document, SearchIndex


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    hermes_root = Path(args.hermes_root).resolve()
    actual_sha = git_head(hermes_root)
    if actual_sha != args.expected_sha:
        raise RuntimeError(f"Hermes SHA mismatch: {actual_sha} != {args.expected_sha}")

    with tempfile.TemporaryDirectory() as temp:
        home = Path(temp) / "hermes-home"
        recall = home / "memories" / ".thm" / "recall.sqlite3"
        recall.parent.mkdir(parents=True)
        index = SearchIndex(recall)
        try:
            index.replace_scope("e2e", [
                Document(
                    "e2e-port", "e2e", "synthetic-session", 0,
                    "The integration database port is 5439.",
                    speaker="user", timestamp="2026-09-06T00:00:00+00:00",
                    source="file:synthetic-e2e", tier="T2",
                )
            ])
        finally:
            index.close()

        before = sha256(recall)
        os.environ["HERMES_HOME"] = str(home)
        os.environ["THM_RECALL_SCOPE"] = "e2e"

        from agent.memory_provider import MemoryProvider
        from agent.memory_manager import MemoryManager, build_memory_context_block
        from plugins.memory import list_memory_provider_names, load_memory_provider

        names = list_memory_provider_names()
        if "thm" not in names:
            raise RuntimeError(f"THM entry point not discovered; providers={names}")
        provider = load_memory_provider("thm", register_skills=False)
        if provider is None or not isinstance(provider, MemoryProvider):
            raise RuntimeError("Hermes did not load THM as a MemoryProvider")
        if not provider.is_available():
            raise RuntimeError(provider.unavailable_reason())

        manager = MemoryManager()
        manager.add_provider(provider)
        if provider not in manager._providers:
            raise RuntimeError("Hermes MemoryManager rejected THM provider")

        provider.initialize(
            "session-a", hermes_home=str(home), platform="cli", agent_context="primary"
        )
        context = provider.prefetch(
            "Which integration database port should I use?", session_id="session-a"
        )
        if "5439" not in context:
            raise RuntimeError(f"prefetch missed synthetic evidence: {context!r}")
        status = provider.recall_status()
        if status is None or status.count < 1:
            raise RuntimeError("Hermes RecallStatus did not expose THM recall")
        tool = json.loads(provider.handle_tool_call("thm_recall_status", {}))
        if "e2e-port" not in tool.get("returned_ids", []):
            raise RuntimeError(f"status tool lost selected source identity: {tool}")
        if tool.get("usefulness") != "unverified":
            raise RuntimeError("THM must not promote retrieval into usefulness")

        fenced = build_memory_context_block(context)
        if "<memory-context>" not in fenced or "5439" not in fenced:
            raise RuntimeError("Hermes memory-context fencing lost THM evidence")

        provider.on_memory_write("add", "memory", "synthetic write")
        after_write = sha256(recall)
        if before != after_write:
            raise RuntimeError("on_memory_write mutated the derived recall database")
        if provider.recall_status() is not None:
            raise RuntimeError("on_memory_write should clear last recall status")

        provider.on_session_switch("session-b")
        if provider.prefetch("database port", session_id="session-a"):
            raise RuntimeError("old session unexpectedly received recall after switch")
        context_b = provider.prefetch("database port", session_id="session-b")
        if "5439" not in context_b:
            raise RuntimeError("new session did not receive fresh recall")
        provider.shutdown()

        result = {
            "status": "PASS",
            "hermes_commit": actual_sha,
            "provider_discovered_by": "hermes_agent.memory_providers",
            "memory_provider_abc": True,
            "memory_manager_admission": True,
            "prefetch_evidence_seen": True,
            "memory_context_fenced": True,
            "session_switch_checked": True,
            "write_callback_is_not_hit": True,
            "recall_db_unchanged_by_write_callback": before == after_write,
            "model_calls": 0,
            "network_calls_by_test": 0,
            "scope": "synthetic temporary provider lifecycle; not answer-generation E2E",
        }
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
