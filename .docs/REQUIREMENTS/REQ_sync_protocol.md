# Sync Protocol Requirements
- Date: 2025-12-06
- Author: AI Partner

## Background
- Mobile clients need durable, resumable sync across all user-scoped data (requests, summaries, crawl/LLM artifacts, user/chat metadata) with multi-worker safety.
- Current in-memory sync sessions and fixed chunk size lack versioning, delete semantics, and conflict handling; multi-process deployments risk divergence.
- Aligns with `TD_mobile_api_improvements.md` goal to support created/updated/deleted flows with server version/ETag, configurable chunking, and explicit conflict/error reporting.

## Functional Requirements
- FR1: Support delta sync covering created/updated/deleted entities for user-scoped data: users/chats, requests, summaries (including source/crawl/LLM artifacts references), preferences/stats.
- FR2: Each entity payload must include server-assigned versioning fields (`updated_at`, optional `deleted_at`, server_version/etag) to drive client pagination and conflict detection.
- FR3: Provide chunked listing for both full and delta sync with client-supplied `limit` bounded by config (min 1, max 500) and server default; responses must include `has_more` and `next_cursor`/`since` indicators.
- FR4: Deletions must be represented as tombstones (id + deleted_at + version) and not overload read flags; clients must receive them in-order with creations/updates.
- FR5: Conflict handling must be explicit: client uploads carry last_seen_version; server resolves using policy (server-wins baseline) and returns per-item conflict results with error codes and server state snapshot.
- FR6: Validation is mandatory on inbound sync uploads: schema, field whitelists (e.g., only is_read or client notes), version monotonicity, and authorization scoping per user/client_id.
- FR7: Sync sessions must be resumable with TTL-backed session tokens/IDs; expired sessions return 410 with correlation_id and guidance.
- FR8: Meta must follow the unified response envelope (success/error) with correlation_id, pagination/meta, and standard error codes; rate-limit and retry headers remain intact.

## Non-Functional Requirements
- NFR1: Durable across multi-worker/process nodes using shared store (Redis preferred, SQLite fallback) for session TTL and rate limits.
- NFR2: Idempotent: repeating the same `since` + session must not duplicate state; uploads with identical payload+version are safe no-ops.
- NFR3: Performance: chunk fetch targets <200ms p95 on warm cache; payload size guarded by chunk limits and optional compression.
- NFR4: Backward compatibility: maintain existing endpoints but respond with new envelopes; opt-in flags only if necessary for legacy clients.

## Constraints
- Must use existing envelope/meta contract from `TD_response_contracts.md`.
- Version sources rely on DB timestamps; no client clocks trusted.
- Redis optional; when disabled, behavior must degrade to single-node-safe SQLite/in-memory with warnings but same API contract.
- No schema expansion beyond required version/deleted fields already present or planned in `TD_mobile_api_improvements.md`; propose ADR if additional fields become necessary.

## Acceptance Criteria
- AC1: Full sync returns complete user scope in bounded chunks with `has_more=false` at completion and valid envelopes/meta.
- AC2: Delta sync returns created/updated/deleted sets ordered by version, respects `since` cursor, and emits tombstones for deletes.
- AC3: Upload with stale `last_seen_version` triggers conflict response containing server state and conflict code; fresh version applies update and increments version.
- AC4: Validation rejects payloads with out-of-scope fields, missing versions, or cross-user IDs; responds with standardized error envelope and correlation_id.
- AC5: Session expiry returns 410 with guidance; reusing valid session is idempotent.
