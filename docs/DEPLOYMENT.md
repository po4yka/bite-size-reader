# Bite‑Size Reader — Setup & Deployment Guide

This guide explains how to prepare environments, configure secrets, and run the service locally and in production (Docker).

## Prerequisites

- Python 3.13+
- Telegram account and bot token
- OpenRouter API key
- Firecrawl API key
- Docker (for containerized deployment)
- (Optional) Redis for API rate limits/sync locks

## Telegram Setup

1. Create a Telegram app to obtain `API_ID` and `API_HASH`:
   - https://my.telegram.org/apps
2. Create a bot via BotFather to obtain `BOT_TOKEN`:
   - https://t.me/BotFather → `/newbot`
3. Restrict access to your Telegram user ID(s):
   - Find your numeric user ID with any Telegram “user id” bot, then set `ALLOWED_USER_IDS` to a comma‑separated list, e.g. `ALLOWED_USER_IDS=123456789`.
4. The bot registers command hints (`/help`, `/summarize`) automatically on startup for private chats.

## OpenRouter Setup

- Sign up: https://openrouter.ai/
- Create an API key and set `OPENROUTER_API_KEY`.
- Choose a model (e.g., `deepseek/deepseek-v3.2`) and set `OPENROUTER_MODEL`.
- Optional attribution: `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`.

## Firecrawl Setup

- Sign up: https://www.firecrawl.dev/
- Create an API key and set `FIRECRAWL_API_KEY`.

## Environment Variables (essentials)

Copy `.env.example` to `.env` and fill:

- Telegram: `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`
- OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (e.g., `deepseek/deepseek-v3.2`), optional `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`
- Firecrawl: `FIRECRAWL_API_KEY`
- Runtime: `DB_PATH=/data/app.db`, `LOG_LEVEL=INFO| DEBUG`, `REQUEST_TIMEOUT_SEC=60`, `PREFERRED_LANG=auto | en | ru`, `DEBUG_PAYLOADS=0 |1` (keep 0 in prod)
- YouTube: `YOUTUBE_DOWNLOAD_ENABLED=true`, `YOUTUBE_PREFERRED_QUALITY=1080p`, `YOUTUBE_STORAGE_PATH=/data/videos`, size/retention knobs as needed
- API (mobile): `JWT_SECRET_KEY` (>=32 chars), `API_HOST`, `API_PORT` (default 8000), optional `ALLOWED_CLIENT_IDS`
- Redis (rate limit/sync, optional): `REDIS_ENABLED`, `REDIS_URL` or host/port/db, `REDIS_PREFIX=bsr`, `REDIS_REQUIRED=false`, `API_RATE_LIMIT_*` caps, `SYNC_DEFAULT_CHUNK_SIZE`, `SYNC_EXPIRY_HOURS`

## Local Development

1) Create venv & install: `make venv && source .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`
2) Export env or use `.env`.
3) Tests: `make test` (or `make lint`, `make format`, `make type` as needed).
4) Run Telegram bot: `python bot.py`
5) Run mobile API (optional): `uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000`

How to use (no commands needed)

- You can simply send a URL (or several URLs in one message) or forward a channel post — the bot will summarize it.
- Commands are optional helpers:
  - `/summarize <URL>` or `/summarize` then send URL
  - `/summarize_all <URLs>` to process many URLs immediately
  - `/summarize_forward` then forward a channel post

## Docker Deployment

1) (Recommended) lock deps: `make lock-uv` (or `make lock-piptools`).
2) Build: `docker build -t bite-size-reader .`
3) Run:

```
docker run --env-file .env \
  -v $(pwd)/data:/data \
  -p 8000:8000 \  # expose API if needed
  --name bsr --restart unless-stopped bite-size-reader
```

Notes

- SQLite at `/data/app.db`; backups under `/data/backups`. Mount `/data` for durability.
- Set `ALLOWED_USER_IDS`; keep `DEBUG_PAYLOADS=0` in prod.
- If using mobile API, ensure `JWT_SECRET_KEY` is set and port 8000 exposed.

## Docker Compose (recommended)

The production `docker-compose.yml` defines a 5-service stack:

```yaml
services:
  bsr:              # Telegram bot
    build: .
    env_file: .env
    volumes: [./data:/data]
    depends_on: [redis, chroma (optional)]
    healthcheck: SQLite SELECT 1 every 30s

  mobile-api:       # FastAPI REST API
    build: {dockerfile: Dockerfile.api}
    env_file: .env
    ports: ["18000:8000"]
    depends_on: [redis, chroma (optional)]
    healthcheck: HTTP /health every 30s

  mcp:              # MCP server (SSE transport)
    build: .
    command: ["python", "-m", "app.cli.mcp_server"]
    volumes: [./data:/data:ro]  # read-only
    ports: ["127.0.0.1:8200:8200"]
    depends_on: [chroma (optional)]
    healthcheck: TCP socket check on port 8200 every 30s

  redis:            # Caching, rate limits, sync locks
    image: redis:7-alpine
    ports: ["127.0.0.1:6379:6379"]
    healthcheck: redis-cli ping every 10s

  chroma:           # Vector search (ChromaDB)
    image: bsr-chroma:1.5.0-curl
    build: {dockerfile: Dockerfile.chroma}
    ports: ["127.0.0.1:8001:8000"]
    healthcheck: HTTP /api/v2/heartbeat every 30s
```

