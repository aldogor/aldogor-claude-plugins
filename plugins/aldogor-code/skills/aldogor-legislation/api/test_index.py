"""Offline tests of the connector in index.py: the command lines it builds, its error reporting, and the HTTP
endpoint behind the secret path. No network: legislation.main is replaced where a test would reach a source.

Run from the skill folder, with the packages of requirements.txt installed:
  python -m unittest api/test_index.py
"""

import importlib
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def load(secret: str):
    """Import index.py afresh with LEGISLATION_MCP_SECRET set to secret ("" for none)."""
    with mock.patch.dict(os.environ, {"LEGISLATION_MCP_SECRET": secret}):
        import index
        return importlib.reload(index)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.index = load("")

    def captured(self, tool, **kwargs) -> list:
        """The argv a tool hands to legislation.main."""
        seen = []
        with mock.patch.object(self.index.legislation, "main", lambda argv: seen.append(argv) or 0):
            tool(**kwargs)
        return seen[0]

    def test_flags_skip_none_and_false_and_keep_true(self):
        argv = self.captured(self.index.eu_text, ref="32016R0679", article="9", toc=True)
        self.assertEqual(argv, ["eu-text", "32016R0679", "--article", "9", "--toc", "--lang", "ITA"])

    def test_article_at_a_date_and_underscored_flags(self):
        argv = self.captured(self.index.it_article, article="2-ter", type="DLGS", year=2003, number="196",
                             date="2017-01-01", gu_date="2003-07-29")
        self.assertEqual(argv, ["it-article", "--type", "DLGS", "--year", "2003", "--number", "196",
                                "--gu-date", "2003-07-29", "--article", "2-ter", "--date", "2017-01-01"])

    def test_pie_search_passes_the_in_flag(self):
        argv = self.captured(self.index.pie_search, words="vaccinazioni", within="text")
        self.assertEqual(argv, ["pie-search", "vaccinazioni", "--in", "text"])

    def test_a_failure_is_reported_with_its_message(self):
        def failing(argv):
            print("Error: Normattiva did not answer", file=sys.stderr)
            return 1

        with mock.patch.object(self.index.legislation, "main", failing):
            text = self.index.smoke()
        self.assertIn("Failed (exit 1): Error: Normattiva did not answer", text)

    def test_a_wrong_argument_is_reported_not_raised(self):
        text = self.index.it_article(article="2-ter", date="2017-01-01", year="not a year")
        self.assertIn("Failed (exit 2)", text)


class EndpointTest(unittest.TestCase):
    def post(self, client, path, payload):
        return client.post(path, json=payload, headers={"Accept": "application/json, text/event-stream"})

    def test_tools_listed_on_the_secret_path_only(self):
        from starlette.testclient import TestClient

        index = load("s3cret")
        with TestClient(index.app) as client:
            init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
            self.assertEqual(self.post(client, "/s3cret/mcp", init).status_code, 200)
            listed = self.post(client, "/s3cret/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            names = {tool["name"] for tool in json.loads(listed.text)["result"]["tools"]}
            self.assertIn("it_article", names)
            self.assertEqual(len(names), 10)
            self.assertEqual(self.post(client, "/mcp", init).status_code, 404)
            # the shape of a request after Vercel's rewrite: the function's own path, the called one in the query
            self.assertEqual(self.post(client, "/api/index?vercel_path=s3cret/mcp", init).status_code, 200)
            self.assertEqual(self.post(client, "/api/index?vercel_path=mcp", init).status_code, 404)


if __name__ == "__main__":
    unittest.main()
