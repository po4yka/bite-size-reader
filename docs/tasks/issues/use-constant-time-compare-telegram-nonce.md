---
title: Use constant-time compare for Telegram link nonce
status: doing
area: auth
priority: high
owner: Senior Python Backend Engineer
blocks: [review-mobile-auth-threat-model]
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Use constant-time compare for Telegram link nonce #repo/ratatoskr #area/auth #status/doing ⏫

## Background

From the security review in [[review-mobile-auth-threat-model]] (finding B3):

`app/api/routers/auth/endpoints_telegram.py:146` validates the link-confirmation nonce with a plain `payload.nonce != link_nonce` comparison, while every other security-sensitive comparison in this module already uses `hmac.compare_digest` (e.g. `webapp_auth.py:68`, `telegram.py:110`, `endpoints_secret_keys.py:142`).

## Risk

High in principle (anti-replay/CSRF-class token), low in practice (32-byte URL-safe random, 10-min TTL). Easy fix; should be uniform across the auth module.

## Acceptance criteria

- [ ] Replace `payload.nonce != link_nonce` with `not hmac.compare_digest(payload.nonce, link_nonce)`.
- [ ] Add a regression test in `tests/api/auth/test_telegram_link.py` asserting the constant-time path is taken.
- [ ] Spot-check the rest of `app/api/routers/auth/` for any remaining non-constant-time security comparisons and fix in the same PR.

## Definition of done

Fix merged, tests pass, unblocks [[review-mobile-auth-threat-model]].
