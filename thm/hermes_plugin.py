"""Hermes MemoryProvider adapter for THM.

The provider keeps native Hermes memory files and state.db read-only. Optional
turn synchronization writes only a derived THM retrieval scope keyed to the
Hermes session; it is disabled by default and never fabricates hit events.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading

from .retrieval import Document, SearchIndex, TokenCounter, SentenceEncoder
from agent.memory_provider import MemoryProvider, RecallStatus


_CONFIG_NAME = "provider.json"


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
    raise ValueError("boolean setting expected")


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("symlink config target refused")
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=".thm-provider-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _profile_config_path(hermes_home: str | Path) -> Path:
    return Path(hermes_home).expanduser().resolve() / "memories" / ".thm" / _CONFIG_NAME


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    if path.is_symlink():
        raise ValueError("symlink provider config refused")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("THM provider config must be a JSON object")
    return value


def _current_hermes_home() -> str | None:
    if os.environ.get("HERMES_HOME"):
        return os.environ["HERMES_HOME"]
    try:
        from hermes_constants import get_hermes_home
        return str(get_hermes_home())
    except Exception:
        return None


def _message_text(message) -> str:
    if not isinstance(message, dict):
        return ""
    try:
        from agent.message_content import flatten_message_text
        return (flatten_message_text(message.get("content")) or "").strip()
    except Exception:
        return message.get("content", "").strip() if isinstance(message.get("content"), str) else ""


class THMProvider(MemoryProvider):
    @property
    def name(self):
        return "thm"

    def __init__(self, config=None):
        self.config = dict(config or {})
        self._lock = threading.RLock()
        self.last = None
        self.error = None
        self.path = None
        self.session_id = None
        self.encoder = None
        self._index = None
        self.scope = self.config.get("scope") or os.environ.get("THM_RECALL_SCOPE")
        self._agent_context = "primary"
        self._sync_turns = False
        self._source_refresh_required = False

    def _saved_config(self, hermes_home=None):
        home = hermes_home or _current_hermes_home()
        return _load_json(_profile_config_path(home)) if home else {}

    def _merged_config(self, hermes_home=None):
        merged = self._saved_config(hermes_home)
        merged.update(self.config)
        env_map = {
            "scope": os.environ.get("THM_RECALL_SCOPE"),
            "mode": os.environ.get("THM_RECALL_MODE"),
            "counter": os.environ.get("THM_RECALL_COUNTER"),
            "budget": os.environ.get("THM_RECALL_BUDGET"),
            "model_path": os.environ.get("THM_RECALL_MODEL_PATH"),
            "model_id": os.environ.get("THM_RECALL_MODEL_ID"),
            "sync_turns": os.environ.get("THM_SYNC_TURNS"),
        }
        merged.update({k: v for k, v in env_map.items() if v not in (None, "")})
        return merged

    def is_available(self):
        try:
            return bool((self._merged_config().get("scope") or "").strip())
        except Exception:
            return False

    def unavailable_reason(self):
        return "" if self.is_available() else "Configure a THM scope with `hermes memory setup` or THM_RECALL_SCOPE."

    def get_config_schema(self):
        return [
            {"key": "scope", "description": "Existing THM retrieval scope", "required": True},
            {"key": "mode", "description": "Recall mode", "default": "sparse",
             "choices": ["sparse", "literal", "hybrid", "dense"]},
            {"key": "budget", "description": "Evidence budget units", "default": 600,
             "type": "integer", "minimum": 0, "maximum": 32768},
            {"key": "sync_turns", "description": "Maintain a derived per-session T2 snapshot",
             "default": False, "type": "boolean"},
        ]

    def save_config(self, values, hermes_home):
        if not isinstance(values, dict):
            raise ValueError("THM config must be a mapping")
        current = self._saved_config(hermes_home)
        current.update(values)
        scope = current.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("scope is required")
        mode = current.get("mode", "sparse")
        if mode not in ("sparse", "literal", "hybrid", "dense"):
            raise ValueError("invalid recall mode")
        budget = current.get("budget", 600)
        if type(budget) is not int or not 0 <= budget <= 32768:
            raise ValueError("budget must be an integer from 0 to 32768")
        current["sync_turns"] = _as_bool(current.get("sync_turns"), False)
        _atomic_json(_profile_config_path(hermes_home), current)

    def initialize(self, session_id, **kwargs):
        home = kwargs.get("hermes_home")
        if not home:
            raise ValueError("Hermes must supply profile-scoped hermes_home")
        with self._lock:
            cfg = self._merged_config(home)
            self.scope = (cfg.get("scope") or "").strip()
            if not self.scope:
                raise ValueError("THM scope is not configured")
            self.session_id = session_id
            self._agent_context = kwargs.get("agent_context") or "primary"
            self.path = Path(home).expanduser().resolve() / "memories" / ".thm" / "recall.sqlite3"
            self.counter = TokenCounter(cfg.get("counter", "utf8_bytes"))
            self.budget = int(cfg.get("budget", 600))
            if not 0 <= self.budget <= 32768:
                raise ValueError("THM budget out of range")
            self.mode = cfg.get("mode", "sparse")
            if self.mode not in ("sparse", "literal", "hybrid", "dense"):
                raise ValueError("invalid THM mode")
            self._sync_turns = _as_bool(cfg.get("sync_turns"), False)
            self.encoder = None
            self.error = None
            model = cfg.get("model_path")
            model_id = cfg.get("model_id")
            if self.mode in ("dense", "hybrid"):
                if not model or not model_id:
                    raise ValueError("dense/hybrid mode requires model_path and model_id")
                self.encoder = SentenceEncoder(model, model_id)
            self.model_id = model_id
            self.last = None
            self._source_refresh_required = False
            if self._index:
                self._index.close()
            self._index = SearchIndex(self.path, self.counter, readonly=True) if self.path.is_file() else None

    def system_prompt_block(self):
        return ""

    def _live_scope(self, session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
        return f"{self.scope}::hermes-live::{digest}"

    def _search_scope(self, scope, query, budget):
        if budget <= 0 or self._index is None:
            return None
        try:
            return self._index.search(scope, query, budget=budget, mode=self.mode,
                                      encoder=self.encoder, model_id=self.model_id)
        except ValueError as exc:
            if "scope not indexed" in str(exc):
                return None
            raise

    def prefetch(self, query, *, session_id=""):
        with self._lock:
            self.last, self.error = None, None
            if session_id and session_id != self.session_id:
                self.error = "session mismatch; call on_session_switch first"
                return ""
            if not isinstance(query, str) or not query.strip() or self.path is None or not self.path.is_file():
                return ""
            try:
                if self._index is None:
                    self._index = SearchIndex(self.path, self.counter, readonly=True)
                pieces, selected, used = [], [], 0
                if self._sync_turns and self.session_id:
                    live_cap = min(self.budget // 3, 256)
                    live = self._search_scope(self._live_scope(self.session_id), query, live_cap)
                    if live and live["context"]:
                        pieces.append(live["context"])
                        selected.extend(live["selected"])
                        used += live["budget_used"]
                base = self._search_scope(self.scope, query, max(0, self.budget - used))
                if base and base["context"]:
                    pieces.append(base["context"])
                    selected.extend(base["selected"])
                    used += base["budget_used"]
                self.last = {"selected": selected, "budget_used": used, "context": "\n\n".join(pieces)}
                return self.last["context"]
            except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
                self.error = str(exc)
                return ""

    def queue_prefetch(self, query, *, session_id=""):
        # THM retrieval is local/current-query-only. Warming on the previous turn's
        # text does not predict the next query, so this hook intentionally performs no work.
        return None

    def _sync_messages(self, messages, session_id):
        if not self._sync_turns or self._agent_context != "primary" or not session_id or not self.path:
            return None
        if not isinstance(messages, list):
            return None
        live_scope = self._live_scope(session_id)
        sid = live_scope.rsplit("::", 1)[-1]
        docs = []
        for order, message in enumerate(messages):
            if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                continue
            if message.get("_compressed_summary"):
                continue
            text = _message_text(message)
            if not text:
                continue
            role = message["role"]
            timestamp = message.get("timestamp") or message.get("_timestamp") or message.get("created_at") or ""
            timestamp = str(timestamp) if timestamp is not None else ""
            docs.append(Document(
                id=f"h-{sid}-{order}-{role}", scope=live_scope, session=session_id,
                order=order, text=text, speaker=role, timestamp=timestamp,
                source=f"harness-turn:hermes:{sid}:{order}:{role}", tier="T2",
            ))
        writer = SearchIndex(self.path, self.counter)
        try:
            result = writer.replace_scope(live_scope, docs)
            if self.encoder is not None and self.model_id:
                writer.embed(live_scope, self.encoder, self.model_id)
            return result
        finally:
            writer.close()

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None):
        with self._lock:
            if self._sync_turns and messages is not None:
                self._sync_messages(messages, session_id or self.session_id)

    def on_session_end(self, messages):
        with self._lock:
            if self._sync_turns:
                self._sync_messages(messages, self.session_id)

    def on_pre_compress(self, messages):
        # Best-effort v1 hook only. THM does not advertise checkpoint API v2.
        with self._lock:
            if self._sync_turns:
                self._sync_messages(messages, self.session_id)
        return ""

    def recall_status(self):
        with self._lock:
            if not self.last or not self.last["selected"]:
                return None
            return RecallStatus(provider_label="THM", count=len(self.last["selected"]))

    def on_session_switch(self, new_session_id, **kwargs):
        with self._lock:
            self.session_id = new_session_id
            self.last = None
            self.error = None

    def get_tool_schemas(self):
        return [{"name": "thm_recall_status", "description": "Return last recall metadata without source text.",
                 "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}]

    def handle_tool_call(self, tool_name, args, **kwargs):
        if tool_name != "thm_recall_status":
            return json.dumps({"error": "unknown THM tool"})
        with self._lock:
            return json.dumps({
                "error": self.error,
                "returned_ids": [x["id"] for x in self.last["selected"]] if self.last else [],
                "usefulness": "unverified",
                "budget_used": self.last["budget_used"] if self.last else 0,
                "source_refresh_required": self._source_refresh_required,
                "sync_turns": self._sync_turns,
            })

    def on_memory_write(self, action, target, content, metadata=None):
        # A native memory write is not a hit and is not silently mirrored as truth.
        with self._lock:
            self.last = None
            self._source_refresh_required = True

    def shutdown(self):
        with self._lock:
            self.last = None
            self.encoder = None
            if self._index:
                self._index.close()
            self._index = None


def register(ctx):
    ctx.register_memory_provider(THMProvider())
