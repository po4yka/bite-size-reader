# Bite‑Size Reader

Async Telegram bot that summarizes URLs via Firecrawl + OpenRouter or summarizes forwarded channel posts. Returns a strict JSON summary and stores artifacts in SQLite. See SPEC.md for full details.

Quick start
- Copy `.env.example` to `.env` and fill required secrets.
- Build and run with Docker.

Docker
- Build: `docker build -t bite-size-reader .`
- Run: `docker run --env-file .env -v $(pwd)/data:/data --name bsr bite-size-reader`

Environment
- `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`
- `FIRECRAWL_API_KEY`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`
- `DB_PATH=/data/app.db`, `LOG_LEVEL=INFO`, `REQUEST_TIMEOUT_SEC=60`
- `PREFERRED_LANG=auto` (auto|en|ru)

Repository layout
- `app/core` — URL normalization, summary contract, logging utils
- `app/adapters` — Firecrawl/OpenRouter clients, Telegram bot
- `app/db` — SQLite schema and helpers
- `app/prompts` — LLM prompt templates
- `bot.py` — entrypoint
- `SPEC.md` — full technical specification

Notes
- Dependencies include Pyrogram; if using PyroTGFork, align installation accordingly.
- This is a skeleton implementation; handlers, retries, and persistence are minimal and should be extended per SPEC.md.
