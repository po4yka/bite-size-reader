---
title: Split auth rate-limit buckets so credentials-login does not share with refresh
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Split auth rate-limit buckets so credentials-login does not share with refresh #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/middleware.py:208-222` registers a dedicated rate-limit bucket only for `POST /v1/auth/secret-login`; every other auth endpoint (`credentials-login`, `telegram-login`, `refresh`, `secret-keys/*`) lands in the generic `"auth"` bucket. A spray attempt on `credentials-login` consumes the same budget as `refresh`, and unauthenticated requests are keyed by `request.client.host` so an attacker behind a CGNAT carrier IP can DoS legitimate login traffic for every tenant on that egress IP.

## Context

- Middleware bucket registration: `app/api/middleware.py:208-222`.
- Unauth key derivation: `app/api/middleware.py:194-200`.
- Existing per-endpoint lockout (correct but inner-layer): `app/api/routers/auth/endpoints_credentials.py:130-143`.

## Scope

- Add a `credentials_login` bucket (limit lower than `secret_login`, e.g. 5 attempts / 15min / actor key).
- Ensure unauthenticated `/refresh` and `/credentials-login` keys include the request body's `client_id` (already in JWT for refresh) so per-client buckets exist alongside per-IP buckets.
- Document trust assumptions for `request.client.host` (CGNAT, proxy) in `docs/reference/mobile-api.md` §"Rate limits".
- Add a metric counter `ratatoskr_rate_limit_hits_total{bucket}` if not already present, with an alert when `credentials_login` hits exceed N/15min (= active credential stuffing).

## Acceptance criteria

- [ ] Each auth endpoint has its own bucket name in the middleware registration.
- [ ] `credentials_login` and `secret_login` buckets keyed by `(client_id, client_ip)` not `client_ip` alone.
- [ ] Integration test: 10 sequential failed logins from the same IP+client_id receive 429 on the 6th; switching `client_id` resets.
- [ ] Documentation updated.

## References

- Middleware: `app/api/middleware.py:194-222`
- Endpoint lockout: `app/api/routers/auth/endpoints_credentials.py:130-143`
- Related: [[fail-loud-on-prod-rate-limit-redis-override]]
