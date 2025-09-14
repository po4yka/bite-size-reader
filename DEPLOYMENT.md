# Bite‑Size Reader — Setup & Deployment Guide

This guide explains how to prepare environments, configure secrets, and run the service locally and in production (Docker).

## Prerequisites
- Python 3.11+
- Telegram account and bot token
- OpenRouter API key
- Firecrawl API key
- Docker (for containerized deployment)

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
- Choose a model (e.g., `openai/gpt-4o`) and set `OPENROUTER_MODEL`.
- Optional attribution: `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`.

## Firecrawl Setup
- Sign up: https://www.firecrawl.dev/
- Create an API key and set `FIRECRAWL_API_KEY`.

## Environment Variables
Copy `.env.example` to `.env` and fill the values:

- Telegram
  - `API_ID` — numeric app id
  - `API_HASH` — app hash
  - `BOT_TOKEN` — bot token from BotFather
  - `ALLOWED_USER_IDS` — comma‑separated user ids allowed to use the bot (strongly recommended)

- OpenRouter
  - `OPENROUTER_API_KEY` — API key
  - `OPENROUTER_MODEL` — model id (e.g., `openai/gpt-4o`)
  - `OPENROUTER_HTTP_REFERER` — optional
  - `OPENROUTER_X_TITLE` — optional

- Firecrawl
  - `FIRECRAWL_API_KEY` — API key

- Runtime
  - `DB_PATH` — default `/data/app.db`
  - `LOG_LEVEL` — `INFO` (default), `DEBUG` for development
  - `REQUEST_TIMEOUT_SEC` — default `60`
  - `PREFERRED_LANG` — `auto|en|ru`
  - `DEBUG_PAYLOADS` — `0|1`, logs request/response previews when `1` (do not enable in prod)

## Local Development
1. Create a virtual environment and install deps:
   - `make venv` (or run `scripts/create_venv.sh`)
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt -r requirements-dev.txt`
2. Export env vars or populate `.env` and export it in your shell.
3. Run tests: `make test`
4. (Optional) Format & lint: `make format && make lint && make type`
5. Run the bot: `python bot.py`

How to use (no commands needed)
- You can simply send a URL (or several URLs in one message) or forward a channel post — the bot will summarize it.
- Commands are optional helpers:
  - `/summarize <URL>` or `/summarize` then send URL
  - `/summarize_all <URLs>` to process many URLs immediately
  - `/summarize_forward` then forward a channel post

## Docker Deployment
1. Generate lock files (recommended):
   - With uv: `make lock-uv`
   - Or pip-tools: `make lock-piptools`
2. Build image: `docker build -t bite-size-reader .`
3. Run container (mount persistent DB volume):
   - `docker run --env-file .env -v $(pwd)/data:/data --name bsr --restart unless-stopped bite-size-reader`

Notes
- The SQLite DB lives at `/data/app.db` inside the container. Mount a host directory for persistence and backups.
- Ensure `ALLOWED_USER_IDS` is set to prevent unauthorized use.
- Keep `DEBUG_PAYLOADS=0` in production.

## Docker Compose (optional)
Create `docker-compose.yml`:

```
services:
  bsr:
    image: bite-size-reader:latest
    build: .
    env_file: .env
    volumes:
      - ./data:/data
    restart: unless-stopped
```

Run: `docker compose up -d --build`

## Security & Hardening
- Access control: set `ALLOWED_USER_IDS`; reject non‑private chats.
- Resource control: consider rate limits and concurrency caps for Firecrawl/LLM calls.
- Secrets: store in `.env` or your secret manager (do not commit `.env`).
- Logs: default JSON logs; correlation IDs included in error messages.
- Container: run with least privileges; ensure volume permissions are restricted on the host.

## Operations
- Health: ensure the bot account stays unbanned and tokens valid.
- Monitoring: watch logs for latency spikes and error rates; consider dashboarding via structured logs.
- Backups: back up `data/app.db` periodically.

## Troubleshooting
- “Access denied”: verify `ALLOWED_USER_IDS` contains your Telegram numeric ID.
- “Failed to fetch content”: Firecrawl error; try again or check the target page access.
- “LLM error”: OpenRouter API issue or model outage; rely on built‑in retries/fallbacks; check logs.
- Large summaries: The bot returns JSON in a message; if too large, consider implementing file replies.