Run: `docker compose up -d --build`

## Optional Subsystems

These services are not required but enhance functionality when available:

- **Redis** -- Caching layer for Firecrawl/LLM responses, API rate limiting, sync locks, and background task distributed locking. Set `REDIS_ENABLED=true` and configure `REDIS_URL` or host/port.
- **ChromaDB** -- Vector search for semantic article queries. Set `CHROMA_HOST` to a running Chroma instance. Degrades gracefully when unavailable.
- **MCP Server** -- Exposes 17 tools and 13 resources for article search, retrieval, and ChromaDB diagnostics to external AI agents (OpenClaw, Claude Desktop). Runs as a dedicated Docker container with SSE transport (`bsr-mcp`) or standalone via `python -m app.cli.mcp_server`. See `docs/mcp_server.md`.
- **Karakeep** -- Bookmark sync integration. Set `KARAKEEP_ENABLED=true` with API URL and key. Use `/sync_karakeep` to trigger manually.

Full variable reference: `docs/environment_variables.md`

## Security & Hardening

- Access control: set `ALLOWED_USER_IDS`; restrict `ALLOWED_CLIENT_IDS` for API if used.
- Resource control: configure rate limits (`API_RATE_LIMIT_*`) and concurrency caps; prefer Redis.
- Secrets: use `.env` or secret manager; never commit secrets.
- Logs: JSON with correlation IDs; redact `Authorization`.
- Container: least privilege; restrict `/data` permissions on host; HTTPS termination in front of API.

## Operations

- Health: ensure the bot account stays unbanned and tokens valid.
- Monitoring: watch logs for latency spikes and error rates; consider dashboarding via structured logs.
- Backups: automatic snapshots land in `/data/backups`. Copy them off-host or adjust `DB_BACKUP_*` if you need a different cadence.

### Health Checks

| Service | Method | Interval | Details |
| --------- | -------- | ---------- | --------- |
| bsr | SQLite `SELECT 1` | 30s | Verifies DB connectivity; 5 retries, 60s start period |
| mobile-api | HTTP `GET /health` | 30s | Returns 200 when API is ready; 5 retries, 60s start period |
| mcp | TCP socket on port 8200 | 30s | SSE server liveness check; 3 retries, 30s start period |
| redis | `redis-cli ping` | 10s | Standard Redis liveness check; 5 retries |
| chroma | HTTP `GET /api/v2/heartbeat` | 30s | ChromaDB heartbeat endpoint; 3 retries, 60s start period |

## Updating a Running Instance

When deploying a new version to a host that already has the service running:

### 1. Backup

```bash
cd /path/to/bite-size-reader
tar czf ~/bite-size-reader-backup-$(date +%Y%m%d%H%M).tgz data .env
```

The container also writes automatic snapshots to `data/backups/`.

### 2. Pull latest

```bash
git fetch --all --prune
git checkout main
git pull --ff-only
```

Pin to a specific tag: `git checkout tags/<tag>`

### 3. Refresh deps (when pyproject/lock changed)

```bash
make lock-uv   # or: make lock-piptools
```

### 4. Rebuild & redeploy

```bash
# Compose (recommended)
docker compose down
docker compose up -d --build

# Or manual
docker stop bsr && docker rm bsr
docker build -t bite-size-reader:latest .
docker run -d --env-file .env -v $(pwd)/data:/data \
  -p 8000:8000 --name bsr --restart unless-stopped bite-size-reader:latest
```

### 5. Verify

```bash
docker ps
docker logs -f bsr
```

Send a test message from a whitelisted Telegram account.

### 6. Rollback

Stop the container, restore the backup tarball, and restart the previous image:

```bash
git checkout <previous-commit-sha>
docker compose up -d --build
```

## Troubleshooting

- "Access denied": verify `ALLOWED_USER_IDS` contains your Telegram numeric ID.
- "Failed to fetch content": Firecrawl error; try again or check the target page access.
- "LLM error": OpenRouter API issue or model outage; rely on built-in retries/fallbacks; check logs.
- Missing deps after update: rebuild the Docker image.
- Secrets/env issues: recheck `.env` (quote special chars).
- Telegram auth: verify `API_ID`, `API_HASH`, `BOT_TOKEN`; ensure bot not banned.
- DB permissions: ensure host `data/` is writable by the Docker user.
- Large summaries: The bot returns JSON in a message; if too large, consider implementing file replies.
