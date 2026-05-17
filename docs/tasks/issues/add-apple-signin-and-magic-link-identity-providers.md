---
title: Add Apple Sign-In and magic-link email identity providers
status: backlog
area: auth
priority: medium
owner: unassigned
blocks: []
blocked_by:
  - add-email-delivery-sink
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Apple Sign-In and magic-link email identity providers #repo/ratatoskr #area/auth #status/backlog 🔼

## Objective

`app/api/routers/auth/` ships Telegram WebApp, GitHub OAuth
Device Flow, and credentials/cookie auth. No Google / Apple /
Microsoft / magic-link adapters. **Apple Sign-In is required by
App Store policy** if any other social login is offered, which
makes it a release-gate for iOS distribution. Magic-link is the
single largest conversion lift for passwordless onboarding.

## Context

- Existing auth providers: `app/api/routers/auth/` (Telegram
  WebApp, GitHub, credentials, cookies).
- Endpoint registry pattern:
  `app/api/routers/auth/endpoints.py` — registry-style router
  that accepts a new IdP cleanly.
- Apple Sign-In gate: required by App Store Review Guideline
  4.8 when any social login is offered.

## Scope

- New `app/api/routers/auth/apple.py`:
  - `POST /v1/auth/apple/start` (PKCE) and
    `POST /v1/auth/apple/callback`.
  - Apple JWT validation against the Apple public-keys JWKS.
  - Email-relay-aware identity normalization.
- New `app/api/routers/auth/magic_link.py`:
  - `POST /v1/auth/magic-link/request` (sends email via
    [[add-email-delivery-sink]]).
  - `GET /v1/auth/magic-link/verify?token=<...>` issues a JWT.
- Schema: extend `User` with a `user_identities` table allowing
  multiple linked identities per user (provider, subject,
  email).
- Reuse existing JWT issuance — **no Mobile API contract
  changes** (envelope, claims, lifetimes unchanged).
- Per-provider rate limit bucket (covered by
  [[split-auth-rate-limit-buckets]]).
- Document the new IdPs in
  `docs/reference/mobile-api.md` §"Auth providers".

## Acceptance criteria

- [ ] Apple Sign-In end-to-end works against Apple's developer
  test endpoint.
- [ ] Magic-link email round-trips: request → click → bot
  authed.
- [ ] Multiple identities can link to one user without
  duplicate-account churn.
- [ ] Existing JWT / refresh flow untouched.

## References

- Existing auth routers: `app/api/routers/auth/`
- Endpoint registry:
  `app/api/routers/auth/endpoints.py`
- Depends on: [[add-email-delivery-sink]]
- Related: [[split-auth-rate-limit-buckets]]
