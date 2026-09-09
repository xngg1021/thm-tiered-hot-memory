import tempfile
import unittest
from pathlib import Path

from thm.harness import HarnessConfig
from thm.mcp_legacy_server import LEGACY_PROTOCOL, LegacyMCPServer
from thm.retrieval import Document, SearchIndex


class LegacyMCPServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "recall.sqlite3"
        index = SearchIndex(self.db)
        try:
            index.replace_scope(
                "legacy-test",
                [
                    Document(
                        "port",
                        "legacy-test",
                        "synthetic",
                        0,
                        "The legacy MCP test database port is 5439.",
                        speaker="user",
                        source="file:synthetic-legacy",
                        tier="T2",
                    )
                ],
            )
        finally:
            index.close()
        self.server = LegacyMCPServer(
            HarnessConfig(db=str(self.db), scope="legacy-test", budget=600, mode="sparse")
        )

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def request(self, request_id, method, params=None):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        response = self.server.handle(message)
        self.assertIsNotNone(response)
        return response

    def test_initializes_legacy_lifecycle_and_advertises_only_read_tools(self):
        response = self.request(
            1,
            "initialize",
            {
                "protocolVersion": LEGACY_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
            },
        )
        self.assertEqual(response["result"]["protocolVersion"], LEGACY_PROTOCOL)
        self.assertEqual(response["result"]["capabilities"], {"tools": {"listChanged": False}})

        tools = self.request(2, "tools/list", {})["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["thm_recall", "thm_status"])
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in tools))
        self.assertTrue(all("outputSchema" in tool for tool in tools))

    def test_recall_returns_structured_content_and_matching_text_fallback(self):
        response = self.request(
            3,
            "tools/call",
            {"name": "thm_recall", "arguments": {"query": "database port"}},
        )
        result = response["result"]
        self.assertFalse(result["isError"])
        structured = result["structuredContent"]
        self.assertIn("5439", structured["context"])
        self.assertEqual(structured["usefulness"], "unverified")
        self.assertEqual(structured["sources"][0]["source"], "file:synthetic-legacy")
        self.assertIn("5439", result["content"][0]["text"])

    def test_status_is_read_only_and_unknown_tool_is_protocol_error(self):
        status = self.request(
            4,
            "tools/call",
            {"name": "thm_status", "arguments": {}},
        )["result"]["structuredContent"]
        from thm.mcp_legacy_server import STATUS_OUTPUT_SCHEMA
        self.assertLessEqual(set(status), set(STATUS_OUTPUT_SCHEMA['properties']))
        self.assertEqual(status['runtime']['mode'], 'zero-touch')
        self.assertFalse(status["source_writes"])
        self.assertEqual(status["scope"], "legacy-test")

        missing = self.request(
            5,
            "tools/call",
            {"name": "thm_delete", "arguments": {}},
        )
        self.assertEqual(missing["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
