"""SECDaily MCP Server（stdio JSON-RPC）。

不额外依赖第三方 MCP SDK，可直接给 Cursor / Claude Desktop 使用。
协议消息走 stdout，日志只写 stderr，避免破坏 MCP 帧。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secdaily_data import DEFAULT_ARCHIVE_DIR, DEFAULT_PAGE_SIZE, ArchiveStore  # noqa: E402

try:
    from config_loader import load_dotenv_if_available
    load_dotenv_if_available()
except Exception:
    pass

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "secdaily"
SERVER_VERSION = "1.0.0"


def log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def make_tools(store: ArchiveStore) -> dict[str, dict[str, Any]]:
    def health() -> dict[str, Any]:
        return store.health()

    def list_dates(year: str = "", limit: int = 30) -> dict[str, Any]:
        data = store.list_dates(year=year or None, limit=limit or 30)
        return {"latest": data[0]["date"] if data else None, "data": data}

    def get_digest(
        date: str = "",
        source: str = "",
        cve_only: bool = False,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        include_markdown: bool = False,
    ) -> dict[str, Any]:
        return store.get_digest(
            date_str=date or None,
            source=source or None,
            cve_only=cve_only,
            page=page,
            page_size=page_size,
            include_markdown=include_markdown,
        )

    def search_articles(
        query: str,
        source: str = "",
        date: str = "",
        date_from: str = "",
        date_to: str = "",
        cve_only: bool = False,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        return store.search_articles(
            query=query,
            source=source or None,
            date=date or None,
            date_from=date_from or None,
            date_to=date_to or None,
            cve_only=cve_only,
            page=page,
            page_size=page_size,
        )

    def search_cves(
        query: str = "",
        date: str = "",
        date_from: str = "",
        date_to: str = "",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        return store.search_cves(
            query=query,
            date=date or None,
            date_from=date_from or None,
            date_to=date_to or None,
            page=page,
            page_size=page_size,
        )

    def get_summary(date: str = "") -> dict[str, Any]:
        return store.get_summary(date or None)

    def list_sources(date: str = "") -> dict[str, Any]:
        return store.list_sources(date or None)

    def analyze_requirement(content: str, use_keyword_analysis: bool = False) -> dict[str, Any]:
        from oneapi import analyze_security_report_fenlei

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            report = analyze_security_report_fenlei(content, use_keyword_analysis=use_keyword_analysis)
        return {"report": report}

    return {
        "secdaily_health": {
            "description": "检查 SECDaily 归档目录是否可用，返回最新日报日期。",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "handler": lambda arguments: health(),
        },
        "secdaily_list_dates": {
            "description": "列出可用的安全资讯日报日期，可按年份过滤。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "year": {"type": "string", "description": "四位年份，如 2026"},
                    "limit": {"type": "integer", "description": "返回条数，默认 30", "default": 30},
                },
                "additionalProperties": False,
            },
            "handler": lambda arguments: list_dates(
                year=str(arguments.get("year") or ""),
                limit=int(arguments.get("limit") or 30),
            ),
        },
        "secdaily_get_digest": {
            "description": "获取某一天的安全资讯日报。date 为空则取最新一天。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD，可空表示最新"},
                    "source": {"type": "string", "description": "按来源名称过滤，支持子串匹配"},
                    "cve_only": {"type": "boolean", "description": "只返回标题含 CVE 的资讯"},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20},
                    "include_markdown": {"type": "boolean", "description": "是否附带原始 Markdown"},
                },
                "additionalProperties": False,
            },
            "handler": lambda arguments: get_digest(
                date=str(arguments.get("date") or ""),
                source=str(arguments.get("source") or ""),
                cve_only=bool(arguments.get("cve_only")),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or DEFAULT_PAGE_SIZE),
                include_markdown=bool(arguments.get("include_markdown")),
            ),
        },
        "secdaily_search": {
            "description": "按关键词搜索历史安全资讯标题、来源、链接或 CVE。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "关键词，如 MCP、勒索、漏洞"},
                    "source": {"type": "string"},
                    "date": {"type": "string", "description": "限定单日 YYYY-MM-DD"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "cve_only": {"type": "boolean"},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: search_articles(
                query=str(arguments.get("query") or ""),
                source=str(arguments.get("source") or ""),
                date=str(arguments.get("date") or ""),
                date_from=str(arguments.get("date_from") or ""),
                date_to=str(arguments.get("date_to") or ""),
                cve_only=bool(arguments.get("cve_only")),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or DEFAULT_PAGE_SIZE),
            ),
        },
        "secdaily_search_cves": {
            "description": "从历史日报标题中检索 CVE 编号。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "CVE 或编号片段，如 2026-4893"},
                    "date": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 20},
                },
                "additionalProperties": False,
            },
            "handler": lambda arguments: search_cves(
                query=str(arguments.get("query") or ""),
                date=str(arguments.get("date") or ""),
                date_from=str(arguments.get("date_from") or ""),
                date_to=str(arguments.get("date_to") or ""),
                page=int(arguments.get("page") or 1),
                page_size=int(arguments.get("page_size") or DEFAULT_PAGE_SIZE),
            ),
        },
        "secdaily_get_summary": {
            "description": "读取某一天的 AI 总结（若已生成 AISummaryYYYY-MM-DD.md）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD，可空表示最新有总结的日期不保证存在"},
                },
                "additionalProperties": False,
            },
            "handler": lambda arguments: get_summary(str(arguments.get("date") or "")),
        },
        "secdaily_list_sources": {
            "description": "列出某日或全站资讯来源及条数。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD；为空则统计全站来源"},
                },
                "additionalProperties": False,
            },
            "handler": lambda arguments: list_sources(str(arguments.get("date") or "")),
        },
        "secdaily_analyze_requirement": {
            "description": "对需求类中文文本做 8 类安全评估。文本需包含“需求”且不少于 20 字。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "需求描述文本"},
                    "use_keyword_analysis": {"type": "boolean", "description": "强制走关键词，不调用 AI"},
                },
                "required": ["content"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: analyze_requirement(
                content=str(arguments.get("content") or ""),
                use_keyword_analysis=bool(arguments.get("use_keyword_analysis")),
            ),
        },
    }


class McpServer:
    def __init__(self, store: ArchiveStore):
        self.tools = make_tools(store)

    def handle(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        if "method" not in message:
            return None
        method = message["method"]
        msg_id = message.get("id")
        params = message.get("params") or {}
        if method.startswith("notifications/") or msg_id is None:
            return None
        try:
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except FileNotFoundError as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "result": text_result(str(exc), is_error=True)}
        except ValueError as exc:
            return {"jsonrpc": "2.0", "id": msg_id, "result": text_result(str(exc), is_error=True)}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            client_version = params.get("protocolVersion") or PROTOCOL_VERSION
            return {
                "protocolVersion": client_version if isinstance(client_version, str) else PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "SECDaily 安全资讯归档工具。"
                    "优先用 secdaily_search / secdaily_get_digest 查资讯，"
                    "用 secdaily_search_cves 查 CVE。"
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in self.tools.items()
                ]
            }
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            spec = self.tools.get(name)
            if not spec:
                raise ValueError(f"未知工具: {name}")
            handler: Callable[[dict[str, Any]], Any] = spec["handler"]
            return text_result(handler(arguments))
        raise ValueError(f"未知方法: {method}")


class StdioFramer:
    """兼容官方 NDJSON 与部分 SDK 使用的 Content-Length 帧。"""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.use_content_length: Optional[bool] = None

    def read(self) -> Optional[dict[str, Any]]:
        while True:
            header_line = self.reader.readline()
            if not header_line:
                return None
            if isinstance(header_line, bytes):
                header_line = header_line.decode("utf-8")
            stripped = header_line.strip()
            if not stripped:
                continue
            if stripped.lower().startswith("content-length:"):
                self.use_content_length = True
                length = int(stripped.split(":", 1)[1].strip())
                while True:
                    line = self.reader.readline()
                    if line in ("", b""):
                        return None
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    if line in ("\r\n", "\n"):
                        break
                raw = self.reader.read(length)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
            if self.use_content_length is None:
                self.use_content_length = False
            return json.loads(stripped)

    def write(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        encoded = data.encode("utf-8")
        if self.use_content_length:
            header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
            self.writer.write(header + encoded)
        else:
            self.writer.write(encoded + b"\n")
        self.writer.flush()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SECDaily MCP Server")
    parser.add_argument("--archive-dir", default=os.getenv("SECDAILY_ARCHIVE_DIR", str(DEFAULT_ARCHIVE_DIR)))
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    store = ArchiveStore(Path(args.archive_dir))
    server = McpServer(store)
    log(f"SECDaily MCP 已启动，归档目录: {store.archive_dir}")
    framer = StdioFramer(sys.stdin.buffer, sys.stdout.buffer)
    while True:
        try:
            message = framer.read()
        except json.JSONDecodeError as exc:
            log(f"JSON 解析失败: {exc}")
            continue
        if message is None:
            break
        response = server.handle(message)
        if response is not None:
            framer.write(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
