# Test Plan – Mobile API
- Date: 2025-12-06
- Author: AI Partner

## Scope
- Authentication and JWT lifecycle, rate limiting, request submission/status, summaries CRUD, search (FTS/semantic), sync flows, user preferences/stats, background processing integration.

## Test Types
- Unit: auth hash verification, JWT encode/decode, rate limit decisions, sync session validation, service-layer filtering, error handlers.
- Integration: login → access protected endpoints, submit request → poll status → fetch summary, sync full/delta, search with auth, preferences update.
- E2E (optional): end-to-end summarization with background processing and storage.

## Environments / Data
- Env vars: BOT_TOKEN, JWT_SECRET_KEY, ALLOWED_USER_IDS, ALLOWED_CLIENT_IDS (optional), OpenRouter/Firecrawl keys (mock for tests), DB_PATH (test DB), optional Redis URL for rate limiting/sync store.
- Fixtures: test user id + client_id, sample URLs, sample forward content, seeded summaries/requests for search/sync.

## Test Cases
- TC1 Auth: Telegram login hash valid/invalid/expired/future timestamp; whitelist and client_id allowlist enforcement; tokens carry is_owner/client_id claims.
- TC2 Rate Limit: per-user bucket caps per endpoint (Redis-backed); exceed returns 429 with headers and correct Retry-After; unauthenticated uses IP key; Redis unavailable path (required=false) falls back to noop with warning; required=true returns 503.
- TC3 Requests: submit URL → duplicate detection; submit forward; retry failed request validation; background status transitions.
- TC4 Summaries: list filters (is_read/lang/date/sort); get summary includes source/processing; patch read flag; delete sets is_deleted.
- TC5 Search: FTS and semantic require auth; pagination; relevance fields; topic-related path handles tags normalization.
- TC6 Sync Full: initiate session, download chunks with user scoping, expiry handling via Redis TTL, chunk size config; session payload uses standard envelope; expired session returns 410.
- TC7 Sync Delta: created/updated/deleted sets; has_more logic; since timestamp parsing; conflict handling when uploading changes.
- TC8 Preferences/Stats: merge semantics, validation of notification/app settings shapes, stats computed only for user’s data.
- TC9 Responses: all routers return `success` wrapper with meta; schemas validate (auth tokens, request submit/status, summaries, search, sync, preferences/stats).
- TC10 Processor: per-request locking prevents double processing; retry/backoff triggers on transient failures (mocked exceptions) and surfaces status `error` on exhaustion.
- TC11 Error Handling: APIException paths return standardized error codes and correlation_id; global handler hides internals in non-debug.
- TC12 Search Performance: Chroma dependency is singleton per process, shutdown closes embedding/vector clients; trending topics caches per user/params with TTL, bounds DB scan size, and invalidates cache on summary writes.

## Non-Functional
- Concurrency: background processing semaphore behavior and idempotency.
- Resiliency: retry paths for external calls mocked; rate limiter under burst.

## Exit Criteria
- All unit and integration tests above pass in CI; regression tests added for any new failure found during implementation.
