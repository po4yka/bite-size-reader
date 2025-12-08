# Tech Design: Mobile API OpenAPI Typed Contracts (v1)
- Date: 2025-12-07
- Owner: AI Partner
- Status: Draft
- Related: `.docs/TECH_DESIGNS/TD_response_contracts.md`, `.docs/TECH_DESIGNS/TD_sync_protocol.md`, `docs/openapi/mobile_api.yaml`, `docs/MOBILE_API_SPEC.md`, `.docs/PROPOSALS/PRP-OPENAPI-typed-contracts.md`

## Context
- Current `/v1` OpenAPI responses are mostly `{}` or `additionalProperties: true`, yielding `Any/Map<String, Any>` models for mobile clients.
- Error responses beyond 422 are undocumented; sync endpoints lack typed payloads and conflict semantics.
- Prior designs define envelope/meta (`TD_response_contracts`) and sync versioning/conflicts (`TD_sync_protocol`); the spec must reflect them.

## Goals
- Provide explicit typed schemas for all `/v1` success responses (auth, user, summaries, search, requests, duplicate check, sync).
- Standardize error responses (401/403/404/409/422/429/500) using a shared `ErrorResponse` with codes and correlation_id.
- Document pagination (limit/offset/has_more/total) and query array encoding; add servers section.
- Capture sync contracts (session/full/delta/apply, conflict semantics) with typed payloads and cursors.

## Non-Goals
- Introduce new endpoints or change business logic.
- DB migrations beyond fields already assumed (`server_version`, `deleted_at`) in sync design.

## Design
### Envelope
- `Meta`: `{ correlation_id, timestamp (RFC3339), version, build?, pagination? { total, limit, offset, has_more, next_cursor? } }`.
- `BaseSuccess`: `{ success: true, meta }` (no `data` yet).
- `BaseError`: `{ success: false, error: { code, message, details?, correlation_id?, retry_after? }, meta }`.
- Per-endpoint envelopes: `allOf [BaseSuccess, { required: [data], properties: { data: <TypedSchema> } }]`.

### Shared Schemas
- `AuthTokens`: `{ access_token, refresh_token, token_type='Bearer', expires_in (sec), refresh_expires_in? }`.
- `User`: `{ id:int, username?:string, display_name?:string, photo_url?:string, is_owner:bool, client_id?:string, created_at:date-time }`.
- `UserPreferences`: `{ lang_preference: enum auto|en|ru, notification_settings: object, app_settings: object }`.
- `UserStats`: `{ total_summaries:int, unread_count:int, read_count:int, total_reading_time_min:int, average_reading_time_min:int, last_summary_at?:date-time, favorite_topics?:[], favorite_domains?:[], language_distribution?:object }`.
- `SummaryPayload`: aligns to summary contract (summary_250/1000, tldr, key_ideas[5], topic_tags, entities, estimated_reading_time_min, key_stats, readability, metadata, extractive_quotes, questions_answered, topic_taxonomy, hallucination_risk, confidence, insights?, forwarded_post_extras?).
- `Summary`: `{ id, request_id, lang, is_read, version, created_at, json_payload: SummaryPayload, title?, domain?, url?, tldr? }`.
- `SummaryListItem`: lighter `{ id, request_id, title, domain, url, tldr, summary_250, reading_time_min, topic_tags, is_read, lang, created_at, confidence?, hallucination_risk? }`.
- `PaginatedSummaries`: `{ items: [SummaryListItem], stats?: { total_summaries, unread_count }, pagination: Pagination }`.
- `SummaryContent`: `{ summary_id, request_id?, format: enum(markdown, text), content: string (full article content for offline reading, typically Markdown), content_type (e.g., text/markdown), lang?, source_url?, title?, domain?, retrieved_at: date-time, size_bytes?, checksum_sha256? }`.
- `SearchResultItem`: `{ request_id, summary_id, url, title, domain, snippet, tldr?, published_at?, created_at, relevance_score?, topic_tags?, is_read? }`.
- `SearchResponse`: `{ results: [SearchResultItem], pagination: Pagination, query: string }`.
- `Request`: `{ id, type: enum url|forward, status: enum pending|processing|success|error, correlation_id, input_url?, normalized_url?, dedupe_hash?, lang_detected?, created_at:date-time }`.
- `RequestStatus`: `{ request_id, status, stage?, progress?, estimated_seconds_remaining?, error_stage?, error_type?, error_message?, can_retry?, correlation_id?, updated_at }`.
- `SubmitRequestResponse`: `{ request_id, correlation_id, type, status, estimated_wait_seconds?, created_at, is_duplicate, duplicate_summary?: SummaryListItem, duplicate_request_id?, duplicate_summary_id? }`.
- `DuplicateUrlCheckResponse`: `{ is_duplicate: bool, normalized_url, dedupe_hash, request_id?, summary_id?, summarized_at?, summary?: SummaryListItem }`.
- `UserPreferencesResponse`, `UserStatsResponse`, `LoginResponse` (tokens + user + preferences?).

