# CLAUDE.md -- AI Assistant Guide for Bite-Size Reader

This document helps AI assistants (like Claude) understand and work effectively with the Bite-Size Reader codebase.

## Project Overview

**Bite-Size Reader** is an async Telegram bot that:
- Accepts web article URLs and summarizes them using Firecrawl (content extraction) + OpenRouter (LLM summarization)
- Accepts YouTube video URLs, downloads them in 1080p, extracts transcripts, and generates summaries
- Accepts forwarded channel posts and summarizes them directly
- Returns structured JSON summaries with a strict contract
- Stores all artifacts (Telegram messages, crawl results, video downloads, LLM calls, summaries) in SQLite
- Runs as a single Docker container with owner-only access control

**Tech Stack:**
- Python 3.13+
- Pyrogram (async Telegram MTProto)
- Firecrawl API (content extraction for web articles)
- yt-dlp (YouTube video downloading)
- youtube-transcript-api (YouTube transcript extraction)
- ffmpeg (video/audio merging for yt-dlp)
- OpenRouter API (OpenAI-compatible LLM completions)
- SQLite (persistence with Peewee ORM)
- httpx (async HTTP client)

## Architecture Overview

### Core Pipeline Flow

```
Telegram Message -> MessageHandler -> AccessController -> MessageRouter
                                                            |
                    +---------------------------------------+-----------+
                    |                                                   |
              URL Handler                                  Forward Processor
                    |                                                   |
              URLProcessor                                  LLMSummarizer
                    |                                                   |
     ContentExtractor -> Firecrawl                              OpenRouter
                    |                                                   |
              LLMSummarizer -> OpenRouter                     Summary JSON
                    |                                                   |
              Summary JSON                                 ResponseFormatter
                    |                                                   |
           ResponseFormatter -------------------------------------------+
                    |
         Telegram Reply + SQLite Storage
```

### Key Components

- **Telegram Layer** (`app/adapters/telegram/`) -- Bot orchestration, message routing, access control, persistence, command processing, URL/forward handling
- **Content Pipeline** (`app/adapters/content/`) -- Firecrawl integration, content chunking, LLM summarization, web search context
- **YouTube Adapter** (`app/adapters/youtube/`) -- yt-dlp video download, transcript extraction, storage management
- **External Services** (`app/adapters/openrouter/`, `app/adapters/external/`) -- OpenRouter client, Firecrawl parser, response formatting
- **Core Utilities** (`app/core/`) -- URL normalization, JSON parsing/repair, summary contract validation, language detection, structured logging
- **Database** (`app/db/`) -- SQLite schema, Peewee ORM models, migrations
- **CLI Tools** (`app/cli/`) -- Summary runner, search, migrations, MCP server, embedding backfill
- **Mobile API** (`app/api/`) -- FastAPI REST API with JWT auth, sync, background processing
- **Multi-Agent System** (`app/agents/`) -- Content extraction, summarization with self-correction, validation, web search agents. See `docs/multi_agent_architecture.md`
- **Search Services** (`app/services/`) -- Topic search, vector/hybrid search, embeddings, reranking, query expansion
- **MCP Server** (`app/mcp/`) -- Model Context Protocol server for AI agent access. See `docs/mcp_server.md`
- **Domain Layer** (`app/domain/`) -- DDD models and services
- **Infrastructure** (`app/infrastructure/`) -- Persistence layer, event bus, vector store

## Directory Structure

```
app/
+-- adapters/           # External service integrations
|   +-- content/        # URL processing pipeline
|   +-- external/       # Firecrawl parser, response formatter
|   +-- openrouter/     # OpenRouter client and helpers
|   +-- telegram/       # Telegram bot logic
|   +-- youtube/        # YouTube video download and transcript extraction
+-- agents/             # Multi-agent system (extraction, summarization, validation, web search)
+-- api/                # Mobile API (FastAPI, JWT auth, sync)
|   +-- models/         # Pydantic request/response models
|   +-- routers/        # Route handlers (auth, summaries, sync)
|   +-- services/       # API business logic
+-- cli/                # CLI tools (summary runner, search, MCP server, migrations)
+-- core/               # Shared utilities (URL, JSON, logging, lang)
+-- db/                 # Database schema and models
+-- di/                 # Dependency injection
+-- domain/             # Domain models and services (DDD patterns)
+-- handlers/           # Request handlers
+-- infrastructure/     # Persistence, event bus, vector store
+-- mcp/                # MCP server for AI agent access
+-- models/             # Pydantic/dataclass models
|   +-- llm/            # LLM config models
|   +-- telegram/       # Telegram entity models
+-- presentation/       # Presentation layer
+-- prompts/            # LLM system prompts (en/ru)
+-- security/           # Security utilities
+-- services/           # Search and other domain services
+-- types/              # Type definitions
+-- utils/              # Helper utilities (progress, formatting, validation)
```

