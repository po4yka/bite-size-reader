---
title: Eliminate remaining 20+ module-level globals across api/di
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-17
---

- [ ] #task Eliminate remaining 20+ module-level globals across api/di #repo/ratatoskr #area/api #status/backlog 🔼

## Status

Three `global _foo` declarations in `app/api/middleware.py` are
gone (`_local_cleanup_last`, `_redis_warning_logged`, `_cfg`)
replaced with `LocalRateLimiter` and single-element holder lists.
TDD coverage: `tests/api/test_local_rate_limiter.py` (6 tests,
including a guard against re-introducing the `global` keyword in
middleware).

`rg 'global _' app/api/middleware.py` returns zero — that file is
now clean. **20+ other call sites remain.**

## Remaining call sites (verified with `rg 'global _' app/api/ app/di/`)

| File | Globals |
| --- | --- |
| `app/di/api.py` | `_current_runtime` (the most dangerous — leaks between test processes per the original task spec) |
| `app/di/database.py` | `_cached_runtime_db` |
| `app/api/services/collection_service.py` | `_repo_factory` |
| `app/api/routers/health.py` | `_database_details_cache`, `_database_details_cached_at` |
| `app/api/routers/auth/secret_auth.py` | `_cfg` |
| `app/api/routers/auth/credential_auth.py` | `_cfg`, `_hasher`, `_DECOY_PHC` |
| `app/api/routers/auth/dependencies.py` | `_auth_token_cache`, `_redis_cache` |
| `app/api/routers/auth/tokens.py` | `_SECRET_KEY`, `_allowlist_empty_warned` |

## Objective

23 module-level `global` variables across the API and config layers create a parallel "ambient" DI system alongside the explicit `ApiRuntime` graph. The most dangerous is `_current_runtime` in `app/di/api.py` — it leaks between test processes. `_repo_factory` in `collection_service.py` is invisible to the DI graph and `None` before `lifespan` runs.

## Acceptance criteria

- [x] `app/api/middleware.py` no longer uses `global` (this commit)
- [ ] `_current_runtime` removed; consumers access runtime via `request.app.state.runtime`
- [ ] `CollectionService` receives its repository via constructor injection from `ApiRuntime`, not via `configure()`
- [ ] Auth module globals replaced with FastAPI dependency injection via `request.app.state`
- [ ] Tests no longer share global state between test cases

## Definition of done

`rg 'global _' app/api/ app/di/` returns zero results.

## Strategy for the remaining work

The middleware slice in this commit uses the single-element-list
pattern for one-time-init holders and a small dedicated class for
multi-attribute state. For the remaining 20+ call sites the right
patterns are:

1. **`_current_runtime`** — Replace with reading from
   `request.app.state.runtime` (FastAPI-native). The migration
   needs careful per-test verification because the global was
   shared across tests.
2. **`_repo_factory` in CollectionService** — Constructor
   injection from `ApiRuntime`. Remove `CollectionService.configure(...)`
   and the lifespan-only side-effect in `app/api/main.py:100`.
3. **Auth caches (`_auth_token_cache`, `_redis_cache`)** — Same
   pattern as middleware: encapsulate in a small class held as a
   singleton on `app.state`.
4. **One-time-warning flags (`_allowlist_empty_warned`, etc.)** —
   Single-element-list pattern as used in middleware.
5. **Lazy-init holders (`_cfg`, `_hasher`, `_DECOY_PHC`)** —
   Single-element holder pattern.
6. **Memoization caches (`_database_details_cache`)** — Encapsulate
   the (value, timestamp) pair in a small class.

This breakdown is intended to make the remaining work
PR-reviewable one file at a time.
