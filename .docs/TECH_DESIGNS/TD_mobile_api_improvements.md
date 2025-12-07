# Mobile API Hardening and Improvement Plan
- Date: 2025-12-06
- Author: AI Partner

## Context
- Mobile API currently uses in-memory rate limiting and sync sessions, legacy background processor config, ad-hoc response shapes, and minimal auth token lifecycle. Multi-worker durability and contract consistency are at risk.

## Goals and Non-Goals
- Goals: harden auth/session safety, make limits and sync durable, align contracts to documented schemas, improve background processing reliability, and prepare for multi-worker deployment.
- Non-Goals: redesign of core summarization pipeline or database schema beyond what is needed for API correctness.

## Architecture / Flow (targeted changes)
- Rate limiting and sync: move counters/sessions to shared store (Redis/SQLite), key by user/client_id with per-endpoint buckets, emit headers consistently.
- Auth: include `is_owner` and `client_id` in access tokens, rotate refresh tokens, enforce allowlist defaults explicitly, and return errors via APIException. **Added:** optional secret-key login backed by DB-stored client secrets with owner-only CRUD (create/rotate/revoke/list) and hashed storage.
- Linking: mobile users can link/unlink Telegram from settings using Telegram Login Widget; flow uses nonce issuance → hash verification → linkage fields persisted on `users` with audit-friendly timestamps.
- API surface: wrap responses in typed Pydantic response models (success/error/meta) and standardize error codes. **Implemented:** unified success envelopes via `success_response`, per-endpoint data models, routers returning typed payloads.
- Background processing: refactor `app/api/background_processor.py` to new config/DI, add idempotent request locks, retries with backoff, and propagate correlation_id. **Implemented:** config-driven init, per-request locks, semaphore from `runtime.max_concurrent_calls`, 3x retry with backoff.
- Sync protocol: support created/updated/deleted with server version/ETag; configurable chunk size; conflict reporting; delete semantics distinct from read.
- Observability: structured logs with correlation_id in background tasks and rate limiter decisions.

