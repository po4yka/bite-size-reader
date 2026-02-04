# Architecture Review: Bite-Size Reader

**Date:** 2026-02-04
**Scope:** Full codebase analysis covering god objects, coupling, design patterns, error handling, and concurrency.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [1. God Objects](#1-god-objects)
  - [1.1 app/config.py](#11-appconfigpy)
  - [1.2 app/db/database.py](#12-appdbdatabasepy)
  - [1.3 app/adapters/openrouter/openrouter_client.py](#13-appadaptersopenrouteropenrouter_clientpy)
  - [1.4 app/adapters/content/content_extractor.py](#14-appadapterscontentcontent_extractorpy)
  - [1.5 app/core/summary_contract.py](#15-appcoresummary_contractpy)
  - [1.6 app/adapters/content/url_processor.py](#16-appadapterscontenturl_processorpy)
  - [1.7 app/adapters/telegram/message_router.py](#17-appadapterstelegrammessage_routerpy)
  - [1.8 app/adapters/telegram/telegram_bot.py](#18-appadapterstelegrammtelegram_botpy)
- [2. Coupling and Dependency Issues](#2-coupling-and-dependency-issues)
  - [2.1 Global Config Access](#21-global-config-access)
  - [2.2 Adapter Cross-Dependencies](#22-adapter-cross-dependencies)
  - [2.3 God Imports](#23-god-imports)
  - [2.4 Layer Violations](#24-layer-violations)
  - [2.5 Direct Class Instantiation](#25-direct-class-instantiation)
  - [2.6 Circular Imports](#26-circular-imports)
- [3. Design Smells and Anti-Patterns](#3-design-smells-and-anti-patterns)
  - [3.1 Unused Protocol Definitions](#31-unused-protocol-definitions)
  - [3.2 Duplicate Error Handlers](#32-duplicate-error-handlers)
  - [3.3 Shotgun Surgery](#33-shotgun-surgery)
  - [3.4 Dead DDD Use-Case Layer](#34-dead-ddd-use-case-layer)
  - [3.5 Circular Coupling via Duck Typing](#35-circular-coupling-via-duck-typing)
  - [3.6 Inconsistent Rate Limiter Interface](#36-inconsistent-rate-limiter-interface)
  - [3.7 Duplicate LLM Workflow Instances](#37-duplicate-llm-workflow-instances)
  - [3.8 Over-Engineered Response Formatter](#38-over-engineered-response-formatter)
  - [3.9 Anemic Domain Model (Partial)](#39-anemic-domain-model-partial)
  - [3.10 Untyped Content Metadata](#310-untyped-content-metadata)
- [4. Error Handling Issues](#4-error-handling-issues)
  - [4.1 Silent Exception Swallowing](#41-silent-exception-swallowing)
  - [4.2 Overly Broad Exception Catches](#42-overly-broad-exception-catches)
  - [4.3 Missing Cancellation Handling](#43-missing-cancellation-handling)
  - [4.4 Fire-and-Forget Tasks Without Error Handling](#44-fire-and-forget-tasks-without-error-handling)
  - [4.5 Inconsistent Error Context](#45-inconsistent-error-context)
- [5. Concurrency and Resource Issues](#5-concurrency-and-resource-issues)
  - [5.1 Memory Leaks from Unbounded Dictionaries](#51-memory-leaks-from-unbounded-dictionaries)
  - [5.2 Race Condition in HTTP Client Pool](#52-race-condition-in-http-client-pool)
  - [5.3 Missing Timeouts](#53-missing-timeouts)
  - [5.4 Resource Cleanup Gaps](#54-resource-cleanup-gaps)
- [6. Positive Patterns (Good Design)](#6-positive-patterns-good-design)
- [7. Prioritized Recommendations](#7-prioritized-recommendations)
  - [P0 -- Fix Memory Leaks and Safety](#p0----fix-memory-leaks-and-safety)
  - [P1 -- Reduce God Objects](#p1----reduce-god-objects)
  - [P2 -- Fix Coupling](#p2----fix-coupling)
  - [P3 -- Clean Up Dead Code](#p3----clean-up-dead-code)

---

## Executive Summary

The bite-size-reader codebase is in a **mid-refactoring state**. Good abstractions exist in some areas (domain models, LLM base client, YouTube downloader), but several critical files exceed 1,000 lines and conflate 10+ responsibilities. The project has partially adopted clean architecture (DDD, repository adapters, protocols) but the migration is incomplete -- legacy facades remain, protocols go unused, and adapters depend on each other bidirectionally.

**Key metrics:**

| Category | Count | Severity |
|----------|-------|----------|
| God objects (>700 lines) | 8 files | CRITICAL-MEDIUM |
| Files importing `app.config` directly | 44 | HIGH |
| Files with 10+ distinct `app.*` imports | 14 | HIGH |
| Adapter-to-adapter cross-dependencies | 5 pairs | HIGH |
| Unused protocol definitions | 7+ | MEDIUM |
| Unbounded in-memory dictionaries | 3+ | HIGH |
| Silent exception swallowing sites | 4+ | MEDIUM |

---

## 1. God Objects

### 1.1 app/config.py

**Lines:** 2,205 | **Classes:** 26 | **Methods:** ~60+

Conflates configuration validation for 12+ domains (Telegram, Firecrawl, OpenRouter, OpenAI, Anthropic, YouTube, Redis, CircuitBreaker, Auth, Karakeep, Database, WebSearch, MCP, Chroma, Runtime) into a single file.

**Responsibilities:**
- Environment variable resolution (`_build_nested_from_env`, 40+ lines)
- API key security validation
- Model name validation and security checks
- Network configuration (TCP, HTTP/2, pooling, timeouts)
- Rate limiting configuration with cooldown math
- 26 Pydantic model classes with 30+ field validators

**Impact:** Changes to ANY configuration domain require modifying this file. Testing individual validators is difficult due to coupling.

**Suggested decomposition:**

```
app/config/
  __init__.py
  domains/
    telegram.py           # TelegramConfig, TelegramLimitsConfig
    content.py            # ContentLimitsConfig, WebSearchConfig
    llm.py                # OpenRouterConfig, OpenAIConfig, AnthropicConfig
    external_services.py  # FirecrawlConfig, KarakeepConfig, YouTubeConfig
    database.py           # DatabaseConfig
    api.py                # ApiLimitsConfig, AuthConfig
    infrastructure.py     # RedisConfig, ChromaConfig, RuntimeConfig, CircuitBreakerConfig
    sync.py               # SyncConfig
  validators.py           # Reusable validators
  loader.py               # Settings class (environment loading only)
  builder.py              # ConfigHelper, _build_nested_from_env
```

### 1.2 app/db/database.py

**Lines:** 1,552 | **Classes:** 1 | **Methods:** 76

A mega-facade that acts as the repository for 10+ entity types. The file itself contains a deprecation notice recommending repository adapters, but the migration is incomplete.

**Responsibilities:**
- Database connection pooling with async locks
- Transaction management with retry logic and timeouts
- JSON validation, parsing, normalization
- CRUD for User, Chat, UserInteraction, Request, Summary, LLMCall, CrawlResult, VideoDownload
- FTS5 topic search index management
- Database health checks, backups, integrity verification

**The repository adapters already exist** at `app/infrastructure/persistence/sqlite/repositories/` but are not fully wired in -- the legacy `Database` class still handles most operations.

**Suggested action:** Complete the repository adapter migration:
1. Move transaction logic to `TransactionManager`
2. Move JSON validation to `JsonValidator`
3. Delete all CRUD methods from `Database`
4. Wire repository adapters through DI container

### 1.3 app/adapters/openrouter/openrouter_client.py

**Lines:** 1,533 | **Classes:** 1 | **Methods:** 31

The `OpenRouterClient` handles ALL aspects of LLM integration in a single class.

**Responsibilities:**
- HTTP client pooling (shared pool with weak references)
- Chat completion request construction with structured outputs
- Retry logic (exponential backoff, transient error detection)
- Error handling (HTTP status mapping, rate limit detection)
- Response processing (JSON parsing, structured output extraction)
- Logging with Authorization header redaction
- Model capability detection
- Circuit breaker integration
- Prompt caching with TTL
- Request metrics collection

**Key metric:** The `chat()` method alone is 360 lines. The `__init__` method is 142 lines with 11+ parameters.

**Note:** Helper classes already exist (RequestBuilder, ResponseProcessor, ErrorHandler, ModelCapabilities, PayloadLogger) but are not fully utilized -- `chat()` still contains inline logic.

**Suggested action:** Complete the decomposition:
1. Move ALL retry logic to `retry_strategy.py`
2. Move caching logic to `structured_output.py`
3. Reduce `OpenRouterClient` to a thin facade (~50 lines)

### 1.4 app/adapters/content/content_extractor.py

**Lines:** 1,180 | **Classes:** 1 | **Methods:** 20

**Responsibilities:**
- Firecrawl API integration (HTTP calls, request building)
- Content deduplication (checking existing crawl results)
- Cache management (reading/writing Firecrawl cache)
- Low-value content detection (paywalls, empty content)
- Request database operations (upsert Request records)
- Content processing (HTML salvage, markdown extraction)
- YouTube detection and routing to YouTubeDownloader
- Crawl result and message snapshot persistence
- Sender metadata extraction (updating User/Chat records)

**Suggested decomposition:**

```
app/adapters/content/
  content_extractor.py         # Thin orchestrator (~200 lines)
  extractors/
    firecrawl_extractor.py     # Firecrawl API calls only
    youtube_router.py          # YouTube detection + delegation
  dedup/
    content_deduplicator.py    # Check existing crawls, manage cache
  quality/
    low_value_detector.py      # Detect paywalls, empty content
  persistence/
    crawl_persistence.py       # Write crawl results, requests, metadata
```

### 1.5 app/core/summary_contract.py

**Lines:** 1,095 | **Classes:** 2 | **Functions:** 30+

The main `validate_and_shape_summary()` function is 220 lines and performs 12 distinct steps.

**Responsibilities:**
- JSON schema definition (`get_summary_json_schema()`)
- Summary validation against spec
- Field normalization (legacy field renaming, entity coercion)
- String processing (capping, whitespace normalization)
- NLP operations: Flesch readability scoring, TF-IDF keyword extraction
- TLDR enrichment from supporting fields
- Tag processing and deduplication
- Insight and semantic chunk shaping
- Semantic booster construction for search optimization
- Query expansion keyword generation
- Fallback logic for missing fields

**Suggested decomposition:**

```
app/core/
  summary_contract.py          # Thin facade (~150 lines)
  summary_schema.py            # Schema definition
  summary_shaping/
    field_normalizer.py        # Legacy field renaming, entity normalization
    text_processor.py          # Capping, whitespace
    type_coercer.py            # Entity coercion, list cleanup
    enricher.py                # TLDR enrichment, insight shaping
  nlp/
    readability.py             # Flesch-Kincaid computation
    keyword_extractor.py       # TF-IDF extraction
    semantic_optimizer.py      # Semantic boosters, query expansion
```

### 1.6 app/adapters/content/url_processor.py

**Lines:** 795 | **Classes:** 1 | **Methods:** 18

The `URLProcessor` orchestrates the entire URL-to-summary pipeline. The `handle_url_flow()` method is 200 lines.

**Responsibilities:** Content extraction orchestration, content caching, LLM summarization, language detection and prompt selection, Russian translation (special case), response formatting, web search enrichment, custom article handling, summary persistence, post-processing task scheduling, system prompt loading.

**Constructor instantiates** `ContentExtractor`, `ContentChunker`, `LLMSummarizer` directly instead of receiving them as injected dependencies.

### 1.7 app/adapters/telegram/message_router.py

**Lines:** 698 | **Classes:** 1 | **Methods:** 10

The `route_message()` method is 270 lines. The `_route_message_content()` method is 200 lines.

**Responsibilities:** Message dispatch, command routing, URL detection, forward message handling, rate limiting (in-memory AND Redis), concurrency control, duplicate detection, user interaction logging, file validation, rate limiter cleanup.

**Key issue:** The router directly accesses internal state of `URLHandler` (`_awaiting_url_users`, `_pending_multi_links`), creating bidirectional coupling.

### 1.8 app/adapters/telegram/telegram_bot.py

**Lines:** 656 | **Classes:** 2 | **Methods:** 25

**Responsibilities:** Component wiring (110-line `__post_init__`), bot lifecycle management, database backup scheduling/creation/cleanup, rate limiter cleanup scheduling, message handling, URL/forward flow dispatch (legacy compatibility hooks), message persistence, audit logging.

---

## 2. Coupling and Dependency Issues

### 2.1 Global Config Access

**44 files** import directly from `app.config`, treating it as global state:
- `adapters`: 17 files
- `api`: 15 files
- `cli`: 4 files
- `infrastructure`: 2 files
- Other: 6 files

Configuration is accessed directly (e.g., `cfg.firecrawl`, `cfg.redis`) rather than receiving needed values as constructor parameters. This creates implicit dependencies and makes testing require monkeypatching or environment variables.

```python
# Example violation -- app/infrastructure/cache/redis_cache.py:21-30
def __init__(self, cfg: AppConfig) -> None:
    self.cfg = cfg  # Direct config access
    timeout = getattr(cfg.redis, "cache_timeout_sec", 0.3)  # Implicit dependency
```

### 2.2 Adapter Cross-Dependencies

Adapters should be independently pluggable but depend directly on each other:

```
telegram -> content, external, llm, karakeep
content  -> external, llm, telegram, youtube
youtube  -> external
llm      -> openrouter
```

The bidirectional `content <-> telegram` dependency is the most problematic:
- `adapters/content/url_processor.py` imports `MessagePersistence` from telegram
- `adapters/telegram/command_processor.py` imports `URLProcessor` from content

### 2.3 God Imports

14 files import from 10+ distinct `app.*` modules:

| File | Distinct Imports |
|------|-----------------|
| `adapters/content/llm_summarizer.py` | 20 |
| `adapters/telegram/command_processor.py` | 20 |
| `adapters/telegram/bot_factory.py` | 19 |
| `adapters/telegram/message_router.py` | 17 |
| `di/container.py` | 17 |

Root causes: heavy orchestration logic in adapters, repositories instantiated directly in adapters, configuration accessed directly.

### 2.4 Layer Violations

Expected dependency direction (clean architecture):

```
api, cli, adapters -> application -> domain <-> infrastructure
                          |
                        core
```

Actual violations:
- **infrastructure imports services**: `summary_repository.py` imports `topic_search_utils`
- **db imports services**: `database.py` imports `trending_cache`; `topic_search_index.py` imports `topic_search_utils`
- **services imports adapters**: should be the opposite direction

Overall package dependency map:

```
adapters      -> agents, api, application, config, core, db, di, infrastructure, models, prompts, security, services, utils
api           -> adapters, config, core, db, di, infrastructure, observability, services
di            -> adapters, api, application, config, core, db, domain, infrastructure
infrastructure -> config, core, db, domain, services (!)
services      -> adapters (!), config, core, db, infrastructure
db            -> cli, core, infrastructure, observability, services (!)
```

### 2.5 Direct Class Instantiation

Classes instantiate their dependencies instead of receiving them via injection:

```python
# adapters/content/llm_summarizer.py:72-74
self.summary_repo = SqliteSummaryRepositoryAdapter(db)
self.request_repo = SqliteRequestRepositoryAdapter(db)
self.crawl_result_repo = SqliteCrawlResultRepositoryAdapter(db)

# adapters/content/llm_summarizer.py:83
self._cache = RedisCache(cfg)

# adapters/content/url_processor.py:138-155
self.content_extractor = ContentExtractor(...)
self.content_chunker = ContentChunker(...)
self.llm_summarizer = LLMSummarizer(...)
```

Impact: testing `LLMSummarizer` requires a real Redis connection; cannot swap implementations.

### 2.6 Circular Imports

8 circular imports found, all properly guarded with `TYPE_CHECKING`:
- `telegram.bot_factory` <-> `telegram.telegram_bot`
- `db.session` <-> `cli.migrations.migration_runner`
- `db.database` <-> `db.database_diagnostics`
- `api.background_processor` <-> `di.background`

**Verdict:** Acceptable. No immediate refactor needed.

---

## 3. Design Smells and Anti-Patterns

### 3.1 Unused Protocol Definitions

`app/protocols.py` defines 7+ protocols that are never used:
- `RequestRepository` -- bypassed; code uses concrete `SqliteRequestRepositoryAdapter`
- `SummaryRepository` -- bypassed; code uses concrete `SqliteSummaryRepositoryAdapter`
- `CrawlResultRepository` -- bypassed
- `UserInteractionRepository` -- not used anywhere
- `LLMCallRepository` -- not used anywhere
- `MessageFormatter` -- not used anywhere
- `FileValidator` -- not used anywhere
- `RateLimiter` -- replaced with concrete `UserRateLimiter` / `RedisUserRateLimiter`

Only `ContentFetcher`, `SummaryGenerator`, and `LLMClient` are actually used (and `LLMClient` is overridden by `LLMClientProtocol` in `app/adapters/llm/protocol.py`).

Dead code creating false polymorphism expectations.

### 3.2 Duplicate Error Handlers

`app/adapters/openrouter/error_handler.py` (290 lines) and `app/adapters/external/firecrawl/error_handler.py` (299 lines) implement nearly identical patterns:

```python
# openrouter/error_handler.py:53-61
async def sleep_backoff(self, attempt: int) -> None:
    base_delay = max(0.0, self._backoff_base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)

# firecrawl/error_handler.py:53-61 -- IDENTICAL
async def sleep_backoff(self, attempt: int) -> None:
    base_delay = max(0.0, self._backoff_base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
```

Additionally, `asyncio_sleep_backoff()` standalone function at `firecrawl/error_handler.py:287-298` duplicates the same logic a third time.

Bug fixes or improvements to retry strategy require changes in 3 places.

### 3.3 Shotgun Surgery

Adding a new summary field (e.g., `sentiment_score`) requires changes in 10+ files:

1. `app/prompts/en/summary.txt` + `app/prompts/ru/summary.txt` -- LLM prompts
2. `app/domain/models/summary.py` -- domain model getter methods
3. `app/core/summary_contract.py` -- validation logic
4. `app/db/models.py` -- Peewee ORM model
5. `app/infrastructure/persistence/sqlite/repositories/summary_repository.py` -- persistence
6. `app/api/models/responses.py` -- API response models
7. `app/api/routers/summaries.py` -- response serialization
8. `app/adapters/external/formatting/summary_presenter.py` -- Telegram formatting
9. `app/adapters/content/llm_summarizer.py` AND `app/adapters/telegram/forward_summarizer.py` -- both summarizers
10. `app/cli/` tools that display summaries
11. `SPEC.md` -- documentation

Root cause: summary validation and structure is spread across multiple layers without a single source of truth. Required fields are duplicated in 3 places:

```python
# domain/models/summary.py
required_fields = ["tldr", "summary_250", "key_ideas"]

# core/summary_contract.py -- SAME validation duplicated
required_fields = ["tldr", "summary_250", "key_ideas"]

# domain/services/summary_validator.py -- AGAIN duplicated
required_fields = ["tldr", "summary_250", "key_ideas"]
```

### 3.4 Dead DDD Use-Case Layer

`app/application/use_cases/summarize_url.py` (515 lines) defines a use-case that wraps the same workflow already orchestrated in `url_processor.py`:

```python
# use_cases/summarize_url.py -- sequences:
# 1. _create_request()
# 2. _fetch_content()
# 3. _generate_summary()
# 4. _persist_summary()
# 5. Publish events

# But actual runtime (bot.py, API routes) bypasses this entirely:
# -> url_processor.process_url()
# -> forward_processor.process_forward()
```

The use case, DTOs, and events add indirection without reducing coupling or improving testability in actual usage.

### 3.5 Circular Coupling via Duck Typing

`TelegramBot` is cast to `URLProcessor` via duck typing so downstream components can call flow methods on it:

```python
# telegram_bot.py:106-114
self._url_processor_entrypoint = _URLProcessorEntrypoint(self)
self.message_handler.command_processor.url_processor = cast("URLProcessor", self)
self.message_handler.url_handler.url_processor = cast("URLProcessor", self)
self.message_handler.url_processor = cast("URLProcessor", self._url_processor_entrypoint)
```

This creates bidirectional dependency: bot depends on URLProcessor interface, URLProcessor implementations depend on bot methods, tests must override `_handle_url_flow()` on bot instance.

### 3.6 Inconsistent Rate Limiter Interface

`UserRateLimiter` and `RedisUserRateLimiter` have different return types for `check_and_record()`:

```python
# UserRateLimiter
async def check_and_record(...) -> tuple[bool, str | None]:

# RedisUserRateLimiter
async def check_and_record(...) -> tuple[bool, str | None, ...]:  # Extra element
```

This requires `isinstance` checks at call sites:

```python
# message_router.py:114-124
async def _check_rate_limit(...) -> tuple[bool, str | None]:
    if isinstance(limiter, RedisUserRateLimiter):
        allowed, error_msg, _ = await limiter.check_and_record(...)
        return allowed, error_msg
    return await limiter.check_and_record(...)
```

### 3.7 Duplicate LLM Workflow Instances

Both `app/adapters/content/llm_summarizer.py` and `app/adapters/telegram/forward_summarizer.py` instantiate identical `LLMResponseWorkflow` objects:

```python
# Both files -- identical instantiation
self._workflow = LLMResponseWorkflow(
    cfg=cfg,
    db=db,
    openrouter=openrouter,
    response_formatter=response_formatter,
    audit_func=audit_func,
    sem=sem,
)
```

Both then call `build_structured_response_format()`, handle `LLMRepairContext`, and call `_workflow.execute()`. Changes to the workflow must be maintained in sync across both.

### 3.8 Over-Engineered Response Formatter

`app/adapters/external/response_formatter.py` delegates to 7 component classes:
1. `DataFormatterImpl`
2. `MessageValidatorImpl`
3. `ResponseSenderImpl`
4. `TextProcessorImpl`
5. `NotificationFormatterImpl`
6. `SummaryPresenterImpl`
7. `DatabasePresenterImpl`

This creates 8 classes (facade + 7 implementations) with 300+ lines of delegation code for message formatting. High cognitive load for a concern that could be 2-3 focused components.

### 3.9 Anemic Domain Model (Partial)

Domain models have some good behavior:
- `Request.mark_as_crawling()`, `mark_as_summarizing()` -- state transitions
- `Summary.validate_content()` -- validation

But critical business logic lives in adapters:
- Content extraction logic in `ContentExtractor`
- Summarization orchestration in `LLMSummarizer`
- Summary contract validation in `app/core/summary_contract.py` (separate from `SummaryValidator`)

### 3.10 Untyped Content Metadata

Content fetching returns loosely-typed metadata:

```python
# url_processor.py:336-370
content_text, content_source, metadata = await self._content_fetcher.extract_content_pure(...)

content = {
    "text": content_text,
    "source": content_source,
    "metadata": metadata,  # Loosely typed dict -- no contract
    "detected_lang": detected_lang,
}
```

Different sources (Firecrawl, forward messages, YouTube) return different keys, but there is no typed contract (Pydantic model or Protocol) defining what `metadata` should contain.

---

## 4. Error Handling Issues

### 4.1 Silent Exception Swallowing

**`telegram_bot.py:540-546`** -- Double-nested exception handlers with final bare `pass`:

```python
except Exception:
    try:
        text = json.dumps(payload, ensure_ascii=False)
        if hasattr(message, "reply_text"):
            await message.reply_text(text)
    except Exception:
        pass  # No logging if both paths fail
```

No audit trail if both JSON document and text fallback fail.

### 4.2 Overly Broad Exception Catches

**`telegram_bot.py:485-487`** -- Bare exception catch in `_safe_reply`:

```python
except Exception:
    # Swallow in tests; production response path logs and continues.
    pass
```

Documented as test-only, but silently swallows all errors including `asyncio.CancelledError`.

**`background_processor.py:212, 528`** -- Multiple bare `Exception` catches marked "defensive":

```python
except Exception as exc:  # pragma: no cover - defensive
```

Cannot distinguish between retryable errors (network) and non-retryable (validation).

### 4.3 Missing Cancellation Handling

**`background_processor.py:474-502`** -- Retry loop catches all `Exception` including `CancelledError`:

```python
async def _run_with_backoff(...):
    for attempt in range(1, self._retry.attempts + 1):
        try:
            return await func()
        except Exception as exc:
            last_error = exc  # Catches CancelledError too!
            delay_ms = min(...)
            if attempt >= self._retry.attempts:
                break
            await asyncio.sleep(delay_ms / 1000)
```

Cancelled tasks retry unnecessarily instead of propagating cancellation. Missing `raise_if_cancelled()` check (the utility exists at `app/core/async_utils.py`).

### 4.4 Fire-and-Forget Tasks Without Error Handling

**`message_handler.py:158-178`** -- Audit tasks created without error callback:

```python
try:
    loop = asyncio.get_running_loop()
    task = loop.create_task(_do_audit())
    if not hasattr(self, "_audit_tasks"):
        self._audit_tasks: set[asyncio.Task] = set()
    self._audit_tasks.add(task)
    task.add_done_callback(self._audit_tasks.discard)
except RuntimeError:
    pass
```

If task fails, error is silently ignored. Only catches `RuntimeError` (no event loop), not task failures.

**`content_extractor.py:98-119`** -- Crawl persistence task logs errors but does not re-raise:

```python
task: asyncio.Task[None] = asyncio.create_task(
    self._persist_crawl_result(req_id, crawl, correlation_id)
)

def _log_task_error(t: asyncio.Task[None]) -> None:
    if t.cancelled():
        return
    exc = t.exception()
    if exc:
        logger.error(...)  # Logs only, does not re-raise

task.add_done_callback(_log_task_error)
```

Crawl results may not be persisted, and the failure is only visible in logs.

### 4.5 Inconsistent Error Context

Different adapters use different error context structures with no unified type:

| Adapter | Pattern |
|---------|---------|
| OpenRouter | `error_context: dict \| None` parameter |
| Firecrawl | `FirecrawlSearchResult` with `error_text` field |
| LLM calls | `LLMCallResult` with `error_context` field |
| Telegram | `error_details` dict |
| Use cases | Different `error_details` dict |

---

## 5. Concurrency and Resource Issues

### 5.1 Memory Leaks from Unbounded Dictionaries

**`app/api/background_processor.py:78`** -- `_local_locks` dictionary grows per `request_id`, never cleaned:

```python
self._local_locks: dict[int, asyncio.Lock] = {}
# setdefault creates locks but never deletes them
```

**`app/adapters/telegram/url_handler.py:54-56`** -- User workflow state accumulates if users abandon workflows:

```python
self._awaiting_url_users: set[int] = set()       # No TTL, no cleanup
self._pending_multi_links: dict[int, list[str]] = {}  # No TTL, no cleanup
```

**`app/adapters/telegram/message_router.py:89`** -- `_recent_message_ids` grows unbounded between cleanup cycles (5-minute intervals):

```python
self._recent_message_ids: dict[tuple[int, int, int], tuple[float, str]] = {}
self._recent_message_ttl = 120
```

### 5.2 Race Condition in HTTP Client Pool

**`openrouter_client.py:73-100`** -- `_get_event_loop()` catches `RuntimeError` broadly and falls back to `get_event_loop()`. If no running loop exists, the fallback may return a stale loop. Creating an `asyncio.Lock()` outside the running loop's context may cause issues later.

### 5.3 Missing Timeouts

**`telegram_bot.py:465-487`** -- `_safe_reply()` and `_reply_json()` call `message.reply_text()` without timeout wrappers. If Telegram API hangs, entire handler blocks.

**`message_router.py:269-283, 671-686`** -- Database operations (`async_insert_user_interaction()` etc.) without explicit timeout wrapper. If DB is stuck, entire message routing path blocks.

### 5.4 Resource Cleanup Gaps

**`firecrawl/client.py:165`** -- httpx.AsyncClient created in `__init__` but only closed in `aclose()`. If initialization fails after this line, client is never closed.

**`background_processor.py:612-631`** -- Task cleanup uses closure over `tasks` set. If processor is garbage collected before task completes, task might leak.

**YouTubeDownloader** -- Creates `storage_path` directory but downloaded files may not be cleaned up on exceptions (orphaned video files after partial writes).

---

## 6. Positive Patterns (Good Design)

Several files demonstrate solid design and should serve as models for refactoring:

- **`app/adapters/youtube/youtube_downloader.py`** (1,078 lines, 1 class) -- Single responsibility: YouTube downloads. Well-focused despite its size.
- **`app/adapters/external/formatting/summary_presenter.py`** (775 lines, 1 class) -- Single responsibility: Telegram formatting.
- **`app/adapters/llm/base_client.py`** -- Well-designed base class with shared HTTP pooling, retry logic, circuit breaker integration, and proper async resource cleanup.
- **`app/api/routers/auth/endpoints.py`** (806 lines, 19 functions) -- Appropriately thin route handlers.
- **`app/db/rw_lock.py`** -- Well-designed AsyncRWLock implementation with clear semantics.
- **`app/adapters/telegram/task_manager.py`** -- Proper user task tracking with cooperative cancellation.
- **`raise_if_cancelled` helper** (`app/core/async_utils.py`) -- Correctly re-raises `asyncio.CancelledError` across exception handlers.
- **Retry logic with exponential backoff and jitter** -- Both OpenRouter and Firecrawl clients implement this correctly (albeit duplicated).
- **HTTP client pooling** -- Shared pool with proper weak references in `openrouter_client.py`.
- **Domain model state transitions** -- `Request.mark_as_crawling()`, `mark_as_summarizing()` etc. are well-designed.

---

## 7. Prioritized Recommendations

### P0 -- Fix Memory Leaks and Safety

| # | Action | File | Impact |
|---|--------|------|--------|
| 1 | Add TTL-based cleanup to `_local_locks` | `app/api/background_processor.py:78` | Prevents unbounded memory growth |
| 2 | Add TTL/cleanup to `_awaiting_url_users` and `_pending_multi_links` | `app/adapters/telegram/url_handler.py:54-56` | Prevents memory leak on abandoned workflows |
| 3 | Add `raise_if_cancelled()` to `_run_with_backoff` retry loop | `app/api/background_processor.py:474-502` | Prevents cancelled tasks from retrying |
| 4 | Add timeout wrappers to `_safe_reply()` and `_reply_json()` | `app/adapters/telegram/telegram_bot.py:465-546` | Prevents bot from hanging on Telegram API |

### P1 -- Reduce God Objects

| # | Action | File | Impact |
|---|--------|------|--------|
| 5 | Complete `database.py` repository migration (repos already exist) | `app/db/database.py` | Removes 1,552-line god object |
| 6 | Split `config.py` into domain-specific modules | `app/config.py` | Reduces 2,205-line file to focused modules |
| 7 | Complete `openrouter_client.py` decomposition (helpers partially exist) | `app/adapters/openrouter/openrouter_client.py` | Reduces 1,533-line class |
| 8 | Extract NLP operations from `summary_contract.py` | `app/core/summary_contract.py` | Separates validation from NLP |

### P2 -- Fix Coupling

| # | Action | File(s) | Impact |
|---|--------|---------|--------|
| 9 | Consolidate duplicate backoff/retry into shared utility | `openrouter/error_handler.py`, `firecrawl/error_handler.py` | Eliminates DRY violation |
| 10 | Unify rate limiter interface (same return type) | `app/security/rate_limiter.py` | Removes `isinstance` checks |
| 11 | Remove bidirectional `content` <-> `telegram` dependency | `url_processor.py`, `command_processor.py` | Cleans adapter boundaries |
| 12 | Inject config values via constructors instead of importing `app.config` | 44 files | Enables testing, makes dependencies explicit |
| 13 | Inject repositories instead of instantiating in adapters | `llm_summarizer.py`, `llm_response_workflow.py` | Enables testing, enables swapping implementations |
| 14 | Consolidate duplicate validation of required summary fields | 3 locations | Single source of truth |

### P3 -- Clean Up Dead Code

| # | Action | File(s) | Impact |
|---|--------|---------|--------|
| 15 | Delete unused protocols or wire them properly | `app/protocols.py` | Removes dead code and false expectations |
| 16 | Either use the DDD use-case layer or remove it | `app/application/use_cases/` | Eliminates dead code path |
| 17 | Consolidate `LLMResponseWorkflow` instantiation | `llm_summarizer.py`, `forward_summarizer.py` | One workflow, two consumers |
| 18 | Define `ContentMetadata` Pydantic model | Multiple adapters | Type safety for metadata dicts |
| 19 | Remove TelegramBot-as-URLProcessor duck typing | `telegram_bot.py` | Eliminates circular coupling |
