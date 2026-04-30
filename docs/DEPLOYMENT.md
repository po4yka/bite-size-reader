# Ratatoskr — Setup & Deployment Guide

This guide explains how to prepare environments, configure secrets, and run the service locally and in production (Docker).

## Prerequisites

- Python 3.13+
- Telegram account and bot token
- OpenRouter API key
- Firecrawl API key (optional -- Scrapling and self-hosted Firecrawl are free alternatives)
- Docker (for containerized deployment)
- Node.js 20+ (optional; needed for local `clients/web/` frontend development)
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

## Firecrawl Setup (Optional)

`FIRECRAWL_API_KEY` is **optional**. The default scraper chain (`SCRAPER_PROVIDER_ORDER`) tries Scrapling (free, in-process) first, then falls back to Firecrawl, Playwright, Crawlee, and direct HTML extraction. You only need a cloud Firecrawl API key if you want to use cloud Firecrawl or web search enrichment.

- Cloud Firecrawl: Sign up at https://www.firecrawl.dev/ and set `FIRECRAWL_API_KEY`.
- Self-hosted Firecrawl: Enable via `FIRECRAWL_SELF_HOSTED_ENABLED=true` and point `FIRECRAWL_SELF_HOSTED_URL` at a running Firecrawl API. The current Compose file does not start Firecrawl; it uses the `firecrawl-api` host-gateway name for an externally managed Firecrawl service. Phase 2 of the refactoring roadmap will add an in-compose Firecrawl profile.
- Scrapling: Enabled by default (`SCRAPER_SCRAPLING_ENABLED=true`), no API key required.
- Breaking rename note: legacy vars (`SCRAPLING_*`, `SCRAPER_DIRECT_HTTP_ENABLED`) now fail fast at startup.

See `docs/environment_variables.md` for the full multi-provider scraper chain configuration.

## Environment Variables (essentials)

Copy `.env.example` to `.env` and fill:

- Telegram: `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`
- OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (e.g., `deepseek/deepseek-v3.2`), optional `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`
- Firecrawl: `FIRECRAWL_API_KEY`
- Runtime: `DB_PATH=/data/ratatoskr.db`, `LOG_LEVEL=INFO| DEBUG`, `REQUEST_TIMEOUT_SEC=60`, `PREFERRED_LANG=auto | en | ru`, `DEBUG_PAYLOADS=0 |1` (keep 0 in prod)
- YouTube: `YOUTUBE_DOWNLOAD_ENABLED=true`, `YOUTUBE_PREFERRED_QUALITY=1080p`, `YOUTUBE_STORAGE_PATH=/data/videos`, size/retention knobs as needed
- Mixed-source aggregation: `AGGREGATION_BUNDLE_ENABLED=true`, `AGGREGATION_ROLLOUT_STAGE=enabled`, optional extractor flags (`AGGREGATION_META_EXTRACTORS_ENABLED`, `AGGREGATION_ARTICLE_MEDIA_ENABLED`, `AGGREGATION_NON_YOUTUBE_VIDEO_ENABLED`)
- API (mobile): `JWT_SECRET_KEY` (>=32 chars), `API_HOST`, `API_PORT` (default 8000), optional `ALLOWED_CLIENT_IDS`
- Web frontend (JWT mode login widget, optional for `clients/web/` local build/dev): `VITE_TELEGRAM_BOT_USERNAME`
- Redis (rate limit/sync, optional): `REDIS_ENABLED`, `REDIS_URL` or host/port/db, `REDIS_PREFIX=ratatoskr`, `REDIS_REQUIRED=false`, `API_RATE_LIMIT_*` caps, `SYNC_DEFAULT_CHUNK_SIZE`, `SYNC_EXPIRY_HOURS`

## Local Development

1) Create venv & install: `make venv && source .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`
2) Export env or use `.env`.
3) Tests: `make test` (or `make lint`, `make format`, `make type` as needed).
4) Run Telegram bot: `python bot.py`
5) Run API host (serves `/v1/*`, `/static/*`, and `/web/*`): `uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000`
6) Optional web frontend local loop:
   - `cd clients/web && npm ci`
   - `npm run dev` (Vite dev server)
   - `npm run check:static` (lint + typecheck)

