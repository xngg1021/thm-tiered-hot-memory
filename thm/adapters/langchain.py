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
    features: dict | None = None

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
                features=self.features,
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
            "runtime_receipt": result.get("runtime_receipt"),
            "execution_plan": result.get("execution_plan"),
        }
        return [
            Document(
                id=row["id"],
                page_content=row["text"],
                metadata={**common, "source": row["source"], "sha256": row["hash"],
                          **{k: row.get(k) for k in ('complete', 'parent_id', 'span_start', 'span_end', 'locator_kind')}},
            )
            for row in result["sources"]
        ]

    def runtime_status(self):
        return self._core().runtime_status()

    def new_session(self):
        return self._core().new_session()

    def close(self) -> None:
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