## Redis-backed limits and sessions
- Store: Redis preferred; fallback to in-process noop when disabled/unavailable (warn + metrics). Keys prefixed by `cfg.redis.prefix` (default `bsr`).
- Connection: `cfg.redis.url` or host/port/db/prefix. Single shared async client; graceful close on shutdown.
- Rate limits:
  - Config under `cfg.api_limits`: default window 60s, cooldown multiplier 2.0, max concurrent 3.
  - Per-path buckets (requests/s): `summaries` 200, `requests` 10, `search` 50, default 100; keyed by authenticated user_id else IP.
  - Sliding window counter with TTL = window+grace; headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` on 429.
  - Log extras: correlation_id, user_id/client_ip, path bucket, retry_after, window.
- Sync sessions:
  - Keys `sync:session:{sync_id}` storing expiry timestamp; TTL = configured `sync_expiry_hours` (default 1h). Validation uses Redis existence/TTL.
  - Chunk size configurable per request (bounded 1..500) but also overridable via config default.
  - Expiry handled by Redis TTL; manual cleanup no longer needed.
- Error handling: If Redis unavailable and `redis.required=true`, return 503 with correlation_id; if `false`, continue with in-memory noop and emit warning metric.

## Data Model / Contracts
- Responses: adopt `SuccessResponse`/`ErrorResponse` wrappers and use explicit schemas per endpoint.
- Auth tokens: payload `{user_id, username, client_id, is_owner, type, exp, iat}`; refresh rotation required.
- Client secrets: new table `client_secrets` with `user_id`, `client_id`, `secret_hash`, `secret_salt`, `status (active|revoked|locked|expired)`, `label/description`, `expires_at`, `last_used_at`, `failed_attempts`, `locked_until`, `server_version`, timestamps. Hashing uses per-secret salt + global pepper (configurable) with constant-time verification; no plaintext is stored.
- Telegram link fields on `users`: `linked_telegram_user_id`, `linked_telegram_username`, `linked_telegram_photo_url`, `linked_telegram_first_name/last_name`, `linked_at`, `link_nonce`, `link_nonce_expires_at`; index on `linked_telegram_user_id`.
- Endpoints: `/v1/auth/secret-login` issues JWTs using client secret + client_id + user_id; owner-only management endpoints `/v1/auth/secret-keys` (create), `/v1/auth/secret-keys/{id}/rotate`, `/v1/auth/secret-keys/{id}/revoke`, `/v1/auth/secret-keys` (list) return enveloped Pydantic payloads without exposing hashes. **New:** `/v1/me/telegram` (GET status, DELETE unlink), `/v1/me/telegram/link` (POST begin nonce), `/v1/me/telegram/complete` (POST finish with Telegram payload + nonce).
- Endpoints: `/v1/auth/secret-login` issues JWTs using client secret + client_id + user_id; owner-only management endpoints `/v1/auth/secret-keys` (create), `/v1/auth/secret-keys/{id}/rotate`, `/v1/auth/secret-keys/{id}/revoke`, `/v1/auth/secret-keys` (list) return enveloped Pydantic payloads without exposing hashes.
- Sync: version fields (`updated_at`, `deleted_at`) on `Summary` (and request if needed) to compute delta; sync session metadata persisted with expiry.

## Decisions (proposed)
- Use Redis (if available) for rate limits and sync sessions; fallback to SQLite-backed tables for single-node deployments.
- Keep HS256 JWT but enforce 32+ char secret and configurable expiry; consider refresh TTL 30d with rotation.
- Keep FastAPI but introduce dependency-injected services for rate limiter and sync manager.
- Preserve existing dedupe logic but add request-level lock to avoid double processing.

## Risks and Mitigations
- Multi-process cache inconsistency: mitigate by shared store and tests.
- Backward compatibility: maintain existing paths/fields; introduce new claims carefully; version responses.
- Operational complexity: provide env toggles and defaults for Redis/SQLite implementations.
- Secret sprawl: secrets are hashed with per-secret salt + pepper; management endpoints are owner-only and return plaintext only on creation/rotation; lockout + expiry + allowlists reduce blast radius.

## Testing Strategy
- Unit: auth token encode/decode/claims, rate limit bucket decisions, sync session lifecycle, background retry logic.
- Integration: login (Telegram + secret-key) + protected endpoints, submit + status + summary retrieval, sync full/delta flows, search auth enforcement; secret management CRUD happy/locked/expired/revoked paths.
- E2E (optional): mobile client happy path with Redis-backed rate limiting.

## Configuration (secret-key auth)
- `SECRET_LOGIN_ENABLED` (bool, default false)
- `SECRET_LOGIN_MIN_LENGTH` / `SECRET_LOGIN_MAX_LENGTH` (length bounds for secrets)
- `SECRET_LOGIN_MAX_FAILED_ATTEMPTS` / `SECRET_LOGIN_LOCKOUT_MINUTES` (lockout policy)
- `SECRET_LOGIN_PEPPER` (optional pepper; falls back to `JWT_SECRET_KEY` when unset)

## Rollout
- Phase 1: implement shared rate limiter + sync store behind feature flags.
- Phase 2: refactor background processor and response contracts.
- Phase 3: add sync versioning and deletion semantics.
- Add migration guide and env samples; monitor logs for rate-limit and processing errors.

## Search Performance Improvements (2025-12-06)
- Chroma semantic search now uses a managed singleton with explicit shutdown; FastAPI shutdown event calls the lifecycle hook to close the vector store and embedding service.
- EmbeddingService and ChromaVectorStore expose close/aclose to release model memory and HTTP clients.
- Trending topics endpoint limits scan size (cap 1000 rows, adaptive to requested limit) and caches results per-user/params with a short TTL; cache is cleared on summary insert/update to reflect new tags promptly.