## Web Interface Serving Contract

The FastAPI service serves the web frontend from a static bundle:

- Web static files: `/static/web/*`
- Web SPA entry routes: `/web` and `/web/{path:path}` (returns `app/static/web/index.html`)

If `/web` returns `404 "Web interface is not built"`, rebuild static assets with:

```bash
cd clients/web
npm ci
npm run build
```

How to use (no commands needed)

- You can simply send a URL (or several URLs in one message) or forward a channel post — the bot will summarize it.
- You can also use `/aggregate` to synthesize one mixed-source bundle from one or more links and, when applicable, the current forwarded/attached Telegram content.
- Commands are optional helpers:
  - `/summarize <URL>` or `/summarize` then send URL
  - `/summarize_all <URLs>` to process many URLs immediately
  - `/aggregate <URLs>` to request one bundle-level aggregation
  - `/summarize_forward` then forward a channel post

## Docker Deployment

1) Lock deps: `make lock-uv`.
2) Build: `docker build -f ops/docker/Dockerfile -t ratatoskr .`
3) Run:

```
docker run --env-file .env \
  -v $(pwd)/data:/data \
  -p 8000:8000 \  # expose API if needed
  --name ratatoskr --restart unless-stopped ratatoskr
```

Notes

- SQLite at `/data/ratatoskr.db`; backups under `/data/backups`. Mount `/data` for durability.
- Set `ALLOWED_USER_IDS`; keep `DEBUG_PAYLOADS=0` in prod.
- If using mobile API, ensure `JWT_SECRET_KEY` is set and port 8000 exposed.
- Docker build includes the `clients/web/` bundle and publishes it under `/static/web/*`.

## Docker Compose (recommended)

The production `ops/docker/docker-compose.yml` defines a 5-service stack:

```yaml
services:
  ratatoskr:              # Telegram bot
    build: .
    env_file: .env
    volumes: [./data:/data]
    depends_on: [redis, chroma (optional)]
    healthcheck: SQLite SELECT 1 every 30s

  mobile-api:       # FastAPI REST API
    build: {context: ../.., dockerfile: ops/docker/Dockerfile.api}
    env_file: .env
    ports: ["127.0.0.1:18000:8000"]
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
    image: ratatoskr-chroma:1.5.2
    build: {context: ../.., dockerfile: ops/docker/Dockerfile.chroma}
    ports: ["127.0.0.1:8001:8000"]
    healthcheck: HTTP /api/v2/heartbeat every 30s
```

Run: `docker compose -f ops/docker/docker-compose.yml up -d --build`

## Optional Subsystems

These services are not required but enhance functionality when available:

- **Redis** -- Caching layer for Firecrawl/LLM responses, API rate limiting, sync locks, and background task distributed locking. Set `REDIS_ENABLED=true` and configure `REDIS_URL` or host/port.
- **ChromaDB** -- Vector search for semantic article queries. Set `CHROMA_HOST` to a running Chroma instance. Degrades gracefully when unavailable.
- **MCP Server** -- Exposes article, search, ChromaDB, and aggregation tools/resources to external AI agents (OpenClaw, Claude Desktop, hosted SSE clients). Runs as a dedicated Docker container with SSE transport (`ratatoskr-mcp`) or standalone via `python -m app.cli.mcp_server`. See `docs/mcp_server.md`.
- **Channel Digest** -- Scheduled digests of subscribed Telegram channels. Set `DIGEST_ENABLED=true` and `API_BASE_URL` to the Mobile API endpoint. Run `/init_session` in the bot to authenticate the userbot via Mini App OTP/2FA flow, then use `/subscribe @channel` to add channels.

Full variable reference: `docs/environment_variables.md`

## Security & Hardening

