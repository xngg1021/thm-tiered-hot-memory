#!/usr/bin/env python3
"""Pinned-upstream Hermes lifecycle E2E for THM 1.3.

Uses Hermes' real pip-entrypoint discovery, MemoryProvider/MemoryManager lifecycle,
setup config, background turn sync, prefetch, compression hook and session switch.
No model/API call is made; all evidence is synthetic and temporary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from thm.retrieval import Document, SearchIndex


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


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

        os.environ["HERMES_HOME"] = str(home)
        for key in (
            "THM_RECALL_SCOPE", "THM_RECALL_MODE", "THM_RECALL_COUNTER", "THM_RECALL_BUDGET",
            "THM_RECALL_MODEL_PATH", "THM_RECALL_MODEL_ID", "THM_SYNC_TURNS",
        ):
            os.environ.pop(key, None)

        from agent.memory_provider import MemoryProvider, PRE_COMPRESS_CHECKPOINT_API_VERSION
        from agent.memory_manager import MemoryManager, build_memory_context_block
        from plugins.memory import list_memory_provider_names, load_memory_provider

        names = list_memory_provider_names()
        if "thm" not in names:
            raise RuntimeError(f"THM entry point not discovered; providers={names}")
        provider = load_memory_provider("thm", register_skills=False)
        if provider is None or not isinstance(provider, MemoryProvider):
            raise RuntimeError("Hermes did not load THM as a MemoryProvider")

        schema = provider.get_config_schema()
        keys = {row.get("key") for row in schema}
        required = {"scope", "mode", "budget", "sync_turns"}
        if not required <= keys:
            raise RuntimeError(f"THM setup schema missing fields: {sorted(required - keys)}")
        provider.save_config({"scope": "e2e", "mode": "sparse", "budget": 600, "sync_turns": True}, str(home))
        config_path = home / "memories" / ".thm" / "provider.json"
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        if saved.get("scope") != "e2e" or saved.get("sync_turns") is not True:
            raise RuntimeError(f"saved setup config mismatch: {saved}")
        if os.name != "nt" and stat.S_IMODE(config_path.stat().st_mode) != 0o600:
            raise RuntimeError("provider config is not private mode 0600")
        if not provider.is_available():
            raise RuntimeError(provider.unavailable_reason())

        manager = MemoryManager()
        manager.add_provider(provider)
        manager.initialize_all("session-a", hermes_home=str(home), platform="cli", agent_context="primary")
        if provider not in manager.providers:
            raise RuntimeError("Hermes MemoryManager rejected THM provider")
        if manager.supports_pre_compress_checkpoint(PRE_COMPRESS_CHECKPOINT_API_VERSION):
            raise RuntimeError("THM must not claim checkpoint API v2")

        context = manager.prefetch_all("Which integration database port should I use?", session_id="session-a")
        if "5439" not in context:
            raise RuntimeError(f"prefetch missed synthetic evidence: {context!r}")
        fenced = build_memory_context_block(context)
        if "<memory-context>" not in fenced or "5439" not in fenced:
            raise RuntimeError("Hermes memory-context fencing lost THM evidence")
        if not manager.describe_recall():
            raise RuntimeError("Hermes recall indicator did not expose THM recall")

        messages = [
            {"role": "system", "content": "system text must not enter live THM scope"},
            {"role": "user", "content": "My live session color code is ultramarine-731."},
            {"role": "assistant", "content": "Recorded for this session."},
            {"role": "user", "content": "DERIVATIVE-SUMMARY-MUST-NOT-BE-INDEXED", "_compressed_summary": True},
        ]
        manager.sync_all(messages[1]["content"], messages[2]["content"], session_id="session-a", messages=messages)
        if not manager.flush_pending(timeout=5.0):
            raise RuntimeError("Hermes background sync did not drain")

        live_context = manager.prefetch_all("What is my live session color code?", session_id="session-a")
        if "ultramarine-731" not in live_context:
            raise RuntimeError(f"sync_turn live scope was not recalled: {live_context!r}")
        live_scope = provider._live_scope("session-a")
        check = SearchIndex(recall, readonly=True)
        try:
            live_rows = check.rows(live_scope)
        finally:
            check.close()
        texts = [row["text"] for row in live_rows]
        if any("DERIVATIVE-SUMMARY" in text or "system text" in text for text in texts):
            raise RuntimeError(f"live scope retained filtered transcript rows: {texts}")

        queued_before = sha256(recall)
        manager.queue_prefetch_all("same current turn text", session_id="session-a")
        if not manager.flush_pending(timeout=5.0):
            raise RuntimeError("Hermes queued prefetch did not drain")
        if sha256(recall) != queued_before:
            raise RuntimeError("queue_prefetch mutated THM derived state")

        precompress = manager.on_pre_compress(messages, evidence_messages=[
            {"role": "user", "content": "normalized evidence"},
        ], require_checkpoint=False)
        if precompress:
            raise RuntimeError("THM best-effort pre-compress hook must not fabricate summary text")

        before_write = sha256(recall)
        manager.on_memory_write("add", "memory", "synthetic native write", metadata={"write_origin": "e2e"})
        after_write = sha256(recall)
        if before_write != after_write:
            raise RuntimeError("on_memory_write mutated the derived recall database")
        tool = json.loads(provider.handle_tool_call("thm_recall_status", {}))
        if tool.get("usefulness") != "unverified" or tool.get("source_refresh_required") is not True:
            raise RuntimeError(f"write callback/status semantics wrong: {tool}")
        if provider.recall_status() is not None:
            raise RuntimeError("on_memory_write should clear last recall status")

        manager.commit_session_boundary_async(messages, new_session_id="session-b", reason="e2e")
        if not manager.flush_pending(timeout=5.0):
            raise RuntimeError("Hermes session-boundary task did not drain")
        if manager.prefetch_all("database port", session_id="session-a"):
            raise RuntimeError("old session unexpectedly received recall after switch")
        context_b = manager.prefetch_all("database port", session_id="session-b")
        if "5439" not in context_b:
            raise RuntimeError("new session did not receive fresh base recall")
        manager.shutdown_all()

        result = {
            "status": "PASS",
            "hermes_commit": actual_sha,
            "provider_discovered_by": "hermes_agent.memory_providers",
            "setup_schema_checked": True,
            "setup_config_saved_private": True,
            "memory_provider_abc": True,
            "memory_manager_admission": True,
            "prefetch_evidence_seen": True,
            "memory_context_fenced": True,
            "background_sync_turn_checked": True,
            "live_session_scope_checked": True,
            "compressed_summary_filtered": True,
            "queue_prefetch_no_source_write": True,
            "pre_compress_best_effort_v1": True,
            "checkpoint_v2_claimed": False,
            "session_boundary_order_checked": True,
            "write_callback_is_not_hit": True,
            "write_callback_marks_refresh_required": True,
            "recall_db_unchanged_by_write_callback": before_write == after_write,
            "model_calls": 0,
            "network_calls_by_test": 0,
            "scope": "synthetic temporary Hermes provider lifecycle; not answer-generation E2E",
        }
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
