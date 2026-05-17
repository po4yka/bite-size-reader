---
title: Extract repositories router DB queries into a RepositoryService
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Extract repositories router DB queries into a RepositoryService #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

`app/api/routers/repositories.py` is the single largest live
counter-example to the "FastAPI routers are transport-only" rule
documented in `docs/explanation/architecture-overview.md`. The
digest and system routers were already refactored to delegate to
`DigestFacade` and `SystemMaintenanceService`; repositories was
not. Persistence and vector-store details leak across the HTTP
boundary, making the router file the natural template for the next
router cleanup.

## Context

Confirmed by the hexagonal-layer audit on 2026-05-17:

- 6 `async with db.session()` / `db.transaction()` blocks doing
  `select(Repository)`, `select(func.count())`,
  `sql_delete(Repository)`, plus inline Qdrant
  `points_selector=PointIdsList(...)` invocations at
  `app/api/routers/repositories.py:244-270, 292-297, 378-407, 426-466`.
- Dynamic `_repo_embedding_gen` builders inside dependency providers
  at `app/api/routers/repositories.py:47-104`.
- Architecture rule cited at
  `docs/explanation/architecture-overview.md` §"Runtime policy" —
  "FastAPI routers remain transport-only: orchestration belongs in
  dedicated application/service classes."

## Scope

- Create `RepositoryService` (or `RepositoryReadModelUseCase`) under
  `app/application/services/` or `app/application/use_cases/`.
- Move list / get / delete / refresh SQL into the service.
- Move Qdrant point deletion into the existing repo-embedding
  adapter at `app/infrastructure/embedding/repository_embedding.py`.
- Router file contains no `select(`, `delete(`, `session.execute`,
  or `qdrant._client.*` calls.
- Wire the service via `ApiRuntime` constructor injection and
  resolve in the router via `Depends(...)`.

## Acceptance criteria

- [ ] `rg "select\(|delete\(|session\.execute|qdrant\._client"
  app/api/routers/repositories.py` returns zero matches.
- [ ] All existing repositories endpoint integration tests pass
  unchanged (refactor is behaviour-preserving).
- [ ] Repository service has unit tests with mocked repo + Qdrant.
- [ ] mypy + ruff clean for both router and new service.

## References

- Current router: `app/api/routers/repositories.py`
- Architecture rule: `docs/explanation/architecture-overview.md`
  §"Runtime policy" and §"Current seam examples (2026-03)"
- Existing good examples: `app/api/routers/digest.py` →
  `DigestFacade`; `app/api/routers/system.py` →
  `SystemMaintenanceService`.
- Embedding adapter: `app/infrastructure/embedding/repository_embedding.py`
