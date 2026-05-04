# CLAUDE.md -- AI Assistant Guide for Ratatoskr

This document helps AI assistants (like Claude) understand and work effectively with the Ratatoskr codebase.

## Project Overview

**Ratatoskr** is an async Telegram bot that:

- Accepts web article URLs and summarizes them using a multi-provider scraper chain (content extraction) + OpenRouter (LLM summarization)
- Accepts YouTube video URLs, downloads them in 1080p, extracts transcripts, and generates summaries
- Accepts forwarded channel posts and summarizes them directly
- Returns structured JSON summaries with a strict contract
- Stores all artifacts (Telegram messages, crawl results, video downloads, LLM calls, summaries) in SQLite
- Exposes a web frontend (`clients/web/`) served by FastAPI on `/web/*`
- Runs as a single Docker container with owner-only access control

**Tech Stack:**

- Python 3.13+
- Telethon (async Telegram MTProto)
- Scrapling (primary in-process content scraper)
- Firecrawl API (self-hosted secondary scraper; cloud API optional for web search)
- yt-dlp (YouTube video downloading)
- youtube-transcript-api (YouTube transcript extraction)
- ffmpeg (video/audio merging for yt-dlp)
- OpenRouter API (OpenAI-compatible LLM completions)
- SQLite (persistence with Peewee ORM)
- httpx (async HTTP client)
- pydantic / pydantic-settings (validation, configuration)
- trafilatura, spacy (lightweight sentence tokenizer via spacy.blank())
- json-repair (JSON recovery from LLM output)
- scikit-learn, sentence-transformers, chromadb (search, local embeddings, vector store)
- google-genai (optional: Gemini Embedding 2 API provider)
- loguru, orjson (structured logging, fast JSON serialization)
- FastAPI / uvicorn (Mobile REST API)
- React 18 + TypeScript + Vite (web frontend)
- Frost design system (`clients/web/src/design/`) — editorial monospace minimalism with two-color rule + spark accent. See DESIGN.md.
- @tanstack/react-query (web data fetching, caching, polling)
- PyJWT (JWT authentication)
- redis (optional caching and distributed locking)
- apscheduler (background task scheduling)
- weasyprint (PDF export)
- mcp (Model Context Protocol server)
- ElevenLabs API (optional: text-to-speech audio generation)

## Architecture Overview

The component diagram, request lifecycle, layered view, and the
canonical subsystem index live in
[`docs/explanation/architecture-overview.md`](docs/explanation/architecture-overview.md).
Read that page first when orienting yourself; this file focuses on
AI-assistant operating notes (where things live, what to touch, what
not to touch) rather than re-stating the architecture.

## Directory Structure

```
app/
+-- adapters/           # External service integrations
|   +-- attachment/     # Attachment handling and processing
|   +-- content/        # URL processing pipeline
|   |   +-- scraper/    # Multi-provider scraper chain (protocol, chain, factory, providers)
|   +-- digest/         # Channel digest orchestration
|   +-- elevenlabs/     # ElevenLabs TTS integration
|   +-- external/       # Firecrawl parser, response formatter
|   +-- llm/            # Provider-agnostic LLM abstraction
|   +-- openrouter/     # OpenRouter client and helpers
|   +-- telegram/       # Telegram bot logic, command_handlers/
|   +-- twitter/        # Twitter/X content extraction
|   +-- youtube/        # YouTube video download and transcript extraction
+-- agents/             # Multi-agent system (extraction, summarization, validation, web search)
+-- api/                # Mobile API (FastAPI, JWT auth, sync)
|   +-- models/         # Pydantic request/response models
|   +-- routers/        # Route handlers (auth, summaries, sync, collections, health, system, tts, search, requests, digest, user)
|   +-- services/       # API business logic
+-- application/        # Application layer (DDD)
|   +-- dto/            # Data transfer objects
|   +-- use_cases/      # Use case orchestrators
+-- config/             # Configuration modules
+-- core/               # Shared utilities (URL, JSON, logging, lang)
+-- db/                 # Database schema and models
+-- di/                 # Dependency injection
+-- domain/             # Domain models and services (DDD patterns)
+-- infrastructure/     # Persistence, event bus, vector store
|   +-- cache/          # Cache layer (Redis)
|   +-- messaging/      # Messaging infrastructure
+-- mcp/                # MCP server for AI agent access
+-- models/             # Pydantic/dataclass models
|   +-- llm/            # LLM config models
|   +-- telegram/       # Telegram entity models
+-- observability/      # Metrics, tracing, telemetry
+-- prompts/            # LLM system prompts (en/ru)
+-- security/           # Security utilities
+-- types/              # Type definitions
+-- utils/              # Helper utilities (progress, formatting, validation)
clients/
+-- cli/                # CLI tools (summary runner, search, MCP server, migrations, Chroma backfill)
+-- browser-extension/  # Browser extension assets and docs
+-- web/                # Web interface (React + TypeScript + Vite)
integrations/
+-- openclaw-skill/     # OpenClaw MCP skill bundle
ops/
+-- config/             # Versioned example config assets
+-- docker/             # Dockerfiles and compose definitions
+-- monitoring/         # Prometheus/Grafana/Loki/Promtail assets
tools/
+-- scripts/            # Development and maintenance scripts
```