### Sync Contracts
- `SyncSessionResponse`: `{ session_id, expires_at, default_limit, max_limit, last_issued_since? }`.
- `SyncEntityEnvelope`: `{ entity_type enum (summary|request|preference|stat|crawl_result|llm_call), id (int|string), server_version:int, updated_at:date-time, deleted_at?:date-time }`.
- `FullSyncItem`: combines `SyncEntityEnvelope` + entity payload (summary, request, preference, stat) where applicable.
- `FullSyncResponse`: `{ session_id, has_more: bool, next_since?:int, items:[FullSyncItem], pagination: Pagination }`.
- `DeltaSyncResponse`: `{ session_id, since:int, has_more: bool, next_since?:int, created:[FullSyncItem], updated:[FullSyncItem], deleted:[SyncEntityEnvelope] }`.
- `SyncApplyItem` (request) is already defined; response items: `{ id, entity_type, status: enum applied|conflict|invalid, server_version, server_snapshot?, error_code?, message? }`.
- `SyncApplyResponse`: `{ session_id, results:[SyncApplyResult], conflicts:[SyncApplyResult], has_more?:bool }`.
- Conflict semantics: if `last_seen_version < current_version`, respond 409 with ErrorResponse and conflict details or in apply results; `next_since` always monotonic; tombstones carry `deleted_at`.

### Error Handling
- `ErrorResponse` reused across 401/403/404/409/410/422/429/500.
- Validation errors embed `HTTPValidationError` in `error.details`.
- Rate limiting uses `retry_after` when relevant.

### New Endpoint: Fetch Full Article Content (Q4 2025)
- Path: `GET /v1/summaries/{summary_id}/content`
- Purpose: deliver full article content for offline reading (Markdown-first) tied to an existing summary.
- Params:
  - `summary_id` (path, required, int)
  - `format` (query, optional, enum `markdown|text`, default `markdown`)
- Response:
  - `SummaryContentResponseEnvelope` (`success=true`, `data.content: SummaryContent`, `meta` per envelope rules).
  - Content is UTF-8, Markdown by default; `content_type` reflects actual format (e.g., `text/markdown`, `text/plain`).
  - Includes `retrieved_at`, `size_bytes`, `checksum_sha256` for caching/offline integrity.
- Errors: 401/403/404/429/500 use existing `ErrorResponse`.
- Notes: Content comes from stored crawl/transcript artifacts; no schema changes to summaries.

### Pagination & Query Encoding
- Pagination block `{ total, limit, offset, has_more, next_cursor? }` for list/search/sync.
- Array query params documented as repeated keys (`tags=ai&tags=travel`).

### Servers
- Add `servers` for production and staging (placeholders configurable).

## Compatibility
- Routes and existing fields stay; new optional fields are marked nullable; defaults noted.
- Envelopes stay aligned with TD_response_contracts (`success/data/meta`).

## Testing
- Lint/validate OpenAPI YAML and generated JSON.
- Smoke codegen check (Kotlin/Swift) to ensure no `Any` for primary entities.
- Contract assertions: responses include meta.correlation_id, pagination on list/search/sync, error responses use ErrorResponse with codes.
