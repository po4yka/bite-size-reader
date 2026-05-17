---
title: Fail-loud on production RATE_LIMIT_REDIS_OVERRIDE for auth routes
status: backlog
area: ops
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Fail-loud on production RATE_LIMIT_REDIS_OVERRIDE for auth routes #repo/ratatoskr #area/ops #status/backlog 🔼

## Objective

`app/api/main.py:115-128` only logs a warning when `RATE_LIMIT_REDIS_OVERRIDE=true` in production, after which `app/api/middleware.py:539-575` falls back to the per-process `LocalRateLimiter`. With N uvicorn workers the effective auth rate limit is multiplied by N and resets on every restart — exactly the wrong behaviour for brute-force mitigation. The override is silent enough to leak into production by accident.

## Context

- Warning path: `app/api/main.py:115-128`.
- Limiter fallback: `app/api/middleware.py:539-575`.
- Local limiter: `app/api/local_rate_limiter.py`.
- The code already supports hard-fail via `REDIS_REQUIRED=true` at `app/api/middleware.py:543-550` — the override is the soft spot, not the limiter itself.

## Scope

- Promote the override-in-production check from `logger.warning` to a startup error for auth routes specifically: - On startup, if `APP_ENV=production` AND `RATE_LIMIT_REDIS_OVERRIDE=true`, raise a `ConfigurationError` for auth-bucket routes. - OR scope the override only to non-auth buckets — auth always requires Redis-backed limiting in prod.
- Add a deploy-time check (CI or Helm hook) that asserts `RATE_LIMIT_REDIS_OVERRIDE!=true` in the production env file.
- Document the policy in `docs/runbooks/` or a new `docs/reference/rate-limiting.md`.

## Acceptance criteria

- [ ] Production startup with `RATE_LIMIT_REDIS_OVERRIDE=true` fails fast (exit non-zero) when Redis is unavailable for auth buckets.
- [ ] Override remains valid for non-auth buckets in dev.
- [ ] Test asserts startup failure path.
- [ ] Documentation updated.

## References

- Override warning: `app/api/main.py:115-128`
- Limiter fallback: `app/api/middleware.py:539-575`
- Related: [[split-auth-rate-limit-buckets]]