## Database Models

48 Peewee model classes registered in `ALL_MODELS` (`app/db/models.py`):

`User`, `Chat`, `Request`, `AggregationSession`, `AggregationSessionItem`, `TelegramMessage`, `CrawlResult`, `LLMCall`, `Summary`, `TopicSearchIndex` (FTS5), `UserInteraction`, `AuditLog`, `SummaryEmbedding`, `VideoDownload`, `AudioGeneration`, `AttachmentProcessing`, `ClientSecret`, `Collection`, `CollectionItem`, `CollectionCollaborator`, `CollectionInvite`, `UserDevice`, `RefreshToken`, `BatchSession`, `BatchSessionItem`, `Channel`, `ChannelCategory`, `ChannelSubscription`, `ChannelPost`, `ChannelPostAnalysis`, `DigestDelivery`, `UserDigestPreference`, `SummaryFeedback`, `CustomDigest`, `SummaryHighlight`, `UserGoal`, `Tag`, `SummaryTag`, `WebhookSubscription`, `WebhookDelivery`, `AutomationRule`, `RuleExecutionLog`, `ImportJob`, `UserBackup`, `RSSFeed`, `RSSFeedSubscription`, `RSSFeedItem`, `RSSItemDelivery`

## Summary JSON Contract

Defined in `app/core/summary_contract.py` (validation) and `app/core/summary_schema.py` (Pydantic model), documented in docs/SPEC.md. Core fields: `summary_250`, `summary_1000`, `tldr`, `key_ideas`, `topic_tags`, `entities`, `estimated_reading_time_min`, `key_stats`, `answered_questions`, `readability`, `seo_keywords`. The full contract includes 35+ fields with nested structures (`source_type`, `temporal_freshness`, `metadata`, `extractive_quotes`, `topic_taxonomy`, `hallucination_risk`, `confidence`, `insights`, `semantic_chunks`, etc.).

## Development Workflow

### Code Standards

- **Formatting:** ruff format + isort (profile=black)
- **Linting:** Ruff (see `pyproject.toml` for rules)
- **Type Checking:** mypy (permissive config, `python_version = "3.13"`)
- **Pre-commit Hooks:** ruff (fix + format) -> isort -> mypy + standard hooks
- **Testing:** pytest + pytest-asyncio, hypothesis, pytest-benchmark

### Common Commands

```bash
# Setup
make venv                  # Create virtual environment
source .venv/bin/activate  # Activate venv
pip install -r requirements.txt -r requirements-dev.txt

# Development
make format                # Format code (ruff format + isort)
make lint                  # Lint code (ruff)
make type                  # Type-check code (mypy)

# Web frontend
cd clients/web && npm ci
cd clients/web && npm run dev
cd clients/web && npm run check:static
cd clients/web && npm run test

# Dependencies
make lock-uv               # Lock dependencies with uv (recommended)

# Docker
# IMPORTANT: `make docker-deploy` builds `ratatoskr:latest` via `docker build`,
# but `docker compose up` uses image `ratatoskr-ratatoskr` (compose prefixes the project name).
# To deploy code changes, always use `docker compose build`:
docker compose -f ops/docker/docker-compose.yml build ratatoskr            # Build with compose (picks up code changes)
docker compose -f ops/docker/docker-compose.yml build --no-cache ratatoskr # Full rebuild (after Dockerfile/dependency changes)
docker compose -f ops/docker/docker-compose.yml down && docker compose -f ops/docker/docker-compose.yml up -d  # Restart with new image

# Legacy standalone build (NOT used by docker compose):
docker build -f ops/docker/Dockerfile -t ratatoskr:latest .
docker run --env-file .env -v $(pwd)/data:/data --name ratatoskr ratatoskr:latest

# CLI Summary Runner
python -m app.cli.summary --url https://example.com/article
python -m app.cli.summary --accept-multiple --json-path out.json --log-level DEBUG
```

