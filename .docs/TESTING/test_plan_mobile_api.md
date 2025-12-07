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
- TC1b Secret-key Auth: feature flag gating, secret length bounds, allowlist enforcement, lockout after N failures, expired/revoked/locked status handling, successful JWT issuance, last_used_at bump, and hashed storage (no plaintext persisted).
- TC1c Secret-key Management: owner-only create/rotate/revoke/list; rotation returns plaintext once and updates hash/salt; revocation blocks login; list filtered by user_id/client_id/status.
- TC2 Rate Limit: per-user bucket caps per endpoint (Redis-backed); exceed returns 429 with headers and correct Retry-After; unauthenticated uses IP key; Redis unavailable path (required=false) falls back to noop with warning; required=true returns 503.
- TC3 Requests: submit URL → duplicate detection; submit forward; retry failed request validation; background status transitions.
- TC4 Summaries: list filters (is_read/lang/date/sort); get summary includes source/processing; patch read flag; delete sets is_deleted.
- TC5 Search: FTS and semantic require auth; pagination; relevance fields; topic-related path handles tags normalization.
- TC6 Sync Full (v2): start session via `/v1/sync/sessions`, enforce user/client binding, retrieve full dataset in chunks ordered by server_version with `has_more`/`next_since`; chunk limit obeys min/max and server downsizing; envelope includes meta.pagination; expired/missing session returns 410.
- TC7 Sync Delta (v2): provide `since` cursor, receive created/updated/tombstone deleted sets ordered by server_version; tombstones include deleted_at/version; `next_since` advances to max version; idempotent repeat with same cursor returns empty/has_more=false.
- TC8 Sync Apply (v2 uploads): upload allowed fields only (e.g., summary.is_read, client_note); valid last_seen_version applies and bumps server_version/etag; stale last_seen_version returns conflict with server snapshot; invalid fields or cross-user IDs rejected with validation error envelope.
- TC9 Chunk/ETag semantics: large payloads trigger server downsizing to stay under target size; optional If-None-Match/etag returns 304-equivalent behavior where supported; has_more remains accurate after downsizing.
- TC10 Preferences/Stats: merge semantics, validation of notification/app settings shapes, stats computed only for user’s data.
- TC11 Responses: all routers return `success` wrapper with meta; schemas validate (auth tokens, request submit/status, summaries, search, sync, preferences/stats).
- TC12 Processor: per-request locking prevents double processing; retry/backoff triggers on transient failures (mocked exceptions) and surfaces status `error` on exhaustion.
- TC13 Error Handling: APIException paths return standardized error codes and correlation_id; global handler hides internals in non-debug.
- TC14 Search Performance: Chroma dependency is singleton per process, shutdown closes embedding/vector clients; trending topics caches per user/params with TTL, bounds DB scan size, and invalidates cache on summary writes.

## Non-Functional
- Concurrency: background processing semaphore behavior and idempotency.
- Resiliency: retry paths for external calls mocked; rate limiter under burst.

## Exit Criteria
- All unit and integration tests above pass in CI; regression tests added for any new failure found during implementation.