- Access control: set `ALLOWED_USER_IDS`; restrict `ALLOWED_CLIENT_IDS` for API if used.
- Resource control: configure rate limits (`API_RATE_LIMIT_*`) and concurrency caps; prefer Redis.
- Aggregation guardrails: tune `API_RATE_LIMIT_AGGREGATION_CREATE_USER` and `API_RATE_LIMIT_AGGREGATION_CREATE_CLIENT` before exposing `/v1/aggregations` to external clients.
- Aggregation URL safety: `/v1/aggregations` rejects localhost, private-network, and other reserved-address targets before extraction starts.
- Secrets: use `.env` or secret manager; never commit secrets.
- Logs: JSON with correlation IDs; redact `Authorization`.
- Container: least privilege; restrict `/data` permissions on host; HTTPS termination in front of API.

### External CLI and Hosted MCP Rollout Checklist

Before onboarding external users, verify:

1. `SECRET_LOGIN_ENABLED=true` on the API service.
2. `ALLOWED_CLIENT_IDS` is explicitly set for the client IDs you plan to issue, for example `cli-workstation-v1,mcp-agent-v1`.
3. Client IDs follow stable prefixes such as `cli-*`, `mcp-*`, `automation-*`, `web-*`, or `mobile-*`.
4. Operators understand that plaintext client secrets are visible only at create or rotate time.
5. External self-service secret issuance remains limited to `cli-*`, `mcp-*`, and `automation-*` clients unless you intentionally widen the model later.

Before exposing hosted public MCP, also verify:

1. `MCP_TRANSPORT=sse`
2. `MCP_AUTH_MODE=jwt`
3. `MCP_USER_ID` is unset for hosted request-scoped mode
4. `MCP_ALLOW_REMOTE_SSE=true` only when you intentionally bind beyond loopback
5. `MCP_FORWARDING_SECRET` is configured if a trusted gateway forwards bearer tokens
6. the MCP deployment has writable access to the database if you want aggregation write tools enabled
7. `/v1/aggregations` and `/sse` both sit behind HTTPS and normal ingress logging/monitoring

### External Access Stage Order

Roll out external aggregation access in this order and only promote when the previous stage stays within the safety thresholds for at least 24 hours:

1. Internal API users only
2. Invite-only external CLI users
3. Local stdio MCP users with write-capable aggregation tools
4. Trusted hosted SSE MCP beta behind a gateway
5. Broad external enablement

Watch these signals during every stage:

- `ratatoskr_requests_total{type="aggregation.create",status=...,source="cli"}` for CLI create volume and error rate
- `ratatoskr_requests_total{type="aggregation.create",status=...,source="api"}` for direct API callers without a typed client prefix
- `ratatoskr_requests_total{type="<tool>",status=...,source="mcp"}` for MCP tool adoption and failures
- `ratatoskr_request_latency_seconds{type="aggregation.create",stage="total"}` for end-to-end API create latency
- `ratatoskr_request_latency_seconds{type="<tool>",stage="total"}` for MCP tool latency
- `ratatoskr_aggregation_bundles_total{status=...,entrypoint=...}` for completed, partial, and failed bundles
- `ratatoskr_aggregation_extraction_total{platform=...,outcome=...}` for per-platform extraction failure spikes
- `ratatoskr_aggregation_bundle_latency_seconds{entrypoint=...}` for bundle completion latency
- `ratatoskr_aggregation_synthesis_coverage_ratio_bucket{source_type=...,status=...}` for low-coverage summaries

Use these go/no-go thresholds:

- Promote only if `aggregation.create` and MCP write-tool error rates stay below 5% over the last 24 hours.
- Hold the rollout if failed plus partial bundles exceed 10% of total bundles for any stage.
- Hold the rollout if p95 `aggregation.create` latency exceeds 30 seconds for CLI/API traffic or if p95 MCP write-tool latency exceeds 15 seconds.
- Hold the rollout if any single platform in `ratatoskr_aggregation_extraction_total` shows a failure rate above 20%.
- Hold the rollout if low-coverage syntheses (`coverage_ratio < 0.5`) exceed 10% of completed mixed bundles.
- Roll back immediately on confirmed cross-user access, auth bypass, SSRF bypass, or sustained 429 saturation caused by the new client cohort.

Stage-specific promotion checks:

