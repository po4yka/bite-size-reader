# Bite‑Size Reader

Async Telegram bot that summarizes URLs via Firecrawl + OpenRouter or summarizes forwarded channel posts. Returns a strict JSON summary and stores artifacts in SQLite. See SPEC.md for full details.

Quick start
- Copy `.env.example` to `.env` and fill required secrets.
- Build and run with Docker.
- See DEPLOYMENT.md for full setup and deployment instructions.

Docker
- If you updated dependencies in `pyproject.toml`, generate lock files first: `make lock-uv` (or `make lock-piptools`).
- Build: `docker build -t bite-size-reader .`
- Run: `docker run --env-file .env -v $(pwd)/data:/data --name bsr bite-size-reader`

Environment
- `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`
- `FIRECRAWL_API_KEY`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`
- `DB_PATH=/data/app.db`, `LOG_LEVEL=INFO`, `REQUEST_TIMEOUT_SEC=60`
- `DB_BACKUP_ENABLED=1`, `DB_BACKUP_INTERVAL_MINUTES=360`, `DB_BACKUP_RETENTION=14`, `DB_BACKUP_DIR=/data/backups`
- `PREFERRED_LANG=auto` (auto|en|ru)
- `DEBUG_PAYLOADS=0` — when `1`, logs request/response payload previews for Firecrawl/OpenRouter (with Authorization redacted)
 - `MAX_CONCURRENT_CALLS=4` — caps simultaneous Firecrawl/OpenRouter calls

Repository layout
- `app/core` — URL normalization, summary contract, logging utils
- `app/adapters` — Firecrawl/OpenRouter clients, Telegram bot
- `app/db` — SQLite schema and helpers
- `app/prompts` — LLM prompt templates
- `bot.py` — entrypoint
- `SPEC.md` — full technical specification

Notes
- Dependencies include Pyrogram; if using PyroTGFork, align installation accordingly.
- Bot commands are registered on startup for private chats: `/help`, `/summarize`.

Commands & usage
- `/help` or `/start` — Show help and usage.
- `/summarize <URL>` — Summarize a URL immediately.
- `/summarize` — Bot will ask you to send a URL in the next message.
- Multiple URLs in one message (or after `/summarize`): bot asks “Process N links?”; reply “yes/no”. Each link gets its own correlation ID and is processed sequentially.
- `/summarize_all <URLs>` — Summarize multiple URLs from one message immediately, without confirmation.
- `/cancel` — Cancel any pending `/summarize` URL prompt or multi-link confirmation.

Local CLI summary runner
- With the same environment variables exported (Firecrawl + OpenRouter keys, DB path, etc.), run `python -m app.cli.summary --url https://example.com/article`.
- Pass full message text instead of `--url` to mimic Telegram input, e.g. `python -m app.cli.summary "/summary https://example.com"`.
- The CLI loads environment variables from `.env` in your current directory (or project root) automatically; override with `--env-file path/to/.env` if needed.
- Add `--accept-multiple` to auto-confirm when multiple URLs are supplied, `--json-path summary.json` to write the final JSON to disk, and `--log-level DEBUG` for verbose traces.
- The insights stage mirrors production: it retries with JSON-schema first, then falls back to JSON-object mode and configured fallback models before giving up, which reduces `structured_output_parse_error` failures during research add-ons.
- The CLI generates stub Telegram credentials automatically, so no real bot token is required for local runs.

Tips
- You can simply send a URL (or several URLs) or forward a channel post — commands are optional.

Errors & correlation IDs
- All user-visible errors include `Error ID: <cid>` to correlate with logs and DB `requests.correlation_id`.

Dev tooling
- Install dev deps: `pip install -r requirements.txt -r requirements-dev.txt`
- Format: `make format` (black + isort + ruff format)
- Lint: `make lint` (ruff)
- Type-check: `make type` (mypy)
- Pre-commit: `pre-commit install` then commits will auto-run hooks
- Optional: `pip install loguru` to enable Loguru-based JSON logging with stdlib bridging

Pre-commit hooks
- Hooks run in this order to minimize churn: Ruff (with `--fix`), isort (profile=black), Black.
- If a first run modifies files, stage the changes and run again.

Local environment
- Create venv: `make venv` (or run `scripts/create_venv.sh`)
- Activate: `source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt -r requirements-dev.txt`

Dependency management
- Source of truth: `pyproject.toml` ([project] deps + [project.optional-dependencies].dev).
- Locked requirements are generated to `requirements.txt` and `requirements-dev.txt`.
- With uv (recommended):
  - Install: `curl -Ls https://astral.sh/uv/install.sh | sh`
  - Lock: `make lock-uv`
- With pip-tools:
  - `python -m pip install pip-tools`
  - Lock: `make lock-piptools`
- Regenerate locks after changing dependencies in `pyproject.toml`.

CI
- GitHub Actions workflow `.github/workflows/ci.yml` enforces:
  - Lockfile freshness (rebuilds from `pyproject.toml` and checks diff)
  - Lint (ruff), format check (black, isort), type check (mypy)
  - Unit tests (unittest)
  - Matrix tests with and without Pydantic installed to exercise both validation paths
  - Docker image build on every push/PR; optional push to GHCR when `PUBLISH_DOCKER` repository variable is set to `true` (non-PR events)
  - Security checks: Bandit (SAST), pip-audit + Safety (dependency vulns)
  - Secrets scanning: Gitleaks on workspace and full history (history only on push)

Docker publishing (optional)
- Enable publishing to GitHub Container Registry (GHCR):
  - In repository settings → Variables, add `PUBLISH_DOCKER=true`.
  - Ensure workflow permissions include `packages: write` (already configured).
  - Images are tagged as:
    - `ghcr.io/<owner>/<repo>:latest` (on main)
    - `ghcr.io/<owner>/<repo>:<git-sha>`

Automated lockfile PRs
- Workflow `.github/workflows/update-locks.yml` watches `pyproject.toml` and opens a PR to refresh `requirements*.txt` using uv.
- Auto-merge is enabled for that PR; once CI passes, GitHub will automatically merge it.
- You can also trigger it manually from the Actions tab.
