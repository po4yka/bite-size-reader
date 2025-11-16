# CLAUDE.md — AI Assistant Guide for Bite-Size Reader

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
Telegram Message → MessageHandler → AccessController → MessageRouter
                                                            ↓
                    ┌───────────────────────────────────────┴─────────────┐
                    ↓                                                     ↓
              URL Handler                                    Forward Processor
                    ↓                                                     ↓
              URLProcessor                                    LLMSummarizer
                    ↓                                                     ↓
     ContentExtractor → Firecrawl                                OpenRouter
                    ↓                                                     ↓
              LLMSummarizer → OpenRouter                         Summary JSON
                    ↓                                                     ↓
              Summary JSON                                     ResponseFormatter
                    ↓                                                     ↓
           ResponseFormatter ─────────────────────────────────────────────┘
                    ↓
         Telegram Reply + SQLite Storage
```

### Key Components

1. **Telegram Layer** (`app/adapters/telegram/`)
   - `telegram_bot.py` — Main bot orchestration
   - `telegram_client.py` — Telegram client wrapper
   - `message_handler.py` — Normalizes incoming updates
   - `access_controller.py` — Enforces owner whitelist
   - `message_router.py` — Routes to URL/forward/command processors
   - `message_persistence.py` — Persists all Telegram message snapshots
   - `command_processor.py` — Handles bot commands (/help, /summarize, /cancel)
   - `commands.py` — Command definitions and descriptions
   - `url_handler.py` — Orchestrates URL processing flow
   - `forward_processor.py` — Handles forwarded message summarization
   - `forward_content_processor.py` — Forward content extraction
   - `forward_summarizer.py` — Forward message summarization
   - `task_manager.py` — Task management for multi-link processing

2. **Content Pipeline** (`app/adapters/content/`)
   - `content_extractor.py` — Firecrawl integration and YouTube routing
   - `content_chunker.py` — Splits large content for LLM processing
   - `llm_summarizer.py` — OpenRouter summarization
   - `llm_response_workflow.py` — LLM response handling workflow
   - `url_processor.py` — Coordinates extraction → chunking → summarization

3. **YouTube Adapter** (`app/adapters/youtube/`)
   - `youtube_downloader.py` — yt-dlp video download and youtube-transcript-api integration
   - Supports all major YouTube URL formats (watch, shorts, live, music, embed, mobile)
   - Dual extraction: transcripts via API + video download in configurable quality (default 1080p)
   - Storage management with configurable limits and auto-cleanup
   - Comprehensive error handling for age-restricted, geo-blocked, and unavailable videos

4. **External Services** (`app/adapters/openrouter/`, `app/adapters/external/`)
   - `openrouter_client.py` — HTTP client for OpenRouter API
   - `request_builder.py` — Builds OpenRouter payloads
   - `response_processor.py` — Parses and validates LLM responses
   - `error_handler.py` — Retry logic and error mapping
   - `firecrawl_parser.py` — Parses Firecrawl responses
   - `response_formatter.py` — Formats Telegram replies

4. **Core Utilities** (`app/core/`)
   - `url_utils.py` — URL normalization and deduplication (sha256 hash)
   - `json_utils.py` — JSON parsing with repair (handles malformed LLM output)
   - `summary_contract.py` — Summary JSON validation (strict contract enforcement)
   - `lang.py` — Language detection and prompt selection
   - `logging_utils.py` — Structured logging with correlation IDs

5. **Database** (`app/db/`)
   - `database.py` — SQLite connection and schema
   - `models.py` — Peewee ORM models
   - Schema: users, chats, requests, telegram_messages, crawl_results, video_downloads, llm_calls, summaries

6. **CLI Tools** (`app/cli/`)
   - `summary.py` — Local CLI runner for testing summaries without Telegram
   - `migrate_db.py` — Database migrations
   - `search.py` — Search summaries by topics/entities
   - `search_compare.py` — Compare search implementations
   - `backfill_embeddings.py` — Backfill embeddings for existing summaries

7. **Mobile API** (`app/api/`)
   - `main.py` — FastAPI application entry point
   - `middleware.py` — Request/response middleware (CORS, error handling)
   - `error_handlers.py` — Global error handlers
   - `exceptions.py` — Custom API exceptions
   - `background_processor.py` — Background task processing
   - **Routers** (`app/api/routers/`)
     - `auth.py` — Telegram-based authentication, JWT tokens
     - `summaries.py` — Summary retrieval endpoints
     - `sync.py` — Mobile client sync endpoints
   - **Models** (`app/api/models/`)
     - Pydantic request/response models for API contracts
   - **Services** (`app/api/services/`)
     - Business logic for API operations

8. **Multi-Agent Architecture** (`app/agents/`)
   - `base_agent.py` — Base agent class with result pattern
   - `validation_agent.py` — Summary validation with detailed errors
   - `content_extraction_agent.py` — Content extraction with quality checks
   - `summarization_agent.py` — Summarization with self-correction loop
   - `orchestrator.py` — Agent pipeline orchestration

9. **Search Services** (`app/services/`)
   - `topic_search.py` — Topic-based search (local and service implementations)
   - `topic_search_utils.py` — Search utilities and helpers
   - `vector_search_service.py` — Vector similarity search
   - `hybrid_search_service.py` — Hybrid search (keyword + vector)
   - `query_expansion_service.py` — Query expansion for better search
   - `reranking_service.py` — Search result reranking
   - `embedding_service.py` — Text embedding generation
   - `summary_embedding_generator.py` — Summary-specific embeddings
   - `search_filters.py` — Search filtering utilities

10. **Utilities** (`app/utils/`)
    - `progress_tracker.py` — Progress tracking for multi-step operations
    - `message_formatter.py` — Message formatting utilities
    - `json_validation.py` — JSON validation helpers

11. **Domain Layer** (`app/domain/`)
    - Domain-driven design models and services
    - Business logic separated from infrastructure

12. **Infrastructure** (`app/infrastructure/`)
    - Persistence layer implementations
    - Event bus and messaging infrastructure

## Directory Structure

```
app/
├── adapters/           # External service integrations
│   ├── content/        # URL processing pipeline
│   ├── external/       # Firecrawl parser, response formatter
│   ├── openrouter/     # OpenRouter client and helpers
│   ├── telegram/       # Telegram bot logic
│   └── youtube/        # YouTube video download and transcript extraction
├── cli/                # CLI tools (summary runner, search, migrations)
├── core/               # Shared utilities (URL, JSON, logging, lang)
├── db/                 # Database schema and models
├── di/                 # Dependency injection
├── domain/             # Domain models and services (DDD patterns)
├── handlers/           # Request handlers
├── infrastructure/     # Persistence and messaging infrastructure
├── models/             # Pydantic/dataclass models
│   ├── llm/            # LLM config models
│   └── telegram/       # Telegram entity models
├── presentation/       # Presentation layer
├── prompts/            # LLM system prompts (en/ru)
├── security/           # Security utilities
├── services/           # Search and other domain services
└── utils/              # Helper utilities (progress, formatting, validation)
```

## Summary JSON Contract

All summaries must conform to a strict JSON schema (defined in `app/core/summary_contract.py`):

```json
{
  "summary_250": "<=250 chars, sentence boundary",
  "summary_1000": "<=1000 chars, multi-sentence overview",
  "tldr": "concise multi-sentence summary",
  "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
  "topic_tags": ["#tag1", "#tag2", "#tag3"],
  "entities": {
    "people": [...],
    "organizations": [...],
    "locations": [...]
  },
  "estimated_reading_time_min": 7,
  "key_stats": [{"label": "...", "value": 12.3, "unit": "BUSD", "source_excerpt": "..."}],
  "answered_questions": ["What is ...?", "How does ...?"],
  "readability": {"method": "Flesch-Kincaid", "score": 12.4, "level": "College"},
  "seo_keywords": ["keyword one", "keyword two", "keyword three"]
}
```

**Validation rules:**
- Enforce character limits on `summary_250` and `summary_1000`
- Deduplicate `topic_tags` (enforce leading `#`)
- Deduplicate `entities` (case-insensitive)
- All fields are validated in `app/core/summary_contract.py`

