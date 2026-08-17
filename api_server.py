"""SECDaily REST API：查询日报、搜索资讯/CVE、读取 AI 总结。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secdaily_data import (  # noqa: E402
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_PAGE_SIZE,
    ArchiveStore,
)

try:
    from config_loader import load_dotenv_if_available
    load_dotenv_if_available()
except Exception:
    pass

API_PREFIX = "/api/v1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def json_bytes(payload: Any, status: int = 200) -> tuple[int, bytes]:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return status, body


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def first_query(params: dict[str, list[str]], *names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        values = params.get(name)
        if values and values[0] != "":
            return values[0]
    return default


def as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def as_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def openapi_spec(host: str, port: int) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "SECDaily API",
            "version": "1.0.0",
            "description": "安全资讯日报查询接口：日报、搜索、CVE、AI 总结。",
        },
        "servers": [{"url": f"http://{host}:{port}{API_PREFIX}"}],
        "paths": {
            "/health": {"get": {"summary": "健康检查"}},
            "/dates": {"get": {"summary": "可用日报日期列表"}},
            "/digest": {"get": {"summary": "最新或指定日期日报"}},
            "/digest/{date}": {"get": {"summary": "指定日期日报"}},
            "/articles": {"get": {"summary": "按关键词/来源/日期搜索资讯"}},
            "/search": {"get": {"summary": "articles 的别名"}},
            "/cves": {"get": {"summary": "搜索标题中的 CVE"}},
            "/sources": {"get": {"summary": "来源列表"}},
            "/summary": {"get": {"summary": "最新或指定日期 AI 总结"}},
            "/summary/{date}": {"get": {"summary": "指定日期 AI 总结"}},
            "/analyze": {"post": {"summary": "安全需求文本分析"}},
            "/reload": {"post": {"summary": "重载搜索索引缓存"}},
            "/openapi.json": {"get": {"summary": "OpenAPI 描述"}},
        },
    }


class SecDailyAPIHandler(BaseHTTPRequestHandler):
    store: ArchiveStore
    api_key: str = ""
    server_host: str = DEFAULT_HOST
    server_port: int = DEFAULT_PORT

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", content_type="text/plain")

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _auth_ok(self) -> bool:
        expected = self.api_key
        if not expected:
            return True
        header_key = self.headers.get("X-API-Key", "")
        auth = self.headers.get("Authorization", "")
        bearer = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else ""
        return header_key == expected or bearer == expected

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query, keep_blank_values=False)

        if path in {"/", "/api", API_PREFIX}:
            status, body = json_bytes({
                "name": "SECDaily API",
                "version": "1.0.0",
                "docs": "/api/v1/openapi.json",
                "endpoints": [
                    "GET /api/v1/health",
                    "GET /api/v1/dates",
                    "GET /api/v1/digest",
                    "GET /api/v1/digest/{date}",
                    "GET /api/v1/articles",
                    "GET /api/v1/cves",
                    "GET /api/v1/sources",
                    "GET /api/v1/summary/{date}",
                    "POST /api/v1/analyze",
                    "POST /api/v1/reload",
                ],
            })
            self._send(status, body)
            return

        if not self._auth_ok():
            status, body = json_bytes(error_body("UNAUTHORIZED", "缺少或无效的 API Key"), 401)
            self._send(status, body)
            return

        try:
            status, body = self._handle(path, params)
        except ValueError as exc:
            status, body = json_bytes(error_body("VALIDATION_ERROR", str(exc)), 400)
        except FileNotFoundError as exc:
            status, body = json_bytes(error_body("NOT_FOUND", str(exc)), 404)
        except json.JSONDecodeError:
            status, body = json_bytes(error_body("VALIDATION_ERROR", "JSON 解析失败"), 400)
        except Exception as exc:  # pragma: no cover - unexpected
            status, body = json_bytes(error_body("INTERNAL_ERROR", "服务器内部错误", str(exc)), 500)
        self._send(status, body)

    def _handle(self, path: str, params: dict[str, list[str]]) -> tuple[int, bytes]:
        store = self.store
        if path == f"{API_PREFIX}/health":
            return json_bytes(store.health())
        if path == f"{API_PREFIX}/openapi.json":
            return json_bytes(openapi_spec(self.server_host, self.server_port))
        if path == f"{API_PREFIX}/dates":
            year = first_query(params, "year")
            limit = first_query(params, "limit")
            data = store.list_dates(year=year, limit=int(limit) if limit else None)
            return json_bytes({
                "latest": data[0]["date"] if data else None,
                "data": data,
                "pagination": {
                    "page": 1,
                    "pageSize": len(data),
                    "totalItems": len(data),
                    "totalPages": 1,
                },
            })
        if path in {f"{API_PREFIX}/digest"} or path.startswith(f"{API_PREFIX}/digest/"):
            date = path[len(f"{API_PREFIX}/digest/") :] if path.startswith(f"{API_PREFIX}/digest/") else first_query(params, "date")
            return json_bytes(store.get_digest(
                date_str=date,
                source=first_query(params, "source"),
                cve_only=as_bool(first_query(params, "cveOnly", "cve_only")),
                page=as_int(first_query(params, "page"), 1),
                page_size=as_int(first_query(params, "pageSize", "page_size"), DEFAULT_PAGE_SIZE),
                include_markdown=as_bool(first_query(params, "includeMarkdown", "include_markdown")),
            ))
        if path in {f"{API_PREFIX}/articles", f"{API_PREFIX}/search"}:
            return json_bytes(store.search_articles(
                query=first_query(params, "q", "query", default="") or "",
                source=first_query(params, "source"),
                date_from=first_query(params, "from", "dateFrom", "date_from"),
                date_to=first_query(params, "to", "dateTo", "date_to"),
                date=first_query(params, "date"),
                cve_only=as_bool(first_query(params, "cveOnly", "cve_only")),
                page=as_int(first_query(params, "page"), 1),
                page_size=as_int(first_query(params, "pageSize", "page_size"), DEFAULT_PAGE_SIZE),
            ))
        if path == f"{API_PREFIX}/cves":
            return json_bytes(store.search_cves(
                query=first_query(params, "q", "query", "cve", default="") or "",
                date_from=first_query(params, "from", "dateFrom", "date_from"),
                date_to=first_query(params, "to", "dateTo", "date_to"),
                date=first_query(params, "date"),
                page=as_int(first_query(params, "page"), 1),
                page_size=as_int(first_query(params, "pageSize", "page_size"), DEFAULT_PAGE_SIZE),
            ))
        if path == f"{API_PREFIX}/sources":
            return json_bytes(store.list_sources(first_query(params, "date")))
        if path in {f"{API_PREFIX}/summary"} or path.startswith(f"{API_PREFIX}/summary/"):
            date = path[len(f"{API_PREFIX}/summary/") :] if path.startswith(f"{API_PREFIX}/summary/") else first_query(params, "date")
            return json_bytes(store.get_summary(date))
        if path == f"{API_PREFIX}/reload" and self.command == "POST":
            return json_bytes(store.reload())
        if path == f"{API_PREFIX}/analyze" and self.command == "POST":
            payload = self._read_json_body()
            content = str(payload.get("content") or "")
            use_keyword = bool(payload.get("useKeywordAnalysis") or payload.get("use_keyword_analysis"))
            from oneapi import analyze_security_report_fenlei
            report = analyze_security_report_fenlei(content, use_keyword_analysis=use_keyword)
            return json_bytes({"report": report})
        return json_bytes(error_body("NOT_FOUND", f"未知接口: {path}"), 404)


def create_handler(store: ArchiveStore, api_key: str, host: str, port: int):
    class BoundHandler(SecDailyAPIHandler):
        pass

    BoundHandler.store = store
    BoundHandler.api_key = api_key
    BoundHandler.server_host = host
    BoundHandler.server_port = port
    return BoundHandler


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SECDaily REST API")
    parser.add_argument("--host", default=os.getenv("SECDAILY_API_HOST", DEFAULT_HOST), help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("SECDAILY_API_PORT", DEFAULT_PORT)), help="端口，默认 8765")
    parser.add_argument("--archive-dir", default=os.getenv("SECDAILY_ARCHIVE_DIR", str(DEFAULT_ARCHIVE_DIR)), help="归档目录")
    parser.add_argument("--api-key", default=os.getenv("SECDAILY_API_KEY", ""), help="可选 API Key，设置后需携带 X-API-Key")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    store = ArchiveStore(Path(args.archive_dir))
    handler = create_handler(store, args.api_key, args.host, args.port)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"SECDaily API 已启动: http://{args.host}:{args.port}{API_PREFIX}")
    print(f"OpenAPI: http://{args.host}:{args.port}{API_PREFIX}/openapi.json")
    print(f"归档目录: {store.archive_dir}")
    if args.api_key:
        print("已启用 API Key 校验（请求头 X-API-Key 或 Authorization: Bearer）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 API 服务")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
