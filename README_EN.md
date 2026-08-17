# SECDaily

[中文](README.md) · [English](README_EN.md)

> Security news RSS daily digest: aggregation, archive, search, and per-item AI analysis  
> **Repo**: [github.com/shellsec/SECDaily](https://github.com/shellsec/SECDaily) · **Issues**: [Issues](https://github.com/shellsec/SECDaily/issues)

## 🚀 Recommended: [ofox.ai](https://ofox.io/x/aiv123)

> **In short**: One account for GPT-5.5 / Claude 4.8 Opus / Gemini 3.5 Flash and **100+** top models. First top-up gets an extra **$3** credit.

[👉 Sign up](https://ofox.io/x/aiv123) · Global dedicated lines · Enterprise SLA · No conversation retention

| ⚡️ Fast & Stable | 🧠 Full Model Coverage | 🛡️ Privacy |
|:---:|:---:|:---:|
| Global dedicated lines, enterprise SLA | 100+ models, one account | No conversation retention |

## ☕ Buy Me a Coke

Open source takes effort — sponsorship is welcome:  
👉 [爱发电 / Afdian](https://ifdian.net/a/shellsec)

## Overview

SECDaily aggregates security-related RSS feeds, produces Markdown/HTML daily digests, and supports optional AI summaries plus multi-channel push. The archive site supports **date browsing**, **site-wide title search** (including CVE / source), in-page filters for a single day, and **one-click AI analysis per article** (ChatGPT / Gemini / DeepSeek, with the analysis prompt copied automatically). You can publish it on GitHub Pages.

## Features

- 🔄 **RSS auto-update**: Checks and refreshes RSS OPML sources so stale remotes do not wipe local data
- 📰 **Multi-source aggregation**: Collects security news from multiple RSS feeds
- 🤖 **AI daily summary** (optional): When enabled, writes `AISummaryYYYY-MM-DD.md` and can push it; requires AI API settings in `.env`
- 🔍 **Requirement keyword analysis** (optional API): `oneapi.analyze_security_report_fenlei` matches 8 security-requirement categories; falls back to keywords without AI; **call it yourself** — not wired into the daily crawl
- 📄 **Multi-format output**: Generates Markdown and HTML digests
- 🔎 **Archive & search**: Static site under `archive/`; home page has date archive + title search; daily pages support title/CVE filters
- 🧠 **Per-item AI analysis**: **ChatGPT → Gemini → DeepSeek** next to each title; copies “title + original URL + structured analysis prompt” and opens the AI
- 🌐 **GitHub Pages**: Deploy the archive via Actions with no extra secrets (see deploy section below)
- 📤 **Multi-channel push**: Feishu, WeCom, DingTalk, Telegram, email, etc. (`config.json` → `bot`)
- ⏰ **Scheduling**: Run on a cron-like daily schedule
- 🛡️ **Safe RSS updates**: Validates remote content before replacing local OPML files
- 🔌 **REST API / MCP**: Query digests, search articles and CVEs from scripts or Cursor / Claude (see [API调用说明.md](API调用说明.md))

**Archive home** (date browse / title search):

<img width="930" alt="Archive home: date browse and title search" src="https://github.com/user-attachments/assets/187e36d9-d7d7-4b83-bd2a-f3d468b826c4" />

**Daily page** (source nav, title filter, word cloud, CVE stats, etc.):

<img width="932" alt="Daily page: article list and filters" src="https://github.com/user-attachments/assets/84b5bfe3-add5-4cc1-b091-96fc3e6bb31a" />

**Per-item AI analysis** (ChatGPT → Gemini → DeepSeek on each title; copy prompt and jump):

<img width="932" alt="Per-item AI analysis buttons" src="https://github.com/user-attachments/assets/9eeb9493-0e92-4194-bb5b-ee4886490b4a" />

## File layout

- `yarb.py`: Main program (scheduling + AI summary)
- `yarb_one.py`: Simplified main entry
- `config.json` / `config.example.json`, `.env.example`: Config and secret templates (**do not commit** `config.json` or `.env`)
- `.github/workflows/pages.yml`: GitHub Pages deploy workflow
- `convert_today.py`: Markdown → HTML; builds archive index and search data
- `index_template.html` / `template.html`: Archive home and daily page templates (header/footer link to the [GitHub repo](https://github.com/shellsec/SECDaily); URL is `SITE_GITHUB_URL` in `convert_today.py`)
- `archive/`: Historical digests (HTML/Markdown) and `search-index.json` (generated in CI)
- `scripts/build_archive_site.py`: Local/CI builder for the archive site and search index
- `oneapi.py`: AI summary helpers
- `bot.py`: Push bots
- `secdaily_data.py`: Archive query layer shared by API and MCP
- `api_server.py`: REST API
- `mcp_server.py`: MCP server (stdio)
- `connect_panel.html`: One-click API / MCP panel on archive pages
- `API调用说明.md` / `mcp.example.json`: API docs and MCP config template
- `rss/`: RSS OPML sources

## Install

```bash
pip install -r requirements.txt
```

Main dependencies:

- `feedparser`: RSS parsing
- `listparser`: OPML parsing
- `requests`: HTTP
- `schedule`: Scheduling
- `markdown`: Markdown conversion
- `jinja2`: HTML templating

## Usage

### Scheduled run

```bash
# Default: run every day at 10:00
python yarb.py

# Run once immediately (for testing)
python yarb.py --force

# Custom time
python yarb.py --cron "11:00"

# Force-refresh RSS sources
python yarb.py --update
```

### Convert HTML manually

```bash
python convert_today.py
```

Builds today’s HTML and updates `archive/index.html`, `search-index.json` (site-wide search), etc.

### REST API and MCP

```bash
# REST API: http://127.0.0.1:8765/api/v1
python api_server.py

curl http://127.0.0.1:8765/api/v1/health
```

MCP is for Cursor / Claude Desktop; see `mcp.example.json`. Endpoints, parameters, and error codes: **[API调用说明.md](API调用说明.md)**.

### Archive site & search

| Capability | Where | Notes |
|------|------|------|
| **Date archive** | Repo root `index.html` (and `archive/index.html`) | Browse past digests by year/month |
| **Site-wide title search** | Archive home → “Title search” | Searches titles, sources, CVE (needs `search-index.json`) |
| **Jump to search from a daily page** | Search box in daily HTML header | Opens archive home with the query |
| **In-page filter** | Daily HTML toolbar | Filters current page titles / CVE only; no index file |
| **Word cloud & CVE stats** | Daily HTML | Computed by `convert_today.py` from that day’s content |
| **Per-item AI analysis** | Daily list / title search results | **ChatGPT → Gemini → DeepSeek**; copies prompt then opens the AI |
| **One-click API / MCP setup** | Repo root `index.html` `#connect` panel | Copy clone command, Cursor / Claude config, and REST examples |

#### Per-item AI analysis (ChatGPT / Gemini / DeepSeek)

Each article title has three buttons (fixed order):

| Button | Behavior |
|------|------|
| **ChatGPT** | Copies the full prompt; for short content also prefills via `chatgpt.com/?q=` |
| **Gemini** | Copies the full prompt, opens [Gemini](https://gemini.google.com/app); paste with **Ctrl+V** |
| **DeepSeek** | Copies the full prompt, opens [DeepSeek](https://chat.deepseek.com/); paste with **Ctrl+V** |

After a click the button briefly shows **“Copied”** (~2s) on success; on failure a dialog shows the full text for manual copy.

**Prompt includes**: source, date, title, original URL (if any), and 7 analysis tasks (event classification, threat techniques, CVE/impact, defense response, related topics, reading tips, etc.). The AI is asked for Markdown output with a TL;DR first.

**Notes**:

- AI **cannot read** local `file://` pages or digest HTML URLs, so we pass **title + outbound article URL**, not the page URL.
- When opening HTML by double-click, clipboard falls back to `execCommand` (usually works in Chrome / Edge). Prefer `http.server` or GitHub Pages for better compatibility.
- Regenerate historical HTML to get the buttons: `python convert_today.py` (today) or `python md_to_html.py` (all archives).

Local preview (search works without GitHub deploy):

```bash
pip install markdown jinja2
python scripts/build_archive_site.py
cd archive && python -m http.server 8080
# Open http://127.0.0.1:8080/
```

## Configuration

### RSS sources (`config.json`)

```json
{
    "rss": {
        "auto_update": {
            "enabled": true,              // enable auto-update
            "update_interval_days": 7     // interval in days
        },
        "CustomRSS": {
            "enabled": true,
            "filename": "CustomRSS.opml"
        },
        "CyberSecurityRSS": {
            "enabled": true,
            "url": "https://...",
            "filename": "CyberSecurityRSS.opml"
        }
    }
}
```

### RSS auto-update

#### Behavior

- **Auto check**: On startup, checks whether RSS source files need refresh
- **Age check**: Uses file mtime and `update_interval_days`
- **Validation**: Verifies downloaded content before replacing local files
- **Failure safety**: Keeps the local file if the remote is down or invalid

#### Update flow

1. **When**: Before each scheduled task run
2. **Conditions**:
   - File missing, or
   - File older than `update_interval_days`
3. **Validation**:
   - Non-empty content
   - Valid OPML
   - Contains usable feeds
4. **Safety**:
   - Write to a temp file first
   - Replace only after validation
   - Keep local file on failure

#### Options

- `auto_update.enabled`: enable/disable (default: `true`)
- `auto_update.update_interval_days`: interval in days (default: `7`)

### Environment & secrets

Copy `.env.example` to `.env` and fill push secrets plus optional AI settings: `AI_API_URL`, `AI_API_KEY`, `AI_MODEL`, etc.  
`config_loader.py` merges `config.json` with environment variables.

### AI daily summary (`config.json` + `.env`)

```json
{
    "AISummary": {
        "enabled": false,              // true: after digest, call AI to write AISummaryYYYY-MM-DD.md
        "wechat": {
            "enabled": false,
            "corpid": "...",
            "corpsecret": "...",
            "agentid": "..."
        },
        "dingtalk": {
            "enabled": false,
            "access_token": "...",
            "secret": "..."
        }
    }
}
```

- `enabled: false` (default): no AI summary file; RSS + HTML archive still run.
- `enabled: true`: configure AI in `.env`; on failure, skip summary and continue the main flow.
- `wechat` / `dingtalk`: optional separate push for the AI summary.

#### Security-requirement analysis API (optional, not part of the daily pipeline)

`oneapi.analyze_security_report_fenlei()` scores **requirement-style text** across 8 security categories (sensitive data, auth, payment, etc.).  
With `AISummary.enabled=true` and a complete AI config it uses the model; otherwise (or on failure) it falls back to keywords. Call it from your own scripts, e.g.:

```python
from oneapi import analyze_security_report_fenlei

result = analyze_security_report_fenlei(content)
result = analyze_security_report_fenlei(content, use_keyword_analysis=True)  # force keywords
```

### Push configuration

Multiple push channels are supported; see the `bot` and `AISummary` sections in `config.json`.

## Recent improvements

1. **Per-item AI analysis**: ChatGPT / Gemini / DeepSeek one-click prompt copy + jump from digests and archive title search
2. **Archive site**: GitHub Pages, site-wide title search, daily-page layout and filters
3. **RSS auto-update**: Refresh sources on a configurable interval
4. **Safe updates**: Validate remote OPML before replacing local data
5. **AI daily summary** (optional): `AISummary` generation and push
6. **Keyword analysis API** (optional): 8-category matching with keyword fallback
7. **Multi-channel push**: Feishu, WeCom, DingTalk, Telegram, email, etc.
8. **Push cleanup**: Removed QQ / go-cqhttp dependencies and config
9. **REST API / MCP**: Query local digests, articles, and CVEs; see [API调用说明.md](API调用说明.md)

## Logs

- `yarb.log`: Main program log
- `convert_today.log`: HTML conversion log

## Error handling

1. Keep local RSS files when remote update fails
2. Reject updates when content validation fails
3. Network request timeout (30s)
4. Markdown parse errors
5. HTML generation errors
6. Automatic fallback when AI analysis fails (keyword analysis)
7. Silent fallback when AI config is missing (keywords, no noisy prompt)

## RSS update safety

### Protections

1. **Content validation**: Non-empty, correct format after download
2. **OPML parsing**: Validate structure and feed count
3. **Atomic replace**: Temp file → replace only after validation
4. **Rollback**: Keep local file on failure

### Example log lines

```
[+] File older than 7 days, updating: CyberSecurityRSS (last update: 2025-01-15 10:00:00)
[+] Update done: CyberSecurityRSS (150 feeds)
```

On failure:

```
[-] Update failed (OPML parse error: ...), keeping old file: CyberSecurityRSS
```

## GitHub Pages deploy (with site-wide search)

The archive can be published as a static site via GitHub Actions. **Title search** and **date archive** both work on Pages.

### Do I need GitHub Secrets?

**No.** The workflow only publishes static files under `archive/` and builds `search-index.json` from existing Markdown in CI.  
GitHub provides `GITHUB_TOKEN` automatically; you do not need extra secrets for Pages.

If you later want Actions to **run the daily crawl** (`yarb.py`), configure DingTalk / WeCom / AI secrets separately — that is unrelated to Pages deploy.

### One-time setup

1. Push the code to GitHub (`main` or `master`).
2. Repo **Settings → Pages → Build and deployment → Source** → **GitHub Actions**.
3. Push a commit that includes `archive/`, or manually run **Deploy GitHub Pages** under **Actions**.
4. After deploy: **[https://shellsec.github.io/SECDaily/](https://shellsec.github.io/SECDaily/)** (archive index; repo: [https://github.com/shellsec/SECDaily](https://github.com/shellsec/SECDaily)).

### Search notes

| Feature | Notes |
|------|------|
| Date archive | Year/month filter on the home page; no extra files |
| Title search | Needs CI-built `search-index.json` (~16MB; first load may be slow) |
| In-page filter | “Filter title or CVE” on a daily HTML page is local-only and always available |
| Per-item AI analysis | Available on daily pages and title-search results; copy prompt then open ChatGPT / Gemini / DeepSeek |

`archive/search-index.json` stays in `.gitignore` and is generated in CI before each deploy so the large file is not kept in Git history.

Local preview steps are under “Archive site & search” above.

## Contributing

Issues and PRs are welcome: [Issues](https://github.com/shellsec/SECDaily/issues) · [Pull Requests](https://github.com/shellsec/SECDaily/pulls).

1. Follow PEP 8
2. Add useful comments and docs
3. Include tests where appropriate
4. Run tests before submitting

## Acknowledgments

Based on [VulnTotal-Team/yarb](https://github.com/VulnTotal-Team/yarb). Thanks to the original authors.

## License

MIT