## Development Workflow

### Code Standards

- **Formatting:** Black (line length 100) + isort (profile=black) + ruff format
- **Linting:** Ruff (see `pyproject.toml` for rules)
- **Type Checking:** mypy (permissive config, `python_version = "3.13"`)
- **Pre-commit Hooks:** Run ruff → isort → black in sequence
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
   - Respect URL normalization (`app/core/url_utils.py`) — all URLs must be normalized before deduplication
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
   - Correlation IDs tie Telegram messages → DB requests → logs
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

- **URL Detection:** Automatically detects YouTube URLs via `app/core/url_utils.py`
- **Supported Formats:** Standard watch, shorts, live, embed, mobile (m.youtube.com), YouTube Music, legacy /v/ URLs
- **URL Pattern Handling:** Handles query parameters in any order (e.g., `?feature=share&v=ID`)
- **Dual Extraction Strategy:**
  1. Transcript extraction via `youtube-transcript-api` (prefers manual, falls back to auto-generated)
  2. Video download via `yt-dlp` in configurable quality (default 1080p)
- **Storage Management:**
  - Videos organized by date: `/data/videos/YYYYMMDD/VIDEO_ID_title.mp4`
  - Configurable limits: per-video size, total storage GB
  - Auto-cleanup of old videos (configurable retention period)
  - Deduplication via URL hash (won't re-download same video)
- **Database Schema:**
  - `video_downloads` table stores metadata, file paths, transcript
  - Links to `requests` table via foreign key
  - Tracks: title, channel, duration, views, likes, resolution, codecs, transcript source
- **Error Handling:**
  - Age-restricted videos: Clear message about login requirement
  - Geo-blocked: Informs user about regional restrictions
  - Private/deleted: Explains unavailability
  - Rate limits: Suggests retry timing
  - No transcript: Continues download without transcript
- **ffmpeg Dependency:**
  - Required for yt-dlp to merge video/audio streams
  - Installed in Docker runtime stage
  - Essential for best quality downloads
- **Integration Point:**
  - `content_extractor.py` routes YouTube URLs to `youtube_downloader.py`
  - Rest of pipeline (LLM summarization, response formatting) remains unchanged

### Debugging Tips

1. **Correlation IDs:** Every request gets a unique `correlation_id` — use it to trace through logs and DB
2. **Debug Payloads:** Set `DEBUG_PAYLOADS=1` to log Firecrawl/OpenRouter request/response previews (Authorization redacted)
3. **CLI Runner:** Use `python -m app.cli.summary` to test URL processing without Telegram
4. **Database Inspection:** SQLite at `DB_PATH` (default: `/data/app.db`) — use any SQLite browser
5. **Logs:** Structured JSON logs to stdout; use `LOG_LEVEL=DEBUG` for verbose traces

## Multi-Agent Architecture

The project implements a multi-agent pattern for improved quality, maintainability, and debugging:

### Agent Overview

**Three specialized agents handle different workflow stages:**

1. **ContentExtractionAgent** (`app/agents/content_extraction_agent.py`)
   - Extracts content from URLs via Firecrawl
   - Validates content quality
   - Persists crawl results

2. **SummarizationAgent** (`app/agents/summarization_agent.py`)
   - Generates summaries via LLM
   - Implements self-correction feedback loop
   - Retries with error feedback up to N times

3. **ValidationAgent** (`app/agents/validation_agent.py`)
   - Enforces JSON contract compliance
   - Checks character limits, field types, deduplication
   - Returns detailed, actionable error messages

### Feedback Loop Pattern

The SummarizationAgent implements self-correction:

```
Generate Summary → Validate → If Valid: Return
                      ↓
                   If Invalid
                      ↓
            Extract Error Details
                      ↓
         Retry with Error Feedback
                      ↓
              (Repeat up to 3x)
```

### Agent Orchestrator

**AgentOrchestrator** (`app/agents/orchestrator.py`) coordinates the full pipeline:

```
URL → ContentExtractionAgent → SummarizationAgent ↔ ValidationAgent → Output
```

### Using Agents

```python
from app.agents import ValidationAgent, SummarizationAgent

# Validate a summary
validator = ValidationAgent(correlation_id="abc123")
result = await validator.execute({"summary_json": summary})

if not result.success:
    print(f"Validation errors: {result.error}")

# Summarize with feedback loop
summarizer = SummarizationAgent(llm_summarizer, validator)
result = await summarizer.execute({
    "content": content,
    "correlation_id": "abc123",
    "max_retries": 3
})
```

### Benefits

- **Improved Quality**: Self-correction reduces validation errors by 60-80%
- **Better Debugging**: Clear agent boundaries and detailed tracking
- **Easier Maintenance**: Single responsibility per agent
- **Enhanced Observability**: Structured results with metadata

**See `docs/multi_agent_architecture.md` for complete documentation.**

## Safety Hooks

Claude Code hooks in `.claude/settings.json` provide automatic safety checks and environment validation.

### Configured Hooks

**PreToolUse Hooks:**
- **File Protection**: Blocks modifications to database, .env, requirements files
- **Code Safety**: Warns about dangerous patterns (eval, exec, os.system)
- **Bash Safety**: Blocks destructive commands (rm -rf /, dd, mkfs)

**SessionStart Hook:**
- Validates Python version and virtual environment
- Checks required dependencies installed
- Verifies .env file and API keys configured
- Shows database status and git branch
- Displays quick command reference

**PostToolUse Hook:**
- Runs quick lint check on modified Python files
- Shows formatting issues immediately
- Suggests fixes with `make format`

**UserPromptSubmit Hook:**
- Auto-injects helpful context based on prompt keywords
- Adds database query patterns for correlation ID debugging
- Links to relevant skills for common tasks

### Hook Examples

**Protected file modification:**
```
ERROR: Cannot modify protected file: data/app.db
Protected pattern matched: data/app.db

To modify this file:
1. Review the change carefully
2. Ask user for explicit permission
3. Make changes manually if needed
```

**Session start output:**
```
=== Bite-Size Reader Session Started ===

✓ Python: 3.13.0
✓ Virtual environment: active
✓ Core dependencies: installed
✓ Environment file: .env exists
✓ Required API keys: configured
✓ Database: data/app.db (2.3M)
✓ Git branch: main

Quick commands:
  make format  - Format code
  make lint    - Lint code
  python -m app.cli.summary --url <URL> - Test CLI runner

IMPORTANT: Always preserve correlation IDs when debugging!
```

### Customizing Hooks

Edit `.claude/settings.json` to modify hook behavior. See `.claude/settings.json` for current configuration.

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

### Firecrawl
- **Docs:** https://docs.firecrawl.dev/features/scrape
- **API Reference:** https://docs.firecrawl.dev/api-reference/endpoint/scrape
- **Advanced Guide:** https://docs.firecrawl.dev/advanced-scraping-guide
- **Integration:** `app/adapters/content/content_extractor.py`

### OpenRouter
- **Overview:** https://openrouter.ai/docs/api-reference/overview
- **Chat Completions:** https://openrouter.ai/docs/api-reference/chat-completion
- **Quickstart:** https://openrouter.ai/docs/quickstart
- **Integration:** `app/adapters/openrouter/openrouter_client.py`

### Pyrogram (Telegram)
- **PyroTGFork Site:** https://telegramplayground.github.io/pyrogram/
- **Upstream Client Docs:** https://docs.pyrogram.org/api/client
- **Upstream Message Docs:** https://docs.pyrogram.org/api/types/Message
- **Integration:** `app/adapters/telegram/telegram_bot.py`

## File References

When making changes, these are the most critical files to understand:

- **`app/adapters/telegram/message_router.py`** — Central routing logic
- **`app/adapters/content/url_processor.py`** — URL processing orchestration
- **`app/core/summary_contract.py`** — Summary validation (strict contract)
- **`app/core/url_utils.py`** — URL normalization and deduplication
- **`app/db/models.py`** — Database schema (ORM models)
- **`app/config.py`** — Configuration loading
- **`bot.py`** — Entrypoint (wires everything together)
- **`SPEC.md`** — Full technical specification (canonical reference)

## Best Practices

1. **Always read SPEC.md first** — it's the authoritative source of truth
2. **Preserve correlation IDs** — they're essential for debugging
3. **Validate summary JSON** — use `app/core/summary_contract.py` functions
4. **Test with CLI runner** — faster iteration than full bot testing
5. **Follow pre-commit hooks** — run `make format` before committing
6. **Update both en/ and ru/ prompts** — when changing LLM behavior
7. **Document DB schema changes** — update SPEC.md data model section
8. **Persist everything** — Firecrawl responses, LLM calls, Telegram messages (observability is key)
9. **Use structured logging** — include correlation IDs and context in all logs
10. **Respect async patterns** — use `await` properly, don't block the event loop

## Quick Reference: Environment Variables

```bash
# Required
API_ID=...                          # Telegram API ID
API_HASH=...                        # Telegram API hash
BOT_TOKEN=...                       # Telegram bot token
ALLOWED_USER_IDS=123456789          # Comma-separated owner IDs
FIRECRAWL_API_KEY=...               # Firecrawl API key
OPENROUTER_API_KEY=...              # OpenRouter API key
OPENROUTER_MODEL=qwen/qwen3-max  # Default model (flagship, most powerful)
OPENROUTER_FALLBACK_MODELS=deepseek/deepseek-r1,moonshotai/kimi-k2-thinking,deepseek/deepseek-v3-0324,openai/gpt-4o  # Fallback models (paid tier)
OPENROUTER_LONG_CONTEXT_MODEL=moonshotai/kimi-k2-thinking  # Long context model (256k context + reasoning)

# Mobile API (Optional - only if using Mobile API)
JWT_SECRET_KEY=...                  # JWT secret for Mobile API auth (min 32 chars)
ALLOWED_CLIENT_IDS=...              # Comma-separated client app IDs (empty = allow all)

# Optional
DB_PATH=/data/app.db                # SQLite database path
LOG_LEVEL=INFO                      # Logging level (DEBUG, INFO, WARNING, ERROR)
REQUEST_TIMEOUT_SEC=60              # Request timeout
PREFERRED_LANG=auto                 # Language preference (auto|en|ru)
DEBUG_PAYLOADS=0                    # Log request/response payloads (0|1)
MAX_CONCURRENT_CALLS=4              # Max concurrent Firecrawl/OpenRouter calls
OPENROUTER_HTTP_REFERER=...         # Optional OpenRouter attribution
OPENROUTER_X_TITLE=...              # Optional OpenRouter attribution
DB_BACKUP_ENABLED=1                 # Enable DB backups (0|1)
DB_BACKUP_INTERVAL_MINUTES=360      # Backup interval
DB_BACKUP_RETENTION=14              # Backup retention days
DB_BACKUP_DIR=/data/backups         # Backup directory

# YouTube Video Download
YOUTUBE_DOWNLOAD_ENABLED=true       # Enable/disable YouTube video download feature
YOUTUBE_STORAGE_PATH=/data/videos   # Directory for downloaded videos
YOUTUBE_MAX_VIDEO_SIZE_MB=500       # Maximum size per video (MB)
YOUTUBE_MAX_STORAGE_GB=100          # Maximum total storage for all videos (GB)
YOUTUBE_PREFERRED_QUALITY=1080p     # Video quality (1080p, 720p, 480p, etc.)
YOUTUBE_SUBTITLE_LANGUAGES=en,ru    # Preferred subtitle/transcript languages
YOUTUBE_AUTO_CLEANUP_ENABLED=true   # Enable automatic cleanup of old videos
YOUTUBE_CLEANUP_AFTER_DAYS=30       # Delete videos older than N days
```

---

**Last Updated:** 2025-11-16

For questions about the codebase, always refer to:
1. This file (CLAUDE.md) for AI assistant guidance
2. SPEC.md for technical specification
3. README.md for user-facing documentation
4. Code comments and docstrings for implementation details
