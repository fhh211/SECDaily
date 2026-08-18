# SECDaily API / MCP 调用说明

SECDaily 提供两套只读查询接口，共用 `archive/` 下的 Markdown 日报：

- **REST API**：给脚本、SIEM、内部平台调用
- **MCP**：给 Cursor、Claude Desktop 等 Agent 当工具用

默认不需要额外依赖。API 默认只监听本机 `127.0.0.1:8765`。

归档首页（仓库根目录 `index.html`，或 `archive/index.html`）顶部有 **一键接入** 面板：MCP 配置、API 接口表、curl / PowerShell / Python / 对话示例均可一键复制。

## 一键接入

```bash
git clone https://github.com/shellsec/SECDaily.git
cd SECDaily
```

| 方式 | 怎么接 |
|------|--------|
| **MCP** | 先 `python api_server.py`，配置里填 `http://127.0.0.1:8765/mcp` |
| **REST API** | 同一进程，请求 `http://127.0.0.1:8765/api/v1` |

```json
{
  "mcpServers": {
    "secdaily": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

局域网把 `127.0.0.1` 换成机器 IP，并启动时加 `--host 0.0.0.0`。无网环境仍可用 stdio：`python mcp_server.py`。

## 启动参数

```bash
python api_server.py --host 127.0.0.1 --port 8765 --archive-dir archive
```

同一进程提供 REST 与 MCP：`http://127.0.0.1:8765/api/v1` 和 `http://127.0.0.1:8765/mcp`。

无 HTTP 时可用 stdio：`python mcp_server.py`（由 Cursor 拉起，不要当普通前台程序跑）。

| 变量 | 说明 |
|------|------|
| `SECDAILY_API_HOST` | 监听地址，默认 `127.0.0.1` |
| `SECDAILY_API_PORT` | 端口，默认 `8765` |
| `SECDAILY_ARCHIVE_DIR` | 归档目录，默认项目下 `archive/` |
| `SECDAILY_API_KEY` | 若设置，REST 必须带 `X-API-Key` 或 `Authorization: Bearer <key>` |

开放到局域网时请绑定具体网卡并设置 API Key，不要对公网裸奔。

---

## REST API

Base URL：`http://127.0.0.1:8765/api/v1`  
OpenAPI：`GET /api/v1/openapi.json`

列表接口里，**只有搜索需要分页**：`/articles`、`/cves` 使用 `page`（从 1 起）、`pageSize`（默认 20，最大 100）。

`GET /digest` 是某一天的完整日报，默认返回当天全部条目，不要按 20 条截断。只有调用方显式传 `pageSize` 时才切片。

`GET /dates` 默认返回全部日期；`limit` / `pageSize` 只影响返回条数，`pagination.totalItems` 仍是真实总数。

### 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查、最新日期 |
| GET | `/dates` | 可用日报日期 |
| GET | `/digest` | 最新一天日报 |
| GET | `/digest/{date}` | 指定日期日报 |
| GET | `/articles` | 关键词搜索（`/search` 为别名） |
| GET | `/cves` | 从标题中检索 CVE |
| GET | `/sources` | 来源列表 |
| GET | `/summary` | 最新一天 AI 总结（若存在） |
| GET | `/summary/{date}` | 指定日期 AI 总结 |
| POST | `/analyze` | 需求文本 8 类安全评估 |
| POST | `/reload` | 重载搜索索引缓存 |

MCP 不走 `/api/v1` 前缀：`GET/POST /mcp`。

错误体：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "未找到 2020-01-01 的日报"
  }
}
```

| HTTP | code |
|------|------|
| 400 | `VALIDATION_ERROR` |
| 401 | `UNAUTHORIZED` |
| 404 | `NOT_FOUND` |
| 500 | `INTERNAL_ERROR` |

资讯条目字段：`title`、`url`、`source`、`date`、`cves`、`hasCve`。

### curl 示例

```bash
python api_server.py

# 健康检查
curl http://127.0.0.1:8765/api/v1/health

# 最近 7 天日期
curl "http://127.0.0.1:8765/api/v1/dates?year=2026&limit=7"

# 最新日报 / 指定日期（只要 CVE）
curl http://127.0.0.1:8765/api/v1/digest
curl "http://127.0.0.1:8765/api/v1/digest/2026-05-28?cveOnly=true"
curl "http://127.0.0.1:8765/api/v1/digest/2026-05-28?source=SecurityWeek"

# 关键词搜索
curl "http://127.0.0.1:8765/api/v1/articles?q=MCP&from=2026-04-01&to=2026-05-28&pageSize=5"

# CVE
curl "http://127.0.0.1:8765/api/v1/cves?q=2026-4893"

