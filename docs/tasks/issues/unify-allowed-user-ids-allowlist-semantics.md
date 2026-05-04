---
title: Unify ALLOWED_USER_IDS allowlist semantics across all auth paths
status: doing
area: auth
priority: high
owner: Senior Python Backend Engineer
blocks: [review-mobile-auth-threat-model]
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Unify ALLOWED_USER_IDS allowlist semantics across all auth paths #repo/ratatoskr #area/auth #status/doing ⏫

## Background

From the security review in [[review-mobile-auth-threat-model]] (finding B1):

`app/api/routers/auth/dependencies.py:117-120` calls `Config.is_user_allowed(user_id, fail_open_when_empty=True)`, while `webapp_auth.py:103`, `telegram.py:117`, and `secret_auth.py:76` all pass `fail_open_when_empty=False`. The startup validator at `app/config/settings.py:315-323` prevents an empty list under production config, but is bypassed by `allow_stub_telegram=True` (the lazy-load default in `secret_auth._get_cfg`).

## Risk

High. Any deployment that instantiates `Settings(allow_stub_telegram=True)` and forgets `ALLOWED_USER_IDS` allows any validly-signed JWT to pass `get_current_user`. Other auth paths fail closed in the same condition — this is a divergence between code paths that must be either codified (documented as intentional multi-user mode) or removed.

## Acceptance criteria

- [ ] Decision recorded: keep fail-open for JWT (multi-user) OR unify to fail-closed.
- [ ] If kept: add a startup `WARNING` log when `ALLOWED_USER_IDS` is empty AND any JWT path is used; document in `docs/MOBILE_API_SPEC.md` §Authentication.
- [ ] If unified: change `dependencies.py:117-120` to `fail_open_when_empty=False` and update `tests/api/auth/` with a matrix test (empty | populated-include | populated-exclude) × {JWT, WebApp, Telegram-Login, secret-login}.
- [ ] No regression in existing WebApp / secret-login tests.

## Definition of done

Decision recorded, implementation done (or explicitly deferred with rationale), unblocks [[review-mobile-auth-threat-model]].
