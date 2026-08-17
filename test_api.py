import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from secdaily_data import ArchiveStore, parse_md_sources
from api_server import ThreadingHTTPServer, create_handler
from mcp_server import McpServer


SAMPLE_MD = """# 每日安全资讯（2026-05-28）

- SecurityWeek
  - [LA Metro Cyberattack](https://example.com/metro)
  - [Exploit for CVE-2026-4893](https://example.com/cve)
- 安全牛
  - [MCP 协议的元数据嗅探风险](https://example.com/mcp)
"""

SAMPLE_SUMMARY = """# AI总结 - 2026-05-28

今日重点关注 CVE-2026-4893 与 MCP 风险。
"""


def make_archive(root: Path) -> Path:
    archive = root / "archive"
    day_dir = archive / "2026"
    day_dir.mkdir(parents=True)
    (day_dir / "2026-05-28.md").write_text(SAMPLE_MD, encoding="utf-8")
    (day_dir / "AISummary2026-05-28.md").write_text(SAMPLE_SUMMARY, encoding="utf-8")
    (day_dir / "2026-05-27.md").write_text(
        "# 每日安全资讯（2026-05-27）\n\n- Tenable Blog\n  - [Patch Tuesday](https://example.com/pt)\n",
        encoding="utf-8",
    )
    return archive


class ArchiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = make_archive(Path(self.tmp.name))
        self.store = ArchiveStore(self.archive)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_sources_extracts_cve(self):
        sources = parse_md_sources(SAMPLE_MD)
        self.assertEqual(len(sources), 2)
        articles = sources[0]["articles"]
        self.assertTrue(articles[1]["hasCve"])
        self.assertEqual(articles[1]["cves"], ["CVE-2026-4893"])

    def test_list_dates_and_digest(self):
        dates = self.store.list_dates()
        self.assertEqual([item["date"] for item in dates], ["2026-05-28", "2026-05-27"])
        digest = self.store.get_digest("2026-05-28", page_size=50)
        self.assertEqual(digest["stats"]["totalArticles"], 3)
        self.assertTrue(digest["hasAiSummary"])
        titles = [item["title"] for item in digest["data"]]
        self.assertIn("Exploit for CVE-2026-4893", titles)

    def test_search_and_cves(self):
        found = self.store.search_articles("MCP")
        self.assertEqual(found["pagination"]["totalItems"], 1)
        self.assertIn("MCP", found["data"][0]["title"])
        cves = self.store.search_cves("2026-4893")
        self.assertEqual(cves["pagination"]["totalItems"], 1)
        self.assertEqual(cves["data"][0]["cve"], "CVE-2026-4893")

    def test_missing_digest(self):
        with self.assertRaises(FileNotFoundError):
            self.store.get_digest("2020-01-01")

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            self.store.get_digest("2026/05/28")


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = ArchiveStore(make_archive(Path(self.tmp.name)))
        self.server = McpServer(store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_initialize_and_tools(self):
        init = self.server.handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
        })
        self.assertEqual(init["result"]["serverInfo"]["name"], "secdaily")
        listed = self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [item["name"] for item in listed["result"]["tools"]]
        self.assertIn("secdaily_search", names)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tool_search(self):
        result = self.server.handle({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "secdaily_search", "arguments": {"query": "CVE-2026-4893"}},
        })
        payload = json.loads(result["result"]["content"][0]["text"])
        self.assertGreaterEqual(payload["pagination"]["totalItems"], 1)


class RestApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = ArchiveStore(make_archive(Path(self.tmp.name)))
        handler = create_handler(store, api_key="", host="127.0.0.1", port=0)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _get(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, body

    def test_health_and_search(self):
        status, body = self._get("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["latestDate"], "2026-05-28")
        status, body = self._get("/api/v1/articles?q=MCP")
        self.assertEqual(status, 200)
        self.assertEqual(body["pagination"]["totalItems"], 1)
        status, body = self._get("/api/v1/digest/2026-05-28?cveOnly=true")
        self.assertEqual(status, 200)
        self.assertTrue(all(item["hasCve"] for item in body["data"]))
        status, body = self._get("/api/v1/digest/1999-01-01")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
