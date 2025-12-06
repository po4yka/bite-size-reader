# Sync Protocol Technical Design
- Date: 2025-12-06
- Author: AI Partner

## Context
- Sync is currently in-memory with fixed chunk size, no versioning/ETag, and deletes mapped to read flags, making multi-worker and offline clients unsafe.
- We must cover full user data scope (users/chats, requests, summaries, crawl/LLM artifacts references, preferences/stats) with created/updated/deleted semantics and conflict reporting.
- This design aligns with `REQ_sync_protocol.md` and `TD_mobile_api_improvements.md`, and reuses the envelope/meta contract from `TD_response_contracts.md`.

## Goals and Non-Goals
- Goals:
  - Provide durable, resumable sync sessions with chunked delivery and tombstones.
  - Enforce server-side versioning/ETag for deltas and uploads; explicit conflict responses.
  - Bound chunk sizing with configurable defaults/limits; include pagination meta.
  - Validate inbound changes and scope them to the authenticated user/client.
- Non-Goals:
  - Redesign of core summarization pipeline or DB schema beyond version/deleted fields already planned.
  - Client-side merge strategies beyond server-wins baseline.

## Architecture / Flow
- Endpoints (FastAPI `/v1/sync`):
  - `POST /sessions`: start/resume sync session; returns `session_id`, `expires_at` (TTL-backed), and default chunk limits. Requires auth.
  - `GET /delta`: parameters `session_id`, `since` (server_version cursor), optional `limit`; returns created/updated/deleted arrays, `has_more`, `next_since`, envelope meta.
  - `GET /full`: same shape as delta but returns entire scoped dataset segmented in chunks, ordered by `server_version`.
  - `POST /apply`: client uploads changes `{entity_type, id, action, last_seen_version, payload?}`; server applies allowed mutations and returns per-item results with conflicts.
- Session management:
  - Stored in shared store (`sync:session:{session_id}`) with expiry (default 1h) and user/client binding; contains last_issued_since cursor and negotiated chunk_limit.
  - TTL enforces expiry; missing/expired → 410 with correlation_id.
- Ordering:
  - Use `server_version` monotonic integer per entity (auto-increment or updated_at->version pair) to order deltas; `deleted_at` marks tombstones.
  - `since` cursor is inclusive-exclusive: return items where `server_version > since` sorted ascending; `next_since` = max returned version.
- Envelope/meta:
  - All responses use `success/error` wrapper with `meta` (correlation_id, timestamp, version/build, pagination `{limit, has_more, next_since}`).

## Data Model / Contracts
- Common fields:
  - `id`, `entity_type` (enum: user, chat, request, summary, crawl_result, llm_call, preference, stat), `server_version` (int), `updated_at` (UTC), optional `deleted_at`.
  - `etag`: hex string derived from `server_version` and payload hash for caching/if-match support (optional header).
- Delta/full response payload:
  - `created`: full records (no deleted_at).
  - `updated`: full records with latest values (deleted_at null).
  - `deleted`: tombstones `{id, entity_type, server_version, deleted_at}`.
  - `has_more`: bool; `next_since`: int.
- Upload (`POST /apply`) request item:
  - `{entity_type, id, action: 'update'|'delete', last_seen_version: int, payload?: object, client_ts?: string}`
  - Allowed mutable fields by entity:
    - summary: `is_read`, optional `client_note`.
    - request: client-level tags/notes (no status changes).
    - preference/stat: documented preference fields only.
  - Server rejects writes to immutable fields (content, embeddings, server timestamps).
- Upload response item:
  - `{id, entity_type, status: 'applied'|'conflict'|'invalid', server_version, server_snapshot?, error_code?}`
  - `conflict` includes server_snapshot (current record or tombstone) and `error_code=CONFLICT_VERSION`.
- Chunk sizing rules:
  - Config: `sync.default_limit=200`, `sync.max_limit=500`, `sync.min_limit=1`.
  - Request `limit` capped to `[min, max]`. Server may downsize if estimated payload > target size (e.g., 512KB) by reducing item count.
  - Items are ordered by `server_version`; chunking splits on boundaries without partial entity slicing.

## Decisions
- Versioning: adopt `server_version` monotonic integer per entity (leveraging DB row_version or generated from updated_at + sequence). Tombstones carry their version. `etag` = `sha256(f\"{entity_type}:{id}:{server_version}\")`.
- Conflict policy: server-wins baseline. If `last_seen_version < current_version`, return `conflict` with server snapshot; no mutation applied. If equal, apply allowed fields and bump version.
- Deletes: represented only via tombstones with `deleted_at`; no overload of read flags. Deleting an already-deleted item is idempotent and returns current tombstone.
- Sessions: stored in Redis with fallback to SQLite; bind to user_id+client_id to prevent cross-account reuse.
- Validation: strict schema per entity; unknown fields rejected; cross-user IDs rejected; `last_seen_version` required for apply.
- Pagination/meta: use existing response envelope helpers; include `has_more`, `next_since`, `limit` in meta.pagination.

## Risks and Mitigations
- Risk: Large payloads despite item limits. Mitigation: adaptive downsizing by estimated bytes and optional compression.
- Risk: Clock skew if relying on timestamps. Mitigation: use server_version as cursor; timestamps are informational only.
- Risk: Redis outage. Mitigation: if required flag set, return 503; else fallback to SQLite with warnings and same API contract.
- Risk: Client divergence on deletions. Mitigation: tombstones retained for configured retention window; conflicts include server snapshot.

## Testing Strategy
- Unit: version/etag generation, chunk sizing cap/downsize logic, conflict detection (stale vs current), tombstone emission, validation of allowed fields.
- Integration: start session, full sync over multiple chunks, delta sync with since cursor, upload apply success/conflict/invalid, session expiry (410), Redis required vs optional paths.
- Contract: response envelopes contain meta (correlation_id, pagination), arrays ordered by server_version, tombstones honored.

## Rollout
- Feature flag `SYNC_V2_ENABLED` guarding new endpoints/behavior; dual-run compatibility if needed.
- Migrations: ensure `server_version` (or row_version) and `deleted_at` available on synced entities; backfill initial version from updated_at order.
- Monitoring: log correlation_id with session_id and since/next_since; track conflict rates and payload sizes; alert on 503/410 spikes.
- Fallback: if feature disabled or store unavailable, keep existing in-memory sync but return warning in meta.debug (if debug enabled).