### Testing

- **Unit Tests:** Focus on pure functions (URL normalization, JSON validation, message mapping)
- **Integration Tests:** Mock Firecrawl/OpenRouter responses
- **E2E Tests:** Gated by `E2E=1` environment variable
- Test files in `tests/` directory (follow `test_*.py` naming)
- **Test DB Helpers:** `tests/db_helpers.py` provides standalone CRUD functions (`create_request`, `insert_summary`, `upsert_summary`, etc.) for test setup -- use these instead of calling ORM models directly for common operations

### CI/CD

GitHub Actions (`.github/workflows/ci.yml`) enforces:

- Lockfile freshness (rebuilds from `pyproject.toml`)
- Lint (ruff), format check (ruff format, isort), type check (mypy)
- Unit tests with coverage (pytest, 80% threshold)
- Frontend jobs: `web-build`, `web-test`, `web-static-check`
- Docker image build
- OpenAPI spec validation, code complexity (radon)
- Codecov coverage reporting
- Integration tests
- Security: Bandit (SAST), pip-audit + Safety (dependency vulns), Gitleaks (secrets)
- Optional GHCR publishing when `PUBLISH_DOCKER=true`
- PR summary automation

## Important Considerations

### When Making Changes

1. **URL Flow Changes:**
   - Respect URL normalization (`app/core/url_utils.py`) -- all URLs must be normalized before deduplication
   - Preserve `dedupe_hash` (sha256) for idempotence
   - Always persist scraper responses in `crawl_results` table (`FirecrawlResult` is the universal output model)
   - Content extraction uses `ContentScraperChain` (ordered fallback: Scrapling -> Crawl4AI -> Firecrawl (self-hosted) -> Defuddle (self-hosted) -> Playwright -> Crawlee -> Direct HTML -> Scrapegraph-AI). See `app/adapters/content/scraper/` for protocol, chain, factory, and providers
   - Check `app/adapters/content/url_processor.py` for orchestration logic
   - **URL Flow models** (`app/adapters/content/url_flow_models.py`):
     - `URLFlowRequest` -- request envelope: wraps the Telegram message, raw URL text, correlation ID, and Telegram-specific callbacks (progress tracker, phase-change callback)
     - `URLFlowContext` -- prepared state bag: populated after extraction, holds dedupe_hash, req_id, extracted content, chosen language, prompt, chunking config. Passed from context builder into the LLM summarization step
     - `URLProcessingFlowResult` -- batch-mode result: success/failure status and title for batch progress tracking
     - When adding fields to `URLFlowContext`, also update `URLFlowContextBuilder` (`url_flow_context_builder.py`) and any callers that destructure the context

2. **Summary Contract Changes:**
   - Update `app/core/summary_contract.py` validation functions
   - Update LLM prompts in `app/prompts/` (both `en/` and `ru/` versions)
   - Update docs/SPEC.md to document new fields
   - Ensure backward compatibility with existing DB summaries

3. **Database Schema Changes:**
   - Use `app/cli/migrate_db.py` for migrations
   - Update `app/db/models.py` (Peewee ORM models)
   - Document in docs/SPEC.md data model section
   - Consider migration path for existing data

4. **Telegram Message Handling:**
   - All messages flow through `message_router.py`
   - Access control is enforced in `access_controller.py` (check `ALLOWED_USER_IDS`)
   - Full message snapshots are stored in `telegram_messages` table
   - Use `ResponseFormatter` for all replies (centralizes logging and error handling)

5. **External API Changes:**
   - Firecrawl: Check docs at https://docs.firecrawl.dev/api-reference/endpoint/scrape
   - OpenRouter: Check docs at https://openrouter.ai/docs/api-reference/chat-completion
   - Both services have retry logic with exponential backoff
   - Always redact `Authorization` headers before logging

