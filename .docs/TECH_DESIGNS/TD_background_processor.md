# Background Processor Hardening
- Date: 2025-12-06
- Author: AI Partner

## Context
- Mobile API background processor uses module-level singletons (`load_config`, `Database`, clients, semaphore) and per-process locks, making multi-worker and hot-reload scenarios unsafe.
- No DI boundary exists; background tasks cannot reuse shared app instances built elsewhere.
- Idempotency relies on in-memory locks, so duplicate request processing can happen across workers or restarts.
- Error handling only sets request.status to "error" and logs a string; correlation_id and error taxonomy are not standardized.
- Retry logic is fixed-attempt linear delay without jitter and cannot be tuned from config.

## Goals and Non-Goals
- Goals:
  - Introduce DI-friendly builder for background processor dependencies using `AppConfig`.
  - Add Redis-backed per-request idempotent lock with TTL and logging, with in-process fallback.
  - Standardize structured error capture (type/code/message, correlation_id) and status updates.
  - Provide configurable exponential backoff with jitter for extraction and LLM steps.
- Non-Goals:
  - Changing summary contract or URL processing semantics beyond retries/error surfacing.
  - Replacing Database/ORM or OpenRouter/Firecrawl client implementations.

## Architecture / Flow
- A background module builder (e.g., `app/di/background.py`) constructs a `BackgroundProcessor` container:
  - Inputs: `AppConfig`, shared clients (`Database`, `FirecrawlClient`, `OpenRouterClient`, `ResponseFormatter`), optional Redis client, logger/audit func, semaphore factory.
  - Exposes `process_request(request_id, correlation_id?)`.
- Processing flow per request:
  1) Acquire idempotent lock `bg:req:{id}` in Redis with TTL (e.g., 5 min) using `SET NX PX`. On lock contention, skip and log `lock_held`.
  2) Load request; if missing or already summarized, release lock and return.
  3) Set correlation_id (from request or fallback) and mark status `processing`.
  4) Run extraction/summarization with `run_with_backoff` helper (exp backoff + jitter, attempts/caps from config) for each stage.
  5) On success: persist summary via DB upsert, set status `success`.
  6) On failure: record structured error (type/code/message, stage, correlation_id) and set status `error`.
  7) Release lock (Redis key expiry or explicit DEL on success/fail). Fallback in-process lock protects single-instance safety if Redis unavailable.
- Logging: use structured extras `{correlation_id, request_id, stage, attempt, delay_ms, error}`.

## Data Model / Contracts
- Lock key: `bg:req:{request_id}`; TTL configurable (`background.lock_ttl_ms`), value holds worker id + timestamp.
- Error record shape (not persisted as separate table): `{error_type, error_code, message, stage, correlation_id}` stored on request status update/log extras.
- Retry config: `background.retry.attempts`, `background.retry.base_delay_ms`, `background.retry.max_delay_ms`, `background.retry.jitter_ratio`.
- Semaphore: cap concurrent background tasks via `cfg.runtime.max_concurrent_calls`; builder injects semaphore factory instead of module globals.

## Decisions
- Use Redis for cross-worker idempotency; fallback to in-process lock with warning when Redis unavailable to keep single-node safety.
- Prefer DI builder to eliminate module-level singletons and allow reuse in FastAPI startup wiring.
- Exponential backoff with jitter to reduce thundering herd and align with external API best practices.
- Structured errors logged and used to update request status; do not propagate raw exceptions to callers.
- Skip-if-locked behavior instead of queueing to avoid duplicate work; relies on client-side retry or manual trigger if necessary.

## Risks and Mitigations
- Redis outage leaves only local lock: mitigate by warning logs/metrics and shortening TTL fallback; consider optional hard-fail flag.
- Lock orphaning if process dies: TTL ensures auto-release; success/fail path attempts explicit DEL.
- Longer retries could hold lock: cap max delay and total attempts; consider shorter TTL than worst-case runtime plus renewal if needed.
- Behavior drift between builder and existing consumers: add tests for wiring and backoff semantics.

## Testing Strategy
- Unit: lock acquisition/skip, fallback path without Redis, backoff delay calculation with jitter and caps, structured error mapping, DI builder wiring.
- Integration (with fakeredis): single and concurrent requests ensuring idempotency; verify status transitions and summary upsert happens once.
- Contract: logs include correlation_id and stage; lock key uses expected format and TTL.

## Rollout
- No DB schema change; config additions under `background.*`. Defaults allow operation without Redis but log degraded mode.
- Guard via feature flag `BACKGROUND_REDIS_LOCK_ENABLED` (config boolean). If disabled, use in-process lock only.
- Monitoring: count lock skips, retry attempts, failures by stage, Redis errors; alert on sustained Redis failures.
- Fallback: if new DI wiring fails, allow temporary use of in-process lock path while keeping new retry/error handling.
