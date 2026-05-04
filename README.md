# Ratatoskr

A self-hosted Telegram bot that turns the things you read, watch, and
forward into a searchable, structured archive — web articles,
YouTube videos, Twitter / X posts, forwarded channel messages, or any
mix of those bundled together. Owner-only by design, runs as a single
Docker container, stores everything in SQLite.

[![CI](https://github.com/po4yka/ratatoskr/actions/workflows/ci.yml/badge.svg)](https://github.com/po4yka/ratatoskr/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker)](ops/docker/Dockerfile)
[![License](https://img.shields.io/badge/license-see%20LICENSE-lightgrey)](LICENSE)

<!-- TODO: drop a hero screenshot or short GIF at docs/assets/hero.png and link it here -->

---

## Why Ratatoskr?

- **Self-hosted, single-tenant.** Your data, your server, your
  Telegram-API quota. The bot only answers IDs in `ALLOWED_USER_IDS`.
- **Pluggable cost.** Bring your own OpenRouter key (or OpenAI /
  Anthropic). Free DeepSeek / Gemini Flash models cover most workloads
  out of the box; paid models are an opt-in upgrade.
- **Built for triage, not bookmarking.** Each summary is a strict
  35+ field JSON contract — TLDR, key ideas, entities, key stats,
  topics, reading time — so search and downstream automation actually
  work.
- **Multi-source aggregation.** Bundle a YouTube clip with two web
  articles and a forwarded post, get one synthesized output with
  per-source provenance.

## 30-second install

```sh
git clone https://github.com/po4yka/ratatoskr.git
cd ratatoskr
cp .env.example .env                  # set the 5 required values
docker compose -f ops/docker/docker-compose.yml up -d
```

Required env vars (everything else has sensible defaults):

```env
API_ID=                # https://my.telegram.org/apps
API_HASH=
BOT_TOKEN=             # @BotFather
ALLOWED_USER_IDS=      # your Telegram user ID
OPENROUTER_API_KEY=    # https://openrouter.ai
```

Optional scraper, YouTube, Twitter/X, MCP, and provider tuning now live in
`ratatoskr.yaml`; see [Optional YAML Configuration](docs/reference/config-file.md).
`JWT_SECRET_KEY` is required only when enabling web/API/browser-extension JWT auth.

Compose profiles:

- `with-scrapers` starts the full self-hosted scraper sidecar stack: `firecrawl-api` (port 3002), `crawl4ai` (port 11235), and `defuddle-api` (port 3003) plus their dependencies. Set `FIRECRAWL_SELF_HOSTED_ENABLED=true` to activate the Firecrawl rung. Cloud Firecrawl is not used for article extraction; there is no `FIRECRAWL_API_KEY` requirement.
- `with-cloud-ollama` adds a remote OpenAI-compatible Ollama reachability check; set `LLM_PROVIDER=ollama` and `OLLAMA_*` values to use it. It does not start a local model server.
- `with-monitoring` starts Prometheus, Grafana, Loki, Promtail, and node-exporter.
- `mcp`, `mcp-write`, and `mcp-public` start the optional MCP server variants.

For the guided walkthrough, see the
[5-minute Quickstart Tutorial](docs/guides/quickstart.md). For the
full setup including TLS, monitoring, and backups, see
[DEPLOYMENT.md](docs/DEPLOYMENT.md).
The onboarding script is tracked in
[Clone to First Summary](docs/guides/clone-to-first-summary.md) for repeatable
10-minute validation runs.

## What it does

**Web articles.** A multi-provider scraper chain — Scrapling →
Crawl4AI → Firecrawl (self-hosted only) → Defuddle → Playwright →
Crawlee → direct HTML → ScrapeGraphAI — extracts clean content, then
OpenRouter generates a summary against the strict JSON contract. The default
order is overridable via `SCRAPER_PROVIDER_ORDER`. Cloud Firecrawl is not
used; all sidecars (Firecrawl, Crawl4AI, Defuddle) run via the
`with-scrapers` Docker Compose profile. JS-heavy hosts can be configured to
skip straight to a browser-based provider.

**YouTube videos.** Detects every common URL form (watch, shorts,
live, embed, music, mobile). Pulls transcripts via
`youtube-transcript-api` (manual subtitles preferred), downloads the
video at 1080p with `yt-dlp` for archival, then summarizes from the
transcript. Storage is capped per-video and in total, with optional
auto-cleanup. See [Configure YouTube Download](docs/guides/configure-youtube-download.md).

**Twitter / X.** Two-tier extraction: Firecrawl public scraping by
default; opt-in authenticated Playwright with your own `cookies.txt`
when you need protected accounts, deep threads, or X Articles.
GraphQL interception for tweets / threads, DOM scraping for X
Articles, redirect-aware article URL resolver. See
[Configure Twitter / X Extraction](docs/guides/configure-twitter-extraction.md).

**Forwarded posts and bundles.** Forward a Telegram channel post and
get the same structured summary; or use `/aggregate` to bundle one or
more URLs (plus optional forwards / attachments) into a single
provenance-tracked synthesis. Channel-digest scheduling on top of all
this turns subscribed channels into a periodic recap.

## Configure & extend

| What | Where |
| --- | --- |
| First-run env and optional YAML config | [docs/environment_variables.md](docs/environment_variables.md) · [docs/reference/config-file.md](docs/reference/config-file.md) |
| Production deploy, monitoring, backups, TLS | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Architecture diagram, request lifecycle, subsystem index | [docs/explanation/architecture-overview.md](docs/explanation/architecture-overview.md) |
| Mobile REST API (JWT auth, sync, aggregations) | [docs/MOBILE_API_SPEC.md](docs/MOBILE_API_SPEC.md) |
| Web frontend (`/web/*`) | [docs/reference/frontend-web.md](docs/reference/frontend-web.md) |
| MCP server for external AI agents | [docs/reference/mcp-server.md](docs/reference/mcp-server.md) |
| FAQ / troubleshooting | [docs/FAQ.md](docs/FAQ.md) · [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Full doc index | [docs/README.md](docs/README.md) |

## Where to next

| If you want to … | Start here |
| --- | --- |
| **Use it.** Run the bot, try out features, configure a knob. | [Quickstart Tutorial](docs/guides/quickstart.md) → [How-to guides](docs/README.md#how-to-guides-goal-oriented) |
| **Deploy and operate it.** Production install, monitoring, backups, upgrades. | [DEPLOYMENT.md](docs/DEPLOYMENT.md) → [Backup and Restore](docs/guides/backup-and-restore.md) → [Optimize Performance](docs/guides/optimize-performance.md) |
| **Extend it.** Read the code, write a feature, integrate a client. | [CLAUDE.md](CLAUDE.md) (codebase tour) → [docs/SPEC.md](docs/SPEC.md) (canonical contract) → [Local Development Tutorial](docs/guides/local-development.md) |

Upgrading from `bite-size-reader`? The rename has its own operator
checklist:
[Migrate from bite-size-reader](docs/guides/migrate-from-bite-size-reader.md).

---

Released under the terms of [LICENSE](LICENSE). Bug reports, feature
requests, and pull requests are welcome at
[github.com/po4yka/ratatoskr/issues](https://github.com/po4yka/ratatoskr/issues).

Built on the shoulders of [Telethon](https://github.com/LonamiWebs/Telethon),
[Scrapling](https://github.com/D4Vinci/Scrapling),
[Firecrawl](https://github.com/mendableai/firecrawl) (self-hosted),
[Crawl4AI](https://github.com/unclecode/crawl4ai),
[Defuddle](https://github.com/kepano/defuddle) (self-hosted Node sidecar),
[OpenRouter](https://openrouter.ai/),
[FastAPI](https://fastapi.tiangolo.com/),
a project-owned design system shim,
and [yt-dlp](https://github.com/yt-dlp/yt-dlp).
