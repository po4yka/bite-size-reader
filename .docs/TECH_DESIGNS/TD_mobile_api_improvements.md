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
- Auth: include `is_owner` and `client_id` in access tokens, rotate refresh tokens, enforce allowlist defaults explicitly, and return errors via APIException.
- API surface: wrap responses in typed Pydantic response models (success/error/meta) and standardize error codes. **Implemented:** unified success envelopes via `success_response`, per-endpoint data models, routers returning typed payloads.
- Background processing: refactor `app/api/background_processor.py` to new config/DI, add idempotent request locks, retries with backoff, and propagate correlation_id. **Implemented:** config-driven init, per-request locks, semaphore from `runtime.max_concurrent_calls`, 3x retry with backoff.
- Sync protocol: support created/updated/deleted with server version/ETag; configurable chunk size; conflict reporting; delete semantics distinct from read.
- Observability: structured logs with correlation_id in background tasks and rate limiter decisions.

## Data Model / Contracts
- Responses: adopt `SuccessResponse`/`ErrorResponse` wrappers and use explicit schemas per endpoint.
- Auth tokens: payload `{user_id, username, client_id, is_owner, type, exp, iat}`; refresh rotation required.
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

## Testing Strategy
- Unit: auth token encode/decode/claims, rate limit bucket decisions, sync session lifecycle, background retry logic.
- Integration: login + protected endpoints, submit + status + summary retrieval, sync full/delta flows, search auth enforcement.
- E2E (optional): mobile client happy path with Redis-backed rate limiting.

## Rollout
- Phase 1: implement shared rate limiter + sync store behind feature flags.
- Phase 2: refactor background processor and response contracts.
- Phase 3: add sync versioning and deletion semantics.
- Add migration guide and env samples; monitor logs for rate-limit and processing errors.

## Search Performance Improvements (2025-12-06)
- Chroma semantic search now uses a managed singleton with explicit shutdown; FastAPI shutdown event calls the lifecycle hook to close the vector store and embedding service.
- EmbeddingService and ChromaVectorStore expose close/aclose to release model memory and HTTP clients.
- Trending topics endpoint limits scan size (cap 1000 rows, adaptive to requested limit) and caches results per-user/params with a short TTL; cache is cleared on summary insert/update to reflect new tags promptly.
