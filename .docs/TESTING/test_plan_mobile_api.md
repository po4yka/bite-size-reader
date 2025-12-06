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
- TC2 Rate Limit: per-user bucket caps per endpoint; exceed returns 429 with headers; unauthenticated uses IP key.
- TC3 Requests: submit URL → duplicate detection; submit forward; retry failed request validation; background status transitions.
- TC4 Summaries: list filters (is_read/lang/date/sort); get summary includes source/processing; patch read flag; delete sets is_deleted.
- TC5 Search: FTS and semantic require auth; pagination; relevance fields; topic-related path handles tags normalization.
- TC6 Sync Full: initiate session, download chunks with user scoping, expiry handling, chunk size config.
- TC7 Sync Delta: created/updated/deleted sets; has_more logic; since timestamp parsing; conflict handling when uploading changes.
- TC8 Preferences/Stats: merge semantics, validation of notification/app settings shapes, stats computed only for user’s data.
- TC9 Error Handling: APIException paths return standardized error codes and correlation_id; global handler hides internals in non-debug.

## Non-Functional
- Concurrency: background processing semaphore behavior and idempotency.
- Resiliency: retry paths for external calls mocked; rate limiter under burst.

## Exit Criteria
- All unit and integration tests above pass in CI; regression tests added for any new failure found during implementation.
