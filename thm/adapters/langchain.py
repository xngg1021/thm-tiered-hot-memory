"""LangChain/LangGraph retriever adapter for THM."""
from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, PrivateAttr

from ..harness import HarnessConfig, THMHarnessAdapter


class THMLangChainRetriever(BaseRetriever):
    """Expose budget-packed THM sources through the standard BaseRetriever API."""

    index_path: str
    scope: str
    budget: int = 600
    counter: str = "utf8_bytes"
    mode: str = "sparse"
    neighbors: int = 0
    model_path: str | None = None
    model_id: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
    _adapter: THMHarnessAdapter | None = PrivateAttr(default=None)

    def _core(self) -> THMHarnessAdapter:
        if self._adapter is None:
            self._adapter = THMHarnessAdapter(HarnessConfig(
                db=self.index_path,
                scope=self.scope,
                budget=self.budget,
                counter=self.counter,
                mode=self.mode,
                neighbors=self.neighbors,
                model_path=self.model_path,
                model_id=self.model_id,
            ))
        return self._adapter

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        result = self._core().recall(query)
        common = {
            "thm_scope": result["scope"],
            "thm_generation": result["generation"],
            "thm_mode": result["mode"],
            "thm_budget": result["budget"],
            "thm_budget_used": result["budget_used"],
            "thm_usefulness": "unverified",
        }
        return [
            Document(
                id=row["id"],
                page_content=row["text"],
                metadata={**common, "source": row["source"], "sha256": row["hash"]},
            )
            for row in result["sources"]
        ]

    def close(self) -> None:
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