## Summary JSON Contract

Defined in `app/core/summary_contract.py` and documented in SPEC.md. Key fields: `summary_250`, `summary_1000`, `tldr`, `key_ideas`, `topic_tags`, `entities`, `estimated_reading_time_min`, `key_stats`, `answered_questions`, `readability`, `seo_keywords`.

## Development Workflow

### Code Standards

- **Formatting:** Black (line length 100) + isort (profile=black) + ruff format
- **Linting:** Ruff (see `pyproject.toml` for rules)
- **Type Checking:** mypy (permissive config, `python_version = "3.13"`)
- **Pre-commit Hooks:** Run ruff -> isort -> black in sequence
- **Testing:** unittest + pytest-asyncio

### Common Commands

```bash
# Setup
make venv                  # Create virtual environment
source .venv/bin/activate  # Activate venv
pip install -r requirements.txt -r requirements-dev.txt

# Development
make format                # Format code (black + isort + ruff format)
make lint                  # Lint code (ruff)
make type                  # Type-check code (mypy)

# Dependencies
make lock-uv               # Lock dependencies with uv (recommended)
make lock-piptools         # Lock dependencies with pip-tools

# Docker
docker build -t bite-size-reader .
docker run --env-file .env -v $(pwd)/data:/data --name bsr bite-size-reader

# CLI Summary Runner
python -m app.cli.summary --url https://example.com/article
python -m app.cli.summary --accept-multiple --json-path out.json --log-level DEBUG
```

### Testing

- **Unit Tests:** Focus on pure functions (URL normalization, JSON validation, message mapping)
- **Integration Tests:** Mock Firecrawl/OpenRouter responses
- **E2E Tests:** Gated by `E2E=1` environment variable
- Test files in `tests/` directory (follow `test_*.py` naming)

### CI/CD

GitHub Actions (`.github/workflows/ci.yml`) enforces:
- Lockfile freshness (rebuilds from `pyproject.toml`)
- Lint (ruff), format check (black, isort), type check (mypy)
- Unit tests (unittest)
- Matrix tests with/without Pydantic
- Docker image build
- Security: Bandit (SAST), pip-audit + Safety (dependency vulns), Gitleaks (secrets)
- Optional GHCR publishing when `PUBLISH_DOCKER=true`

## Important Considerations

### When Making Changes

1. **URL Flow Changes:**
   - Respect URL normalization (`app/core/url_utils.py`) -- all URLs must be normalized before deduplication
   - Preserve `dedupe_hash` (sha256) for idempotence
   - Always persist Firecrawl responses in `crawl_results` table
   - Check `app/adapters/content/url_processor.py` for orchestration logic

2. **Summary Contract Changes:**
   - Update `app/core/summary_contract.py` validation functions
   - Update LLM prompts in `app/prompts/` (both `en/` and `ru/` versions)
   - Update SPEC.md to document new fields
   - Ensure backward compatibility with existing DB summaries

3. **Database Schema Changes:**
   - Use `app/cli/migrate_db.py` for migrations
   - Update `app/db/models.py` (Peewee ORM models)
   - Document in SPEC.md data model section
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
   - Async/await throughout (Pyrogram, httpx, SQLite via peewee-async patterns)
   - Optional `uvloop` for async performance

### Security Considerations

- **Secrets:** All secrets via env vars (never in DB or logs)
- **Access Control:** Single-user whitelist (`ALLOWED_USER_IDS`)
- **Input Validation:** Validate all URLs, escape JSON strings
- **Authorization Redaction:** Strip `Authorization` headers before persisting
- **No PII:** Only store Telegram user IDs (no phone numbers, real names)

### Language Support

- Language detection via `app/core/lang.py`
- Prompts in `app/prompts/en/` and `app/prompts/ru/`
- Configurable preference: `PREFERRED_LANG=auto|en|ru`
- Detection result stored in `requests.lang_detected`

### YouTube Video Support

YouTube URL detection, transcript extraction, and video download are handled by `app/adapters/youtube/`. Supports all major URL formats (watch, shorts, live, embed, mobile, music). See README.md for details.

### Web Search Enrichment (Optional)

When `WEB_SEARCH_ENABLED=true`, the bot enriches summaries with current web context via a two-pass LLM architecture. See README.md for details.

### Debugging Tips

