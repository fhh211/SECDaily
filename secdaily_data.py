"""SECDaily 归档查询层：供 REST API 与 MCP 共用。"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CVE_RE = re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE)
ARTICLE_LINK_RE = re.compile(r"^\s+-\s+\[(.+?)\]\((.+?)\)")
TOP_LEVEL_ITEM_RE = re.compile(r"^-\s+(.+)$")
SOURCE_H2_RE = re.compile(r"^##\s+(.+)$")
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE_DIR = ROOT / "archive"


def validate_date(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not DATE_RE.match(text):
        raise ValueError(f"日期格式无效，应为 YYYY-MM-DD: {text}")
    return text


def extract_cves(text: str) -> list[str]:
    seen = []
    for match in CVE_RE.findall(text or ""):
        cve = match.upper()
        if cve not in seen:
            seen.append(cve)
    return seen


def paginate(
    items: list[Any],
    page: int = 1,
    page_size: Optional[int] = None,
    max_size: int = MAX_PAGE_SIZE,
) -> tuple[list[Any], dict[str, int]]:
    total = len(items)
    if page_size is None or int(page_size) <= 0:
        return items, {
            "page": 1,
            "pageSize": total,
            "totalItems": total,
            "totalPages": 1 if total else 0,
        }
    page = max(1, int(page or 1))
    page_size = min(max_size, max(1, int(page_size)))
    start = (page - 1) * page_size
    sliced = items[start : start + page_size]
    total_pages = (total + page_size - 1) // page_size if total else 0
    return sliced, {
        "page": page,
        "pageSize": page_size,
        "totalItems": total,
        "totalPages": total_pages,
    }


def parse_md_sources(md_content: str) -> list[dict[str, Any]]:
    """将 Markdown 日报解析为按来源分组的结构（与 convert_today.parse_md_sources 对齐）。"""
    sources: list[dict[str, Any]] = []
    current_source: Optional[dict[str, Any]] = None

    def append_article(title: str, url: str) -> None:
        nonlocal current_source
        if not title or not url:
            return
        if current_source is None:
            current_source = {"name": "未分类", "articles": []}
            sources.append(current_source)
        cves = extract_cves(title)
        current_source["articles"].append({
            "title": title.strip(),
            "url": url.strip(),
            "cves": cves,
            "hasCve": bool(cves),
        })

    for line in md_content.split("\n"):
        if line.startswith("# "):
            continue

        h2_match = SOURCE_H2_RE.match(line)
        if h2_match:
            name = h2_match.group(1).strip() or "未命名来源"
            current_source = {"name": name, "articles": []}
            sources.append(current_source)
            continue

        if line.startswith("  - "):
            article_match = ARTICLE_LINK_RE.match(line)
            if article_match:
                append_article(article_match.group(1), article_match.group(2))
            continue

        top_match = TOP_LEVEL_ITEM_RE.match(line)
        if top_match and not line.startswith("  "):
            content = top_match.group(1).strip()
            if content.startswith("[") and "](" in content:
                append_article(content.split("](")[0][1:], content.split("](")[1].rstrip(")"))
            elif content:
                current_source = {"name": content, "articles": []}
                sources.append(current_source)

    return sources


def flatten_articles(sources: list[dict[str, Any]], date_str: str, page_path: str = "") -> list[dict[str, Any]]:
    articles = []
    for source in sources:
        for article in source["articles"]:
            item = {
                "title": article["title"],
                "url": article["url"],
                "source": source["name"],
                "date": date_str,
                "cves": article.get("cves") or extract_cves(article["title"]),
                "hasCve": bool(article.get("hasCve") or article.get("cves")),
            }
            if page_path:
                item["page"] = page_path
            articles.append(item)
    return articles


class ArchiveStore:
    """读取 archive/ 下的 Markdown 日报与 AI 总结。"""

    def __init__(self, archive_dir: Optional[Path] = None):
        self.archive_dir = Path(archive_dir or DEFAULT_ARCHIVE_DIR).resolve()
        self._lock = threading.Lock()
        self._articles: Optional[list[dict[str, Any]]] = None
        self._loaded_at: Optional[str] = None

    def health(self) -> dict[str, Any]:
        dates = self.list_dates(limit=1)
        latest = dates[0]["date"] if dates else None
        return {
            "status": "ok" if self.archive_dir.exists() else "degraded",
            "archiveDir": str(self.archive_dir),
            "archiveExists": self.archive_dir.exists(),
            "latestDate": latest,
            "dateCount": len(self.list_dates()),
            "indexLoaded": self._articles is not None,
            "indexSize": len(self._articles) if self._articles is not None else 0,
            "loadedAt": self._loaded_at,
        }

    def digest_path(self, date_str: str) -> Path:
        year = date_str[:4]
        return self.archive_dir / year / f"{date_str}.md"

    def summary_path(self, date_str: str) -> Path:
        year = date_str[:4]
        return self.archive_dir / year / f"AISummary{date_str}.md"

    def list_dates(self, year: Optional[str] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
        if not self.archive_dir.exists():
            return []
        items = []
        year_dirs: Iterable[Path]
        if year:
            if not re.match(r"^\d{4}$", year):
                raise ValueError(f"年份格式无效: {year}")
            year_dirs = [self.archive_dir / year]
        else:
            year_dirs = sorted(
                (p for p in self.archive_dir.iterdir() if p.is_dir() and p.name.isdigit()),
                reverse=True,
            )
        for year_dir in year_dirs:
            if not year_dir.exists():
                continue
            for md_file in year_dir.glob("*.md"):
                if md_file.name.startswith("AISummary"):
                    continue
                date_str = md_file.stem
                if not DATE_RE.match(date_str):
                    continue
                items.append({
                    "date": date_str,
                    "year": date_str[:4],
                    "hasAiSummary": self.summary_path(date_str).exists(),
                })
        items.sort(key=lambda item: item["date"], reverse=True)
        if limit:
            items = items[: max(1, int(limit))]
        return items

    def latest_date(self) -> Optional[str]:
        dates = self.list_dates(limit=1)
        return dates[0]["date"] if dates else None

    def resolve_date(self, date_str: Optional[str]) -> str:
        if not date_str or date_str in {"latest", "today"}:
            latest = self.latest_date()
            if not latest:
                raise FileNotFoundError("归档中没有任何日报")
            return latest
        return validate_date(date_str)  # type: ignore[return-value]

    def get_digest(
        self,
        date_str: Optional[str] = None,
        source: Optional[str] = None,
        cve_only: bool = False,
        page: int = 1,
        page_size: Optional[int] = None,
        include_markdown: bool = False,
    ) -> dict[str, Any]:
        date_str = self.resolve_date(date_str)
        path = self.digest_path(date_str)
        if not path.exists():
            raise FileNotFoundError(f"未找到 {date_str} 的日报")
        md_content = path.read_text(encoding="utf-8")
        sources = parse_md_sources(md_content)
        articles = flatten_articles(sources, date_str, f"{date_str[:4]}/{date_str}.html")
        if source:
            needle = source.strip().lower()
            articles = [item for item in articles if needle in item["source"].lower()]
            sources = [item for item in sources if needle in item["name"].lower()]
        if cve_only:
            articles = [item for item in articles if item["hasCve"]]
        page_data, pagination = paginate(articles, page, page_size)
        stats = {
            "totalArticles": len(articles),
            "totalSources": len({item["source"] for item in articles}),
            "cveCount": sum(1 for item in articles if item["hasCve"]),
        }
        result: dict[str, Any] = {
            "date": date_str,
            "title": f"每日安全资讯（{date_str}）",
            "hasAiSummary": self.summary_path(date_str).exists(),
            "stats": stats,
            "sources": [{"name": item["name"], "articleCount": len(item["articles"])} for item in sources],
            "data": page_data,
            "pagination": pagination,
        }
        if include_markdown:
            result["markdown"] = md_content
        return result

    def get_summary(self, date_str: Optional[str] = None) -> dict[str, Any]:
        date_str = self.resolve_date(date_str)
        path = self.summary_path(date_str)
        if not path.exists():
            raise FileNotFoundError(f"未找到 {date_str} 的 AI 总结")
        return {
            "date": date_str,
            "exists": True,
            "content": path.read_text(encoding="utf-8"),
        }

    def list_sources(self, date_str: Optional[str] = None) -> dict[str, Any]:
        if date_str:
            digest = self.get_digest(date_str, page=1, page_size=1)
            return {"date": digest["date"], "data": digest["sources"]}
        counts: dict[str, int] = {}
        for article in self._load_articles():
            name = article["source"]
            counts[name] = counts.get(name, 0) + 1
        data = [
            {"name": name, "articleCount": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {"date": None, "data": data}

    def search_articles(
        self,
        query: str = "",
        source: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        date: Optional[str] = None,
        cve_only: bool = False,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        date_from = validate_date(date_from)
        date_to = validate_date(date_to)
        date = validate_date(date)
        needle = (query or "").strip().lower()
        source_needle = (source or "").strip().lower()
        matched = []
        for article in self._load_articles():
            if date and article["date"] != date:
                continue
            if date_from and article["date"] < date_from:
                continue
            if date_to and article["date"] > date_to:
                continue
            if source_needle and source_needle not in article["source"].lower():
                continue
            if cve_only and not article["hasCve"]:
                continue
            if needle:
                haystack = " ".join([
                    article["title"],
                    article["source"],
                    article["url"],
                    " ".join(article.get("cves") or []),
                ]).lower()
                if needle not in haystack:
                    continue
            matched.append(article)
        page_data, pagination = paginate(matched, page, page_size)
        return {
            "query": query,
            "data": page_data,
            "pagination": pagination,
        }

    def search_cves(
        self,
        query: str = "",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        date: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        date_from = validate_date(date_from)
        date_to = validate_date(date_to)
        date = validate_date(date)
        needle = (query or "").strip().upper()
        if needle and not needle.startswith("CVE-"):
            needle = f"CVE-{needle}" if needle[0].isdigit() else needle
        matched = []
        for article in self._load_articles():
            if not article.get("cves"):
                continue
            if date and article["date"] != date:
                continue
            if date_from and article["date"] < date_from:
                continue
            if date_to and article["date"] > date_to:
                continue
            cves = article["cves"]
            if needle:
                cves = [cve for cve in cves if needle in cve]
                if not cves:
                    continue
            for cve in cves:
                matched.append({
                    "cve": cve,
                    "title": article["title"],
                    "url": article["url"],
                    "source": article["source"],
                    "date": article["date"],
                })
        page_data, pagination = paginate(matched, page, page_size)
        return {
            "query": query,
            "data": page_data,
            "pagination": pagination,
        }

    def reload(self) -> dict[str, Any]:
        with self._lock:
            self._articles = None
            self._loaded_at = None
        count = len(self._load_articles())
        return {"reloaded": True, "indexSize": count, "loadedAt": self._loaded_at}

    def _load_articles(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._articles is not None:
                return self._articles
            articles = self._read_search_index()
            if articles is None:
                articles = self._scan_markdown()
            self._articles = articles
            self._loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return self._articles

    def _read_search_index(self) -> Optional[list[dict[str, Any]]]:
        index_file = self.archive_dir / "search-index.json"
        if not index_file.exists():
            return None
        try:
            payload = json.loads(index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        raw_articles = payload.get("articles")
        if not isinstance(raw_articles, list):
            return None
        normalized = []
        for item in raw_articles:
            title = str(item.get("title") or "")
            cves = extract_cves(title)
            normalized.append({
                "title": title,
                "url": str(item.get("url") or ""),
                "source": str(item.get("source") or "未分类"),
                "date": str(item.get("date") or ""),
                "page": str(item.get("page") or ""),
                "cves": cves,
                "hasCve": bool(cves),
            })
        normalized.sort(key=lambda item: (item["date"], item["title"]), reverse=True)
        return normalized

    def _scan_markdown(self) -> list[dict[str, Any]]:
        articles: list[dict[str, Any]] = []
        if not self.archive_dir.exists():
            return articles
        for md_file in sorted(self.archive_dir.rglob("*.md")):
            if md_file.name.startswith("AISummary"):
                continue
            date_str = md_file.stem
            if not DATE_RE.match(date_str):
                continue
            try:
                md_content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            rel_page = md_file.with_suffix(".html").relative_to(self.archive_dir).as_posix()
            sources = parse_md_sources(md_content)
            articles.extend(flatten_articles(sources, date_str, rel_page))
        articles.sort(key=lambda item: (item["date"], item["title"]), reverse=True)
        return articles
