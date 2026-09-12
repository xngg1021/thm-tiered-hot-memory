"""LangGraph nodes and Deep Agents tools over the canonical read-only harness."""
from ..harness import THMHarnessAdapter


class THMGraphNode:
    def __init__(self, config, *, query_key='query', output_key='memory_evidence'):
        self.adapter = THMHarnessAdapter(config)
        self.query_key, self.output_key = query_key, output_key

    def __call__(self, state):
        if not isinstance(state, dict) or self.query_key not in state:
            raise ValueError('graph state requires an explicit query')
        return {self.output_key: self.adapter.recall(state[self.query_key]),
                'thm_runtime_status': self.adapter.runtime_status()}

    def new_session(self):
        return self.adapter.new_session()

    def close(self):
        self.adapter.close()


def deep_agents_tools(config):
    """Returns a standard LangChain tool list and its caller-owned lifecycle."""
    from langchain_core.tools import tool
    node = THMGraphNode(config)
    @tool
    def thm_recall(query: str) -> dict:
        """Retrieve bounded local source evidence without changing memory authority."""
        return node.adapter.recall(query)
    @tool
    def thm_status() -> dict:
        """Inspect provider, session operating point and fallback status."""
        return node.adapter.runtime_status()
    return [thm_recall, thm_status], node