6. **Error Handling:**
   - All user-visible errors must include `Error ID: <correlation_id>`
   - Correlation IDs tie Telegram messages -> DB requests -> logs
   - Use structured logging (`app/core/logging_utils.py`)
   - Persist all LLM failures in `llm_calls` table (even errors)

7. **Concurrency:**
   - Semaphore-based rate limiting for Firecrawl/OpenRouter (`MAX_CONCURRENT_CALLS`)
   - Async/await throughout (Telethon, httpx, SQLite via peewee-async patterns)
   - Optional `uvloop` for async performance

8. **Web Frontend Changes (`clients/web/`):**
   - Read `docs/reference/frontend-web.md` before changing web architecture, routing, auth, or data layer behavior
   - Keep same-host serving contract intact (`/web`, `/web/*`, `/static/web/*`)
   - Preserve hybrid auth behavior (Telegram WebApp header mode and JWT mode with refresh)
   - Web UI must adapt to ≤768px via container queries on AppShell main; see DESIGN.md Mobile section.
   - Run `cd clients/web && npm run check:static && npm run test` before finalizing

### Security Considerations

- **Secrets:** All secrets via env vars (never in DB or logs)
- **Access Control:** Single-user whitelist (`ALLOWED_USER_IDS`)
- **Input Validation:** Validate all URLs, escape JSON strings
- **Authorization Redaction:** Strip `Authorization` headers before persisting
- **No PII:** Only store Telegram user IDs (no phone numbers, real names)

### Language Support

- Language detection via `app/core/lang.py`
- Prompts in `app/prompts/` (for example `summary_system_en.txt`, `summary_system_ru.txt`)
- Configurable preference: `PREFERRED_LANG=auto| en |ru`
- Detection result stored in `requests.lang_detected`

### YouTube Video Support

YouTube URL detection, transcript extraction, and video download are handled by `app/adapters/youtube/`. Supports all major URL formats (watch, shorts, live, embed, mobile, music). See README.md for details.

### Twitter/X Content Extraction

Twitter/X URLs (tweets, threads, X Articles) are handled by `app/adapters/twitter/`. Uses a two-tier extraction strategy:

1. **Firecrawl** (default, free) -- works for some public tweets
2. **Playwright** (opt-in via `TWITTER_PLAYWRIGHT_ENABLED`) -- intercepts GraphQL API for tweets/threads, DOM-scrapes X Articles. Requires cookies.txt and Chromium.

Key files: `url_patterns.py` (URL parsing), `graphql_parser.py` (TweetData extraction), `text_formatter.py` (LLM-ready text), `playwright_client.py` (browser automation), `twitter_extractor.py` (orchestrator). Config: `app/config/twitter.py`.

### Web Search Enrichment (Optional)

When `WEB_SEARCH_ENABLED=true`, the bot enriches summaries with current web context via a two-pass LLM architecture. See README.md for details.

### Debugging Tips

1. **Correlation IDs:** Every request gets a unique `correlation_id` -- use it to trace through logs and DB
2. **Debug Payloads:** Set `DEBUG_PAYLOADS=1` to log Firecrawl/OpenRouter request/response previews (Authorization redacted)
3. **CLI Runner:** Use `python -m app.cli.summary` to test URL processing without Telegram
4. **Database Inspection:** SQLite at `DB_PATH` (default: `/data/ratatoskr.db`) -- use any SQLite browser
5. **Logs:** Structured JSON logs to stdout; use `LOG_LEVEL=DEBUG` for verbose traces
6. **Scraper Chain:** Each provider logs success/failure with provider name. Check logs for `scraper` context to see which provider served the request and which ones failed in the fallback chain. Config in `app/config/scraper.py` (`ScraperConfig`)

### Multi-Agent Architecture

Four specialized agents (ContentExtraction, Summarization, Validation, WebSearch) coordinate via an AgentOrchestrator (multi-step pipeline) or SingleAgentOrchestrator (single-agent execution). The SummarizationAgent implements a self-correction feedback loop (retry with error feedback up to 3x). See `docs/explanation/multi-agent-architecture.md` for complete documentation.

### Additional Subsystems

