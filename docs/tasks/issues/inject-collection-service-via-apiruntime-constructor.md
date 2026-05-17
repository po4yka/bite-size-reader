---
title: Replace CollectionService single-element-holder with ApiRuntime constructor injection
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Replace CollectionService single-element-holder with ApiRuntime constructor injection #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`CollectionService` (`app/api/services/collection_service.py`) is
the last remnant of the eliminated module-globals pattern flagged
in the now-closed `eliminate-module-globals` task. It still uses
`_repo_factory_holder: list[Callable[..., Any] | None] = [None]`
plus a classmethod `configure()` and `_repo()` resolver on a 566-
line class with 25 class/static methods. Removing the holder lets
`ApiRuntime` construct the service like every other API service
and unblocks per-request scoping (tests, future read-replica
support, multi-tenant).

## Context

- Holder + classmethod surface: `app/api/services/collection_service.py:32-56`.
- Inline comment at lines 33-35 explicitly defers the fix to
  "constructor injection from ApiRuntime" and points at the
  deleted `eliminate-module-globals` task (now in git history
  only) — that stale wiki-link inside the source file should be
  removed at the same time.
- `ApiRuntime` (`app/di/api.py:54-110`) already owns the `Database`
  and constructs every other application service; adding
  `CollectionService` is mechanical.
- Completion record (`docs/tasks/COMPLETION-2026-05-17.md`) flags
  this as inline TODO #4 — "deferred quality follow-up, not a
  correctness follow-up".

## Scope

- Convert `CollectionService` to instance methods with
  `__init__(self, repo_factory: Callable[[Database], CollectionRepository])`.
- Replace every `cls._repo()` call with `self._repo()` (or pass the
  repo into each method).
- Delete `_repo_factory_holder`, `configure()`, and any other
  module-level state.
- Construct the service in `build_api_runtime`
  (`app/di/api.py:54-110`) and expose via `ApiRuntime` (e.g.
  `runtime.collections`).
- Update `app/api/routers/collections.py` (and any other consumer)
  to resolve the service via `Depends(...)` against the runtime.
- Remove the stale `[[eliminate-module-globals]]` wiki-link inline
  comment.

## Acceptance criteria

- [ ] `rg "_repo_factory_holder|@classmethod"
  app/api/services/collection_service.py` returns zero matches.
- [ ] `ApiRuntime` exposes the service and is the only construction
  site.
- [ ] Existing collections endpoint integration tests pass
  unchanged (refactor is behaviour-preserving).
- [ ] mypy + ruff clean.

## References

- Current service: `app/api/services/collection_service.py:32-56`
- DI runtime: `app/di/api.py:54-110`
- Router: `app/api/routers/collections.py`
- Completion record: `docs/tasks/COMPLETION-2026-05-17.md` (inline TODO #4)