- Stage 1 to Stage 2:
  keep invite-only CLI clients on an explicit allowlist, verify client IDs map cleanly to `cli-*`, and confirm successful create/get/list flows for at least three distinct external users.
- Stage 2 to Stage 3:
  verify local MCP aggregation writes use scoped identities only, and confirm `ratatoskr_requests_total{source="mcp"}` shows zero auth or access-denied surprises for trusted testers.
- Stage 3 to Stage 4:
  verify hosted SSE traffic arrives through JWT or trusted forwarded-token auth only, confirm request-scoped reads and writes in logs, and require no security incidents during the beta window.
- Stage 4 to Stage 5:
  confirm support docs, troubleshooting coverage, rate-limit capacity, and operator dashboards are all in active use before widening access.

Rollback triggers and actions:

- If any hold or rollback condition is hit, stop issuing new external secrets, pause hosted MCP onboarding, and set `AGGREGATION_ROLLOUT_STAGE` back to the last safe stage.
- If hosted MCP is implicated, disable public exposure first by setting `MCP_ALLOW_REMOTE_SSE=false` or removing the public ingress route.
- If only secret-based external access is implicated, set `SECRET_LOGIN_ENABLED=false` while keeping internal bot/API traffic available.
- Rotate affected client secrets, review `aggregation.bundle_create_*` audit events, and restore the previous known-good image before reopening the stage.

## Operations

- Health: ensure the bot account stays unbanned and tokens valid.
- Monitoring: watch logs for latency spikes and error rates; consider dashboarding via structured logs.
- Aggregation observability: Grafana provisioning includes `ops/monitoring/grafana/provisioning/dashboards/ratatoskr-aggregation.json` for bundle cost, latency, partial-success, and coverage tracking.
- Backups: automatic snapshots land in `/data/backups`. Copy them off-host or adjust `DB_BACKUP_*` if you need a different cadence.

### Health Checks

| Service | Method | Interval | Details |
| --------- | -------- | ---------- | --------- |
| ratatoskr | SQLite `SELECT 1` | 30s | Verifies DB connectivity; 5 retries, 60s start period |
| mobile-api | HTTP `GET /health` | 30s | Returns 200 when API is ready; 5 retries, 60s start period |
| mcp | TCP socket on port 8200 | 30s | SSE server liveness check; 3 retries, 30s start period |
| redis | `redis-cli ping` | 10s | Standard Redis liveness check; 5 retries |
| chroma | HTTP `GET /api/v2/heartbeat` | 30s | ChromaDB heartbeat endpoint; 3 retries, 60s start period |

## Updating a Running Instance

When deploying a new version to a host that already has the service running:

### 1. Backup

```bash
cd /path/to/ratatoskr
tar czf ~/ratatoskr-backup-$(date +%Y%m%d%H%M).tgz data .env
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
make lock-uv
```

> **First upgrade onto Ratatoskr from `bite-size-reader`?** Read
> [Migrate from bite-size-reader](how-to/migrate-from-bite-size-reader.md)
> first — it covers the renamed Docker image, MCP URIs / headers,
> Prometheus metric names, web storage keys, and the retired Karakeep
> integration.

### 4. Rebuild & redeploy

```bash
# Compose (recommended)
docker compose -f ops/docker/docker-compose.yml down
docker compose -f ops/docker/docker-compose.yml up -d --build

# Or manual
docker stop ratatoskr && docker rm ratatoskr
docker build -f ops/docker/Dockerfile -t ratatoskr:latest .
docker run -d --env-file .env -v $(pwd)/data:/data \
  -p 8000:8000 --name ratatoskr --restart unless-stopped ratatoskr:latest
```

### 5. Verify

```bash
docker ps
docker logs -f ratatoskr
```

Send a test message from a whitelisted Telegram account.

### 6. Rollback

Stop the container, restore the backup tarball, and restart the previous image:

```bash
git checkout <previous-commit-sha>
docker compose -f ops/docker/docker-compose.yml up -d --build
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
- `/web` returns 404: web bundle is missing; build `clients/web/` (`npm run build`) or redeploy an image that includes the web build stage.