1. **Correlation IDs:** Every request gets a unique `correlation_id` -- use it to trace through logs and DB
2. **Debug Payloads:** Set `DEBUG_PAYLOADS=1` to log Firecrawl/OpenRouter request/response previews (Authorization redacted)
3. **CLI Runner:** Use `python -m app.cli.summary` to test URL processing without Telegram
4. **Database Inspection:** SQLite at `DB_PATH` (default: `/data/app.db`) -- use any SQLite browser
5. **Logs:** Structured JSON logs to stdout; use `LOG_LEVEL=DEBUG` for verbose traces

### Multi-Agent Architecture

Four specialized agents (ContentExtraction, Summarization, Validation, WebSearch) coordinate via an AgentOrchestrator. The SummarizationAgent implements a self-correction feedback loop (retry with error feedback up to 3x). See `docs/multi_agent_architecture.md` for complete documentation.

### Safety Hooks

Claude Code hooks provide automatic safety checks. See `docs/claude_code_hooks.md`.

## Common Tasks

### Adding a New Bot Command

1. Add command to `app/adapters/telegram/commands.py` (`COMMAND_NAMES` and `COMMAND_DESCRIPTIONS`)
2. Implement handler in `app/adapters/telegram/command_processor.py`
3. Update `message_router.py` to route to new handler
4. Add tests in `tests/`

### Adding a New Summary Field

1. Update `app/core/summary_contract.py` with new validation logic
2. Update `app/prompts/en/summary.txt` and `app/prompts/ru/summary.txt` with new field instructions
3. Update SPEC.md Summary JSON contract section
4. Test with CLI runner: `python -m app.cli.summary --url <test-url>`

### Adding a New External Service

1. Create new adapter in `app/adapters/<service>/`
2. Create client class (e.g., `<service>_client.py`)
3. Add error handling and retry logic (see `app/adapters/openrouter/error_handler.py` for reference)
4. Add request/response models in `app/models/`
5. Persist API calls in new DB table (follow `llm_calls` pattern)
6. Update config (`app/config.py`) with new env vars

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
- **Pyrogram:** https://telegramplayground.github.io/pyrogram/ | Integration: `app/adapters/telegram/telegram_bot.py`

## File References

When making changes, these are the most critical files to understand:

- **`app/adapters/telegram/message_router.py`** -- Central routing logic
- **`app/adapters/content/url_processor.py`** -- URL processing orchestration
- **`app/core/summary_contract.py`** -- Summary validation (strict contract)
- **`app/core/url_utils.py`** -- URL normalization and deduplication
- **`app/db/models.py`** -- Database schema (ORM models)
- **`app/config.py`** -- Configuration loading
- **`app/api/main.py`** -- Mobile API entry point
- **`app/mcp/server.py`** -- MCP server for AI agents
- **`bot.py`** -- Entrypoint (wires everything together)
- **`SPEC.md`** -- Full technical specification (canonical reference)

## Best Practices

1. **Always read SPEC.md first** -- it's the authoritative source of truth
2. **Preserve correlation IDs** -- they're essential for debugging
3. **Validate summary JSON** -- use `app/core/summary_contract.py` functions
4. **Test with CLI runner** -- faster iteration than full bot testing
5. **Follow pre-commit hooks** -- run `make format` before committing
6. **Update both en/ and ru/ prompts** -- when changing LLM behavior
7. **Document DB schema changes** -- update SPEC.md data model section
8. **Persist everything** -- Firecrawl responses, LLM calls, Telegram messages (observability is key)
9. **Use structured logging** -- include correlation IDs and context in all logs
10. **Respect async patterns** -- use `await` properly, don't block the event loop

## Quick Reference: Environment Variables

```bash
# Required
API_ID=...                          # Telegram API ID
API_HASH=...                        # Telegram API hash
BOT_TOKEN=...                       # Telegram bot token
ALLOWED_USER_IDS=123456789          # Comma-separated owner IDs
FIRECRAWL_API_KEY=...               # Firecrawl API key
OPENROUTER_API_KEY=...              # OpenRouter API key
OPENROUTER_MODEL=deepseek/deepseek-v3.2  # Default model
OPENROUTER_FALLBACK_MODELS=moonshotai/kimi-k2.5,qwen/qwen3-max,deepseek/deepseek-r1
```

Full reference: `docs/environment_variables.md`

---

**Last Updated:** 2026-02-03

For questions about the codebase, always refer to:
1. This file (CLAUDE.md) for AI assistant guidance
2. SPEC.md for technical specification
3. README.md for user-facing documentation
4. Code comments and docstrings for implementation details
