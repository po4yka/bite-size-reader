---
title: Decouple SECRET_LOGIN_PEPPER from JWT signing key
status: doing
area: auth
priority: high
owner: Senior Python Backend Engineer
blocks: [review-mobile-auth-threat-model]
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Decouple SECRET_LOGIN_PEPPER from JWT signing key #repo/ratatoskr #area/auth #status/doing ⏫

## Background

From the security review in [[review-mobile-auth-threat-model]] (finding B2):

`app/api/routers/auth/secret_auth.py:42-52` (`_get_secret_pepper`) returns `cfg.runtime.jwt_secret_key` when `SECRET_LOGIN_PEPPER` is unset.

## Risk

High. Two unrelated security domains share a single secret: rotating `JWT_SECRET_KEY` invalidates every stored `ClientSecret.secret_hash` and locks every user out of secret-login. A leak of either secret compromises both — JWT signing keys live in different places (env, CI runners, deploy secrets) than DB peppers should.

## Acceptance criteria

- [ ] Production `.env` and `.env.example` require an explicit `SECRET_LOGIN_PEPPER` (≥32 chars, generated independently of `JWT_SECRET_KEY`).
- [ ] `_get_secret_pepper()` raises a startup `RuntimeError` if `SECRET_LOGIN_ENABLED=true` AND `SECRET_LOGIN_PEPPER` is unset (do not silently fall back to JWT key).
- [ ] Migration path documented for any pre-existing `ClientSecret` rows hashed under the old pepper (one-time re-hash on next successful login, or forced rotation banner).
- [ ] Bandit / pip-audit / unit tests still green.

## Definition of done

Security Engineer + Senior Python Backend Engineer sign off on the rotation plan; unblocks [[review-mobile-auth-threat-model]].