- **Collections** -- User-created collections with items, collaborators, and invite links (`app/db/models.py`: Collection, CollectionItem, CollectionCollaborator, CollectionInvite)
- **Device Sync** -- Multi-device sync with full/delta modes and conflict resolution (`app/api/routers/sync.py`, UserDevice model)
- **Event Bus** -- Internal event publishing/subscribing (`app/infrastructure/messaging/`)
- **Chroma Vector Store** -- Semantic search via ChromaDB embeddings (`app/infrastructure/`, `app/cli/backfill_chroma_store.py`). Embedding provider switchable via `EmbeddingConfig` (local sentence-transformers or Gemini API); see `app/infrastructure/embedding/embedding_factory.py`
- **PDF Export** -- Summary export to PDF via weasyprint
- **Background Scheduling** -- APScheduler-based background task processing with Redis distributed locks
- **Channel Digest** -- Scheduled digests of subscribed Telegram channels via userbot. Commands: `/init_session`, `/digest`, `/channels`, `/subscribe`, `/unsubscribe`. Uses a separate Telethon userbot session to read channel posts. Bot-mediated session init via Telegram Mini App OTP/2FA flow. Ops reference: `docs/reference/digest-subsystem-ops.md`.

### Safety Hooks

Claude Code hooks provide automatic safety checks. See `docs/reference/claude-code-hooks.md`.

## Common Tasks

### Adding a New Bot Command

1. Create a handler in `app/adapters/telegram/command_handlers/`
2. Register via `CommandRegistry.register_command()` in `app/adapters/telegram/commands.py`
3. The message router delegates automatically to registered commands
4. Add tests in `tests/`

### Adding a New Summary Field

1. Update `app/core/summary_contract.py` with new validation logic
2. Update `app/prompts/summary_system_en.txt` and `app/prompts/summary_system_ru.txt` with new field instructions
3. Update docs/SPEC.md Summary JSON contract section
4. Test with CLI runner: `python -m app.cli.summary --url <test-url>`

### Adding a New External Service

1. Create new adapter in `app/adapters/<service>/`
2. Create client class (e.g., `<service>_client.py`)
3. Add error handling and retry logic (see `app/adapters/openrouter/error_handler.py` for reference)
4. Add request/response models in `app/models/`
5. Persist API calls in new DB table (follow `llm_calls` pattern)
6. Update config (`app/config/`) with new env vars

### Debugging a Failing Summarization

1. Find `correlation_id` from error message
2. Query SQLite: `SELECT * FROM requests WHERE id = '<correlation_id>'`
3. Check `crawl_results` for Firecrawl response
4. Check `llm_calls` for OpenRouter requests/responses
5. Inspect `summaries` table for final JSON payload
6. Review logs for structured events with matching `correlation_id`

## External Service References

- **Firecrawl:** https://docs.firecrawl.dev/api-reference/endpoint/scrape | Integration: `app/adapters/content/content_extractor.py`
- **OpenRouter:** https://openrouter.ai/docs/api-reference/chat-completion | Integration: `app/adapters/openrouter/openrouter_client.py`
- **Telethon:** https://docs.telethon.dev/ | Integration: `app/adapters/telegram/telegram_bot.py`

## File References

When making changes, these are the most critical files to understand:

