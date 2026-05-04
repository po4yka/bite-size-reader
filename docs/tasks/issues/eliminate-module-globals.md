---
title: Eliminate 23 module-level singletons and fold into ApiRuntime DI graph
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Eliminate 23 module-level singletons and fold into ApiRuntime DI graph #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

23 module-level `global` variables across the API and config layers create a parallel "ambient" DI system alongside the explicit `ApiRuntime` graph. The most dangerous is `_current_runtime` in `app/di/api.py` — it leaks between test processes. `_repo_factory` in `collection_service.py` is invisible to the DI graph and `None` before `lifespan` runs.

## Context

- `app/di/api.py` — `_current_runtime` set via `set_current_api_runtime()`, read via `get_current_api_runtime()`
- `app/api/services/collection_service.py` — `_repo_factory` set by `CollectionService.configure()` in lifespan
- `app/api/middleware.py`, `app/api/routers/auth/dependencies.py`, `app/api/routers/auth/tokens.py` — auth cache globals
- `app/api/main.py:100` — `CollectionService.configure()` side-effect in lifespan

## Acceptance criteria

- [ ] `_current_runtime` removed; consumers access runtime via `request.app.state.runtime`
- [ ] `CollectionService` receives its repository via constructor injection from `ApiRuntime`, not via `configure()`
- [ ] Auth module globals replaced with FastAPI dependency injection via `request.app.state`
- [ ] Tests no longer share global state between test cases

## Definition of done

`rg 'global _' app/api/ app/di/` returns zero results.
