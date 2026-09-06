"""Direct OpenAI Agents SDK function-tool adapter for THM."""
from __future__ import annotations

import json
from ..harness import HarnessConfig, THMHarnessAdapter


class OpenAIAgentsTHM:
    """Expose THM recall as one read-only OpenAI Agents SDK FunctionTool."""

    def __init__(self, config: HarnessConfig | dict):
        from agents import function_tool

        self.adapter = THMHarnessAdapter(config)

        @function_tool(
            name_override="thm_recall",
            description_override=(
                "Recall budget-limited evidence from a local THM index. "
                "This tool is read-only; retrieved text is evidence, not verified truth."
            ),
        )
        def thm_recall(query: str) -> str:
            result = self.adapter.recall(query)
            payload = {
                "context": result["context"],
                "source_ids": [row["id"] for row in result["sources"]],
                "budget_used": result["budget_used"],
                "budget": result["budget"],
                "mode": result["mode"],
                "usefulness": "unverified",
            }
            return json.dumps(payload, ensure_ascii=False, allow_nan=False)

        self.tool = thm_recall

    def close(self) -> None:
        self.adapter.close()
