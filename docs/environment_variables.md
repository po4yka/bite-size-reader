# Environment Variables Reference

Complete reference for all Bite-Size Reader configuration. Source of truth: `app/config.py`.

## Required

| Variable | Description |
|----------|-------------|
| `API_ID` | Telegram API ID (from https://my.telegram.org/apps) |
| `API_HASH` | Telegram API hash |
| `BOT_TOKEN` | Telegram bot token (from BotFather) |
| `ALLOWED_USER_IDS` | Comma-separated Telegram user IDs allowed to interact |
| `FIRECRAWL_API_KEY` | Firecrawl API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |

## LLM Provider Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openrouter` | Active LLM backend: `openrouter`, `openai`, or `anthropic` |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key (when using `openai` provider) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `OPENAI_FALLBACK_MODELS` | `gpt-4o-mini` | Comma-separated fallback models |
| `OPENAI_ORGANIZATION` | _(none)_ | OpenAI organization ID |
| `OPENAI_ENABLE_STRUCTURED_OUTPUTS` | `true` | Enable structured output mode |
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key (when using `anthropic` provider) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5-20250929` | Anthropic model name |
| `ANTHROPIC_FALLBACK_MODELS` | `claude-3-5-haiku-20241022` | Comma-separated fallback models |
| `ANTHROPIC_ENABLE_STRUCTURED_OUTPUTS` | `true` | Enable structured output mode |

## OpenRouter

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_MODEL` | `deepseek/deepseek-v3.2` | Primary model |
| `OPENROUTER_FALLBACK_MODELS` | `moonshotai/kimi-k2.5,qwen/qwen3-max,deepseek/deepseek-r1` | Comma-separated fallback chain |
| `OPENROUTER_LONG_CONTEXT_MODEL` | `moonshotai/kimi-k2.5` | Model for long-context content (256k+) |
| `OPENROUTER_TEMPERATURE` | `0.2` | Sampling temperature (0-2) |
| `OPENROUTER_TOP_P` | _(none)_ | Top-p sampling |
| `OPENROUTER_MAX_TOKENS` | _(none)_ | Max completion tokens |
| `OPENROUTER_HTTP_REFERER` | _(none)_ | Attribution referer |
| `OPENROUTER_X_TITLE` | _(none)_ | Attribution title |
| `OPENROUTER_PROVIDER_ORDER` | _(none)_ | Comma-separated provider priority |
| `OPENROUTER_ENABLE_STATS` | `false` | Include usage stats in response |
| `OPENROUTER_ENABLE_STRUCTURED_OUTPUTS` | `true` | Enable structured JSON output |
| `OPENROUTER_STRUCTURED_OUTPUT_MODE` | `json_schema` | Mode: `json_schema` or `json_object` |
| `OPENROUTER_REQUIRE_PARAMETERS` | `true` | Require all schema parameters |
| `OPENROUTER_AUTO_FALLBACK_STRUCTURED` | `true` | Auto-fallback from json_schema to json_object |
| `OPENROUTER_MAX_RESPONSE_SIZE_MB` | `10` | Max response payload size (MB) |
| `OPENROUTER_SUMMARY_TEMPERATURE_RELAXED` | _(none)_ | Temperature override for relaxed retry |
| `OPENROUTER_SUMMARY_TOP_P_RELAXED` | _(none)_ | Top-p override for relaxed retry |
| `OPENROUTER_SUMMARY_TEMPERATURE_JSON` | _(none)_ | Temperature override for JSON fallback |
| `OPENROUTER_SUMMARY_TOP_P_JSON` | _(none)_ | Top-p override for JSON fallback |
| `OPENROUTER_ENABLE_PROMPT_CACHING` | `true` | Enable prompt caching for supported providers |
| `OPENROUTER_PROMPT_CACHE_TTL` | `ephemeral` | Cache TTL: `ephemeral` (5min) or `1h` |
| `OPENROUTER_CACHE_SYSTEM_PROMPT` | `true` | Cache system message for reuse |
| `OPENROUTER_CACHE_LARGE_CONTENT_THRESHOLD` | `4096` | Min tokens to auto-cache (Gemini requires 4096) |

## Firecrawl

| Variable | Default | Description |
|----------|---------|-------------|
| `FIRECRAWL_TIMEOUT_SEC` | `90` | Request timeout (10-300s) |
| `FIRECRAWL_WAIT_FOR_MS` | `3000` | JS content load wait (0-30000ms) |
| `FIRECRAWL_MAX_CONNECTIONS` | `10` | Max HTTP connections |
| `FIRECRAWL_MAX_KEEPALIVE_CONNECTIONS` | `5` | Max keepalive connections |
| `FIRECRAWL_KEEPALIVE_EXPIRY` | `30.0` | Keepalive expiry (seconds) |
| `FIRECRAWL_RETRY_MAX_ATTEMPTS` | `3` | Max retry attempts (0-10) |
| `FIRECRAWL_RETRY_INITIAL_DELAY` | `1.0` | Initial retry delay (seconds) |
| `FIRECRAWL_RETRY_MAX_DELAY` | `10.0` | Max retry delay (seconds) |
| `FIRECRAWL_RETRY_BACKOFF_FACTOR` | `2.0` | Backoff multiplier |
| `FIRECRAWL_CREDIT_WARNING_THRESHOLD` | `1000` | Credit warning level |
| `FIRECRAWL_CREDIT_CRITICAL_THRESHOLD` | `100` | Credit critical level |
| `FIRECRAWL_MAX_RESPONSE_SIZE_MB` | `50` | Max response size (MB) |
| `FIRECRAWL_MAX_AGE_SECONDS` | `172800` | Max content age (seconds, default 2 days) |
| `FIRECRAWL_REMOVE_BASE64_IMAGES` | `true` | Strip base64 images |
| `FIRECRAWL_BLOCK_ADS` | `true` | Block ads during scrape |
| `FIRECRAWL_SKIP_TLS_VERIFICATION` | `true` | Skip TLS verification |
| `FIRECRAWL_INCLUDE_MARKDOWN` | `true` | Include markdown format |
| `FIRECRAWL_INCLUDE_HTML` | `true` | Include HTML format |
| `FIRECRAWL_INCLUDE_LINKS` | `false` | Include extracted links |
| `FIRECRAWL_INCLUDE_SUMMARY` | `false` | Include auto-summary |
| `FIRECRAWL_INCLUDE_IMAGES` | `false` | Include image URLs |
| `FIRECRAWL_ENABLE_SCREENSHOT` | `false` | Enable page screenshot |
| `FIRECRAWL_SCREENSHOT_FULL_PAGE` | `true` | Full-page screenshot |
| `FIRECRAWL_SCREENSHOT_QUALITY` | `80` | Screenshot JPEG quality (1-100) |
| `FIRECRAWL_JSON_PROMPT` | _(none)_ | Custom JSON extraction prompt |

## YouTube Video Download

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_DOWNLOAD_ENABLED` | `true` | Enable YouTube video downloading |
| `YOUTUBE_STORAGE_PATH` | `/data/videos` | Video storage directory |
| `YOUTUBE_MAX_VIDEO_SIZE_MB` | `500` | Max per-video size (MB) |
| `YOUTUBE_MAX_STORAGE_GB` | `100` | Max total video storage (GB) |
| `YOUTUBE_PREFERRED_QUALITY` | `1080p` | Video quality: 1080p, 720p, 480p, 360p, 240p |
| `YOUTUBE_SUBTITLE_LANGUAGES` | `en,ru` | Preferred subtitle languages |
| `YOUTUBE_AUTO_CLEANUP_ENABLED` | `true` | Auto-delete old videos |
| `YOUTUBE_CLEANUP_AFTER_DAYS` | `30` | Retention period (days) |

## Web Search Enrichment

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_SEARCH_ENABLED` | `false` | Enable LLM-driven web search (opt-in) |
| `WEB_SEARCH_MAX_QUERIES` | `3` | Max search queries per article (1-10) |
| `WEB_SEARCH_MIN_CONTENT_LENGTH` | `500` | Min content chars to trigger search |
| `WEB_SEARCH_TIMEOUT_SEC` | `10.0` | Search operation timeout (1-60s) |
| `WEB_SEARCH_MAX_CONTEXT_CHARS` | `2000` | Max injected context chars (500-10000) |
| `WEB_SEARCH_CACHE_TTL_SEC` | `3600` | Search result cache TTL (60-86400s) |

## Redis Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_ENABLED` | `true` | Enable Redis integration |
| `REDIS_CACHE_ENABLED` | `true` | Enable caching via Redis |
| `REDIS_REQUIRED` | `false` | Fail requests when Redis unavailable |
| `REDIS_URL` | _(none)_ | Full Redis URL (overrides host/port/db) |
| `REDIS_HOST` | `127.0.0.1` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | _(none)_ | Redis password |
| `REDIS_PREFIX` | `bsr` | Key prefix for namespacing |
| `REDIS_SOCKET_TIMEOUT` | `5.0` | Socket timeout (seconds) |
| `REDIS_CACHE_TIMEOUT_SEC` | `0.3` | Cache operation timeout (seconds) |
| `REDIS_FIRECRAWL_TTL_SECONDS` | `21600` | Firecrawl response cache TTL (6h) |
| `REDIS_LLM_TTL_SECONDS` | `7200` | LLM response cache TTL (2h) |

## Vector Search / ChromaDB

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_HOST` | `http://localhost:8000` | Chroma HTTP endpoint |
| `CHROMA_AUTH_TOKEN` | _(none)_ | Bearer token for secured Chroma |
| `CHROMA_ENV` | `dev` | Environment label for collection namespacing |
| `CHROMA_USER_SCOPE` | `public` | Tenant scope for collections |
| `CHROMA_COLLECTION_VERSION` | `v1` | Collection version suffix |
| `CHROMA_REQUIRED` | `false` | Fail startup if ChromaDB unavailable |
| `CHROMA_CONNECTION_TIMEOUT` | `10.0` | Connection timeout (seconds) |

## MCP Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ENABLED` | `false` | Enable MCP server for AI agent access |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |
| `MCP_HOST` | `0.0.0.0` | SSE bind address |
| `MCP_PORT` | `8200` | SSE port |

## Mobile API and Auth

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | _(required if API used)_ | JWT signing secret (min 32 chars) |
| `ALLOWED_CLIENT_IDS` | _(empty = allow all)_ | Comma-separated allowed client app IDs |
| `API_RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `API_RATE_LIMIT_COOLDOWN_MULTIPLIER` | `2.0` | Cooldown multiplier on limit exceeded |
| `API_RATE_LIMIT_MAX_CONCURRENT_PER_USER` | `3` | Max concurrent requests per user |
| `API_RATE_LIMIT_DEFAULT` | `100` | Default rate limit |
| `API_RATE_LIMIT_SUMMARIES` | `200` | Summaries endpoint limit |
| `API_RATE_LIMIT_REQUESTS` | `10` | Requests endpoint limit |
| `API_RATE_LIMIT_SEARCH` | `50` | Search endpoint limit |
| `SYNC_EXPIRY_HOURS` | `1` | Sync session expiry |
| `SYNC_DEFAULT_LIMIT` | `200` | Default sync page size |
| `SYNC_MIN_LIMIT` | `1` | Min sync page size |
| `SYNC_MAX_LIMIT` | `500` | Max sync page size |
| `SYNC_TARGET_PAYLOAD_KB` | `512` | Target sync payload size (KB) |
| `SECRET_LOGIN_ENABLED` | `false` | Enable secret-key login flow |
| `SECRET_LOGIN_MIN_LENGTH` | `32` | Min secret length |
| `SECRET_LOGIN_MAX_LENGTH` | `128` | Max secret length |
| `SECRET_LOGIN_MAX_FAILED_ATTEMPTS` | `5` | Max failed login attempts before lockout |
| `SECRET_LOGIN_LOCKOUT_MINUTES` | `15` | Lockout duration |
| `SECRET_LOGIN_PEPPER` | _(none)_ | Optional pepper for secret hashing |

## Karakeep Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `KARAKEEP_ENABLED` | `false` | Enable Karakeep bookmark sync |
| `KARAKEEP_API_URL` | `http://localhost:3000/api/v1` | Karakeep API endpoint |
| `KARAKEEP_API_KEY` | _(empty)_ | Karakeep API key |
| `KARAKEEP_SYNC_TAG` | `bsr-synced` | Tag applied to synced bookmarks |
| `KARAKEEP_SYNC_INTERVAL_HOURS` | `6` | Auto-sync interval (1-168h) |
| `KARAKEEP_AUTO_SYNC_ENABLED` | `true` | Enable automatic periodic sync |

## Database and Backups

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `/data/app.db` | SQLite database path |
| `DB_BACKUP_ENABLED` | `1` | Enable automatic backups (0/1) |
| `DB_BACKUP_INTERVAL_MINUTES` | `360` | Backup interval |
| `DB_BACKUP_RETENTION` | `14` | Backup retention (days) |
| `DB_BACKUP_DIR` | `/data/backups` | Backup directory |
| `DB_OPERATION_TIMEOUT` | `30.0` | Database operation timeout (seconds) |
| `DB_MAX_RETRIES` | `3` | Retries for transient DB errors |
| `DB_JSON_MAX_SIZE` | `10000000` | Max JSON payload size (bytes, 10MB) |
| `DB_JSON_MAX_DEPTH` | `20` | Max JSON nesting depth |
| `DB_JSON_MAX_ARRAY_LENGTH` | `10000` | Max JSON array length |
| `DB_JSON_MAX_DICT_KEYS` | `1000` | Max JSON dictionary keys |

## Telegram Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_MAX_MESSAGE_CHARS` | `3500` | Max chars per reply (safety margin below 4096) |
| `TELEGRAM_MAX_URL_LENGTH` | `2048` | Max URL length (RFC 2616) |
| `TELEGRAM_MAX_BATCH_URLS` | `200` | Max URLs in a batch operation |
| `TELEGRAM_MIN_MESSAGE_INTERVAL_MS` | `100` | Min interval between messages (rate limiting) |

## Content Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_TEXT_LENGTH_KB` | `50` | Max text length for URL extraction (KB, regex DoS prevention) |

## Circuit Breaker

| Variable | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable circuit breaker for external services |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before opening circuit |
| `CIRCUIT_BREAKER_TIMEOUT_SECONDS` | `60.0` | Wait before half-open state |
| `CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | `2` | Successes needed to close from half-open |

## Background Processor

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKGROUND_REDIS_LOCK_ENABLED` | `true` | Use Redis distributed locks |
| `BACKGROUND_REDIS_LOCK_REQUIRED` | `false` | Fail if Redis unavailable for locking |
| `BACKGROUND_LOCK_TTL_MS` | `300000` | Lock TTL (ms, default 5min) |
| `BACKGROUND_LOCK_SKIP_ON_HELD` | `true` | Skip task if lock already held |
| `BACKGROUND_RETRY_ATTEMPTS` | `3` | Retry attempts for failed tasks |
| `BACKGROUND_RETRY_BASE_DELAY_MS` | `500` | Base retry delay (ms) |
| `BACKGROUND_RETRY_MAX_DELAY_MS` | `5000` | Max retry delay (ms) |
| `BACKGROUND_RETRY_JITTER_RATIO` | `0.2` | Jitter ratio (0-1) |

## Runtime and Debug

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `REQUEST_TIMEOUT_SEC` | `60` | General request timeout |
| `PREFERRED_LANG` | `auto` | Language preference: `auto`, `en`, `ru` |
| `DEBUG_PAYLOADS` | `0` | Log API payloads (0/1, Authorization redacted) |
| `MAX_CONCURRENT_CALLS` | `4` | Max concurrent Firecrawl/OpenRouter calls |