- **`app/adapters/telegram/message_router.py`** -- Central routing logic
- **`app/adapters/content/url_processor.py`** -- URL processing orchestration
- **`app/core/summary_contract.py`** -- Summary validation (strict contract)
- **`app/core/summary_schema.py`** -- Summary Pydantic model (full schema)
- **`app/core/url_utils.py`** -- URL normalization and deduplication
- **`app/db/models.py`** -- Database schema (ORM models)
- **`app/db/session.py`** -- `DatabaseSessionManager` (sole DB entry point)
- **`app/config/settings.py`** -- Configuration loading
- **`app/config/scraper.py`** -- Scraper chain configuration (`ScraperConfig`)
- **`app/adapters/content/scraper/`** -- `ContentScraperProtocol`, `ContentScraperChain`, `ContentScraperFactory`, providers
- **`app/api/main.py`** -- Mobile API entry point
- **`docs/reference/frontend-web.md`** -- Web frontend architecture, auth, and local workflow
- **`clients/web/src/App.tsx`** -- Web route map and route guards
- **`clients/web/src/auth/AuthProvider.tsx`** -- Hybrid auth mode selection and session handling
- **`app/mcp/server.py`** -- MCP server for AI agents
- **`bot.py`** -- Entrypoint (wires everything together)
- **`docs/SPEC.md`** -- Full technical specification (canonical reference)
- **`DESIGN.md`** -- Frost design system specification (DESIGN.md format, https://github.com/google-labs-code/design.md). Canonical reference for tokens, typography, components, and UI rules for the web client.

## Impeccable Design Skills

Curated UI/UX design skills from [impeccable](https://github.com/pbakaus/impeccable) (Apache 2.0). Available as `/i-*` commands for the web frontend.

| Command | Purpose |
|---------|---------|
| `/i-frontend-design` | Core design framework -- run first to establish design context |
| `/i-audit` | Technical quality checks (accessibility, performance, responsive, anti-patterns) |
| `/i-polish` | Final refinement across alignment, typography, color, interactions |
| `/i-normalize` | Align UI to project design system tokens, spacing, patterns |
| `/i-typeset` | Typography hierarchy, font choices, readability |
| `/i-colorize` | Strategic color usage with 60-30-10 distribution |
| `/i-clarify` | Improve UX copy, error messages, labels |
| `/i-harden` | i18n, error handling, edge cases, text overflow resilience |
| `/i-optimize` | Core Web Vitals, rendering, bundle size performance |

Most skills require `/i-frontend-design` context first. Skills are in `.claude/skills/i-*/` (Claude Code) and `.codex/skills/i-*/` (Codex CLI).

## Best Practices

1. **Always read docs/SPEC.md first** -- it's the authoritative source of truth
2. **Preserve correlation IDs** -- they're essential for debugging
3. **Validate summary JSON** -- use `app/core/summary_contract.py` functions
4. **Test with CLI runner** -- faster iteration than full bot testing
5. **Follow pre-commit hooks** -- run `make format` before committing
6. **Update both en/ and ru/ prompts** -- when changing LLM behavior
7. **Document DB schema changes** -- update docs/SPEC.md data model section
8. **Persist everything** -- Firecrawl responses, LLM calls, Telegram messages (observability is key)
9. **Use structured logging** -- include correlation IDs and context in all logs
10. **Respect async patterns** -- use `await` properly, don't block the event loop
11. **State scope explicitly when you give an instruction** -- "apply this to every section, not just the first." Don't rely on the model generalizing silently
12. **Tell the model what to do, not what to avoid** -- prefer "use the existing helper in `tests/db_helpers.py`" over "don't create new test fixtures"
13. **Keep tool/skill guidance in the tool's own description** -- not in CLAUDE.md prose. CLAUDE.md is for project context; per-tool semantics belong with the tool
14. **Make independent tool calls in parallel** -- only sequence when one result determines the next call's parameters
15. **Investigate before claiming** -- never assert behavior of code you haven't read; cite `file:line` for each non-obvious claim

## Quick Reference: Environment Variables

```bash
# Required
API_ID=...                          # Telegram API ID
API_HASH=...                        # Telegram API hash
BOT_TOKEN=...                       # Telegram bot token
ALLOWED_USER_IDS=123456789          # Comma-separated owner IDs
OPENROUTER_API_KEY=...              # OpenRouter API key
OPENROUTER_MODEL=deepseek/deepseek-v3.2  # Default model
OPENROUTER_FALLBACK_MODELS=qwen/qwen3.5-plus-02-15,google/gemini-3.1-flash-lite-preview,moonshotai/kimi-k2.5

# Scraper chain (all optional -- defaults enable full fallback chain)
# Default order: scrapling -> crawl4ai -> firecrawl -> defuddle -> playwright -> crawlee -> direct_html -> scrapegraph_ai
FIRECRAWL_API_KEY=                  # Optional; used only by TopicSearchService web search (NOT the scraper chain)
FIRECRAWL_SELF_HOSTED_ENABLED=false
FIRECRAWL_SELF_HOSTED_URL=http://firecrawl-api:3002  # Self-hosted Firecrawl (Docker Compose service)
SCRAPER_ENABLED=true
SCRAPER_PROFILE=balanced
SCRAPER_BROWSER_ENABLED=true
SCRAPER_SCRAPLING_ENABLED=true      # Enable Scrapling provider (primary, in-process)
SCRAPER_CRAWL4AI_ENABLED=true       # Enable Crawl4AI provider (self-hosted Docker sidecar)
SCRAPER_CRAWL4AI_URL=http://crawl4ai:11235
SCRAPER_CRAWL4AI_TOKEN=             # Bearer token for secured Crawl4AI instances (optional)
SCRAPER_CRAWL4AI_TIMEOUT_SEC=60
SCRAPER_DEFUDDLE_ENABLED=true       # Enable Defuddle API provider (self-hosted, default on)
SCRAPER_DEFUDDLE_TIMEOUT_SEC=20
SCRAPER_DEFUDDLE_API_BASE_URL=http://defuddle-api:3003  # Self-hosted Defuddle (Docker Compose service)
SCRAPER_FIRECRAWL_TIMEOUT_SEC=90
SCRAPER_PLAYWRIGHT_ENABLED=true
SCRAPER_CRAWLEE_ENABLED=true
SCRAPER_DIRECT_HTML_ENABLED=true
SCRAPER_SCRAPEGRAPH_ENABLED=true    # Enable ScrapeGraph-AI last-resort provider (requires scrapegraphai pkg)
SCRAPER_SCRAPEGRAPH_TIMEOUT_SEC=90

# Channel Digest (optional)
DIGEST_ENABLED=false                # Enable channel digest subsystem
API_BASE_URL=http://localhost:8000  # Mobile API base URL (for session init)

# Embedding provider (optional -- defaults to local sentence-transformers)
EMBEDDING_PROVIDER=local              # "local" (sentence-transformers) or "gemini"
GEMINI_API_KEY=                        # Required when provider=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-2-preview  # Model ID
GEMINI_EMBEDDING_DIMENSIONS=768       # Output dimensions (1-3072)
EMBEDDING_MAX_TOKEN_LENGTH=512        # Max tokens for text preparation

# ElevenLabs TTS (optional)
ELEVENLABS_ENABLED=false              # Enable text-to-speech
ELEVENLABS_API_KEY=                   # ElevenLabs API key
```

Full reference: `docs/environment_variables.md`

---

**Last Updated:** 2026-05-04

For questions about the codebase, always refer to:

1. This file (CLAUDE.md) for AI assistant guidance
2. docs/SPEC.md for technical specification
3. docs/reference/frontend-web.md for web frontend contracts and workflows
4. DESIGN.md for the Frost design system (tokens, typography, components, anti-patterns). Read before any web UI change.
5. README.md for user-facing documentation
6. Code comments and docstrings for implementation details

---

## Task Board

This repository uses Obsidian Tasks-compatible Markdown task lines as the canonical task system.
Use the `repo-task-board` skill for all task-related operations.

Canonical files:

- `docs/tasks/issues/<slug>.md` — **source of truth** — one note per task (YAML frontmatter + canonical `- [ ]` line + spec)
- `docs/tasks/active.md` — Obsidian Tasks query view (`#status/doing`, `#status/review`)
- `docs/tasks/backlog.md` — Obsidian Tasks query view (`#status/backlog`)
- `docs/tasks/blocked.md` — Obsidian Tasks query view (`#status/blocked`)
- `docs/tasks/dashboard.md` — Obsidian Tasks query hub + Bases view links
- `docs/tasks/board.md` — Kanban board (visual layer; source of truth is `issues/`)

Canonical task syntax (lives inside `docs/tasks/issues/<slug>.md`):

```md
- [ ] #task <imperative title> #repo/ratatoskr #area/<area> #status/<status> <priority>
```

Per-task note YAML frontmatter:

```yaml
---
title: Imperative task title
status: doing          # backlog | todo | doing | review | blocked | done | dropped
area: auth             # auth | api | kmp | sync | ci | frontend | observability | testing | content | scraper | llm | db | docs | ops
priority: high         # critical | high | medium | low
owner: Role name
blocks: []
blocked_by: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Lifecycle: create via Templater template → transitions update `status:` + `#status/*` tag → delete file on close (git history is the audit trail). Do NOT add task lines to `active.md`, `backlog.md`, or `blocked.md` — those are query-only views.

Invoke the `repo-task-board` skill when the user mentions: roadmap, TODO, backlog, Kanban, task board, sprint, blocked work, or agent-ready work.
