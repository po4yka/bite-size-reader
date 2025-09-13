# Bite‑Size Reader

Async Telegram bot that summarizes URLs via Firecrawl + OpenRouter or summarizes forwarded channel posts. Returns a strict JSON summary and stores artifacts in SQLite. See SPEC.md for full details.

Quick start
- Copy `.env.example` to `.env` and fill required secrets.
- Build and run with Docker.

Docker
- If you updated dependencies in `pyproject.toml`, generate lock files first: `make lock-uv` (or `make lock-piptools`).
- Build: `docker build -t bite-size-reader .`
- Run: `docker run --env-file .env -v $(pwd)/data:/data --name bsr bite-size-reader`

Environment
- `API_ID`, `API_HASH`, `BOT_TOKEN`, `ALLOWED_USER_IDS`
- `FIRECRAWL_API_KEY`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE`
- `DB_PATH=/data/app.db`, `LOG_LEVEL=INFO`, `REQUEST_TIMEOUT_SEC=60`
- `PREFERRED_LANG=auto` (auto|en|ru)
 - `DEBUG_PAYLOADS=0` — when `1`, logs request/response payload previews for Firecrawl/OpenRouter (with Authorization redacted)

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

Dev tooling
- Install dev deps: `pip install -r requirements.txt -r requirements-dev.txt`
- Format: `make format` (black + isort + ruff format)
- Lint: `make lint` (ruff)
- Type-check: `make type` (mypy)
- Pre-commit: `pre-commit install` then commits will auto-run hooks
 - Optional: `pip install loguru` to enable Loguru-based JSON logging with stdlib bridging

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
