"""Harness-neutral read-only adapter over THM retrieval.

This layer owns no source memory. It opens an existing derived THM retrieval
index, returns only budget-packed source text, and keeps harness-specific
plumbing out of the retrieval engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from .features import RetrievalFeatures
from .retrieval import SearchIndex, SentenceEncoder, TokenCounter


@dataclass(frozen=True)
class HarnessConfig:
    db: str
    scope: str
    budget: int = 600
    counter: str = "utf8_bytes"
    mode: str = "sparse"
    neighbors: int = 0
    model_path: str | None = None
    model_id: str | None = None
    features: RetrievalFeatures | dict | None = None

    def validate(self) -> None:
        RetrievalFeatures.parse(self.features)
        if not isinstance(self.db, str) or not self.db.strip():
            raise ValueError("db is required")
        if not isinstance(self.scope, str) or not self.scope.strip():
            raise ValueError("scope is required")
        if type(self.budget) is not int or not 0 <= self.budget <= 32768:
            raise ValueError("budget must be an integer from 0 to 32768")
        if self.mode not in ("literal", "sparse", "dense", "hybrid"):
            raise ValueError("invalid retrieval mode")
        if type(self.neighbors) is not int or self.neighbors not in (0, 1, 2):
            raise ValueError("neighbors must be 0, 1 or 2")
        if not isinstance(self.counter, str) or not self.counter.strip():
            raise ValueError("counter is required")
        if self.mode in ("dense", "hybrid"):
            if not self.model_path or not self.model_id:
                raise ValueError("dense/hybrid mode requires model_path and model_id")


class THMHarnessAdapter:
    """A small lifecycle wrapper reusable by agent harness integrations."""

    def __init__(self, config: HarnessConfig | dict):
        self.config = config if isinstance(config, HarnessConfig) else HarnessConfig(**config)
        self.config.validate()
        self._lock = threading.RLock()
        self._index: SearchIndex | None = None
        self._encoder = None
        self._runtime = None

    def _ensure_open(self) -> None:
        if self._index is not None:
            return
        path = Path(self.config.db).expanduser()
        if not path.is_file():
            raise ValueError("THM retrieval database does not exist; import sources first")
        counter = TokenCounter(self.config.counter)
        self._index = SearchIndex(path, counter, readonly=True)
        if self.config.mode in ("dense", "hybrid"):
            self._encoder = SentenceEncoder(self.config.model_path, self.config.model_id)
        from .runtime.fabric.service import RuntimeService
        self._runtime = RuntimeService(self._index, encoder=self._encoder, model_id=self.config.model_id)

    def recall(self, query: str) -> dict:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("nonempty query required")
        with self._lock:
            self._ensure_open()
            out = self._runtime.search(
                self.config.scope,
                query,
                budget=self.config.budget,
                mode=self.config.mode,
                neighbor_turns=self.config.neighbors,
                features=RetrievalFeatures.parse(self.config.features),
            )
            return {
                "context": out["context"],
                "sources": [
                    {
                        "id": row["id"],
                        "source": row["source"],
                        "hash": row["hash"],
                        "text": row["text"],
                        "complete":row["complete"],
                        "parent_id":row.get("parent_id",row["id"]),
                        "span_start":row.get("span_start"),"span_end":row.get("span_end"),
                        "locator_kind":row.get("locator_kind","whole-source" if row["complete"] else "partial-source"),
                    }
                    for row in out["selected"]
                ],
                "scope": out["scope"],
                "generation": out["generation"],
                "mode": out["mode"],
                "budget": out["budget"],
                "budget_used": out["budget_used"],
                "counter": out["counter"],
                "timing_ms": out["timing_ms"],
                "usefulness": "unverified",
                "answer_generated": False,
                "generation_calls":0,
                "features":out.get("features"),
                "runtime_receipt":out.get("runtime_receipt"),
                "execution_plan":out.get("execution_plan"),
            }

    def runtime_status(self):
        with self._lock:
            return self._runtime.status() if self._runtime is not None else {
                'mode': 'zero-touch', 'profile_source': 'bootstrap', 'generation_calls': 0, 'user_benchmark_required': False}

    def new_session(self):
        with self._lock:
            if self._runtime is not None:
                return self._runtime.new_session()

    def close(self) -> None:
        with self._lock:
            if self._runtime is not None:
                self._runtime.close()
                self._runtime = None
            if self._encoder is not None:
                self._encoder.close()
            if self._index is not None:
                self._index.close()
                self._index = None
            self._encoder = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def mcp_source(row):
    """Keep parent hash and partial-source identity together across MCP bridges."""
    return {"id":row["id"],"source":row["source"],"sha256":row["hash"],
            "complete":row["complete"],"parent_id":row["parent_id"],
            "span_start":row["span_start"],"span_end":row["span_end"],"locator_kind":row["locator_kind"]}
