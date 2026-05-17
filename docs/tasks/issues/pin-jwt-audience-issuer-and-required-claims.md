---
title: Pin JWT audience, issuer, and required claims on decode
status: backlog
area: auth
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Pin JWT audience, issuer, and required claims on decode #repo/ratatoskr #area/auth #status/backlog 🔼

## Objective

`jwt.decode` at `app/api/routers/auth/tokens.py:206` pins the
algorithm (`algorithms=[ALGORITHM]`) — which correctly blocks the
`none`-alg attack — but does not set `audience`, `issuer`, or
`options.require`. A token missing `exp` would decode successfully
if signed with the right secret, and a token minted for one
purpose (mobile API) could be reused for another (MCP HTTP-auth)
because there is no per-audience separation.

## Context

- Call site: `app/api/routers/auth/tokens.py:206` —
  `jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])`.
- The same helper is the only JWT validator referenced from the
  bearer dependency at `app/api/dependencies/auth.py` (sample
  call sites cite this helper, not a re-implementation).
- Defense-in-depth gap — no exploitable hole today because the
  helper is single-purpose, but the moment MCP HTTP-auth shares
  the secret, the audience gap becomes exploitable.

## Scope

- Pass `audience="ratatoskr-api"` and `issuer="ratatoskr"` to
  `jwt.decode`.
- Add `options={"require": ["exp", "iat", "type", "user_id"]}`.
- Update `create_*_token` builders in `tokens.py` to set the same
  `iss` and `aud` claims.
- Migration plan for in-flight tokens: 5-minute grace window where
  the validator accepts missing `aud`/`iss` (log a deprecation
  warning), then enforce.
- Document the audience values in
  `docs/reference/mobile-api.md` §"Auth tokens".

## Acceptance criteria

- [ ] Tokens missing `exp` / `iat` / `type` / `user_id` are
  rejected with `InvalidTokenError`.
- [ ] Tokens with a wrong `aud` or `iss` are rejected.
- [ ] Existing token-flow integration tests pass; new test asserts
  a token with stripped `aud` is rejected.
- [ ] Backwards-compatibility window documented and removable in a
  follow-up after one release.

## References

- Validator: `app/api/routers/auth/tokens.py:206`
- Bearer dep: `app/api/dependencies/auth.py`
- Audit finding: hexagonal-layer + security review, 2026-05-17
