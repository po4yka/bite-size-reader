---
title: Convert /v1/auth/github error responses to the standard error envelope
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Convert /v1/auth/github error responses to the standard error envelope #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

`app/api/routers/auth/github.py` raises bare `HTTPException(status_code=..., detail="...")` for every 4xx path, which produces FastAPI's default `{"detail": "..."}` body. The mobile-api reference doc mandates the standard envelope `{success:false, error:{code, message, details, correlation_id}, meta:{...}}`. KMP error-path code that switches on `error.code` sees `null` for every GitHub OAuth failure, including user-recoverable cases like "Invalid or revoked GitHub token".

## Context

- Violating raises: `app/api/routers/auth/github.py:140, 142, 200, 267, 350, 352` — all `HTTPException(status_code=..., detail=str)`.
- Standard envelope spec: `docs/reference/mobile-api.md:102-118`.
- Compliant comparator: `app/api/routers/content/summaries.py:647, 686` raise `ValidationError` / `ResourceNotFoundError` from the shared error system that emits the envelope.

## Scope

- Replace every `HTTPException(...)` raise in `app/api/routers/auth/github.py` with the appropriate project-standard exception subclass (or a `JSONResponse` built from `success_response_error(...)`).
- Map error reasons to stable `error.code` values: - Invalid OAuth state → `oauth_state_invalid` - Token exchange failure → `github_token_exchange_failed` - Revoked / expired GitHub token → `github_token_invalid` - Rate-limited callback → `github_oauth_rate_limited`
- Snapshot test all `/v1/auth/github/*` 4xx paths and assert the envelope shape + stable `error.code`.

## Acceptance criteria

- [ ] No `HTTPException(...)` raises remain in `app/api/routers/auth/github.py`.
- [ ] Every 4xx response body matches the envelope schema in `docs/reference/mobile-api.md`.
- [ ] New `tests/api/test_envelope_consistency.py` covers each `/v1/auth/github/*` 4xx path and asserts the envelope shape.
- [ ] Document the new `error.code` values in `docs/reference/mobile-api.md`.

## References

- Router: `app/api/routers/auth/github.py:140-352`
- Envelope spec: `docs/reference/mobile-api.md:102-118`
- Compliant example: `app/api/routers/content/summaries.py:647-686`