# 来源与 AI 总结
curl "http://127.0.0.1:8765/api/v1/sources?date=2026-05-28"
curl http://127.0.0.1:8765/api/v1/summary/2025-12-03

# 需求评估（文本需包含「需求」且不少于 20 字）
curl -X POST http://127.0.0.1:8765/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"需求：用户注册登录并绑定银行卡支付\",\"useKeywordAnalysis\":true}"

# 可选 API Key
curl -H "X-API-Key: your-secret" http://127.0.0.1:8765/api/v1/health
```

### PowerShell 示例

```powershell
python api_server.py
Invoke-RestMethod http://127.0.0.1:8765/api/v1/health
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/articles?q=勒索&pageSize=5"
(Invoke-RestMethod "http://127.0.0.1:8765/api/v1/cves?q=2026-4893").data
Invoke-RestMethod -Method Post http://127.0.0.1:8765/api/v1/analyze `
  -ContentType "application/json" `
  -Body '{"content":"需求：用户注册登录并绑定银行卡支付","useKeywordAnalysis":true}'
```

### Python 示例

```python
import requests

base = "http://127.0.0.1:8765/api/v1"
print(requests.get(f"{base}/health").json()["latestDate"])

digest = requests.get(f"{base}/digest", params={"cveOnly": True}).json()
print(digest["date"], digest["stats"], len(digest["data"]))

news = requests.get(f"{base}/articles", params={"q": "MCP", "pageSize": 5}).json()
for item in news["data"]:
    print(item["date"], item["title"], item["url"])

cves = requests.get(f"{base}/cves", params={"q": "2026-4893"}).json()
print(cves["pagination"]["totalItems"], cves["data"])
```

### JavaScript 示例

```javascript
const base = 'http://127.0.0.1:8765/api/v1';
const health = await fetch(`${base}/health`).then((r) => r.json());
const news = await fetch(`${base}/articles?q=MCP&pageSize=5`).then((r) => r.json());
console.log(health.latestDate, news.data);
```

`GET /dates` 参数：`year`（四位年份）；可选 `page`、`pageSize` / `limit`（只切返回条数，不改 `totalItems`）。  
`GET /digest` 参数：`source`、`cveOnly`、`includeMarkdown`；可选 `page`、`pageSize`（不传则当天全部）。  
`GET /articles` 参数：`q`、`source`、`date`、`from`、`to`、`cveOnly`、`page`、`pageSize`。  
`GET /cves` 的 `q` 可以是 `CVE-2026-4893` 或 `2026-4893`。

---

## MCP

### Cursor / Claude Desktop

先启动 `python api_server.py`，配置默认指向本机 IP：

```json
{
  "mcpServers": {
    "secdaily": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

局域网示例：`http://192.168.1.10:8765/mcp`（服务端 `--host 0.0.0.0`）。

仓库已带 `.cursor/mcp.json`。无 HTTP 服务时才用 stdio：

```json
{
  "mcpServers": {
    "secdaily": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "<SECDaily仓库根目录>"
    }
  }
}
```

### 工具列表

| 工具 | 作用 |
|------|------|
| `secdaily_health` | 检查归档是否可用 |
| `secdaily_list_dates` | 列出日报日期 |
| `secdaily_get_digest` | 取某一天日报 |
| `secdaily_search` | 关键词搜索资讯 |
| `secdaily_search_cves` | 按 CVE 检索 |
| `secdaily_get_summary` | 读取 AI 总结 |
| `secdaily_list_sources` | 来源列表 |
| `secdaily_analyze_requirement` | 需求文本安全评估 |

### 对话示例

在 Cursor / Claude 里可以直接说：

```
用 secdaily 查最近关于 MCP 的资讯
用 secdaily_get_digest 看今天的安全日报，只要含 CVE 的
用 secdaily_search_cves 查 CVE-2026-4893
用 secdaily_list_sources 列出 2026-05-28 的资讯来源
用 secdaily_get_summary 读取最近一份 AI 总结
```

### 工具参数示例

```json
{"query": "MCP", "date_from": "2026-04-01", "date_to": "2026-05-28", "page_size": 10}
```

```json
{"date": "2026-05-28", "cve_only": true, "page_size": 20}
```

```json
{"query": "2026-4893"}
```

---

## 数据从哪来

接口只读本地 `archive/YYYY/YYYY-MM-DD.md`。没有跑过抓取、也没有历史归档时，日期列表为空。

搜索会优先用 `archive/search-index.json`（`convert_today.py` / `scripts/build_archive_site.py` 生成）；没有该文件时会扫描全部 Markdown 并缓存到内存。归档更新后可 `POST /api/v1/reload`，或重启进程。

## 自测

```bash
python test_api.py
```
