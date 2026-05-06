---
title: Introduce SQLAlchemy async engine and session factory
status: backlog
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-port-models-core
  - migrate-postgres-port-runtime-services
  - migrate-postgres-update-alembic-env
  - migrate-postgres-build-data-migrator
blocked_by:
  - migrate-postgres-add-driver-and-pooling-deps
  - migrate-postgres-decide-orm-strategy
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Introduce SQLAlchemy async engine and session factory #repo/ratatoskr #area/db #status/backlog 🔺

## Objective

Replace `DatabaseSessionManager` (Peewee) with a SQLAlchemy 2.0 `AsyncEngine` +
`async_sessionmaker[AsyncSession]` factory so the model port (M-phase) and call-site
port (R-phase) have a target to compile against.

## Context

Today (`app/db/session.py`) Peewee owns connection lifecycle, locking, retries, and
the database proxy. SQLAlchemy 2.0 inverts the model:

- `create_async_engine(dsn, pool_size, max_overflow, pool_pre_ping, pool_recycle)`
  owns the connection pool.
- `async_sessionmaker(bind=engine, expire_on_commit=False)` produces sessions.
- Callers do `async with session_maker() as session, session.begin(): …`.

Target shape:

```python
# app/db/session.py — illustrative

class Database:
    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = create_async_engine(
            config.dsn,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=True,
            pool_recycle=900,
        )
        self._session_maker = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_maker() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._session_maker() as session, session.begin():
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
```

`DATABASE_URL` parsing lives in `app/config/settings.py`. Required form:
`postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr`.

A retry decorator for `serialization_failure` (Postgres SQLSTATE `40001`) replaces
the old SQLite-busy-retry loop. Lives next to `Database` as `with_serialization_retry`.

## Acceptance criteria

- [ ] `app/db/session.py` exposes `Database`, `get_session()`, `get_session_for_request()`
      (FastAPI `Depends`), and `with_serialization_retry`. Public Peewee surface
      (`DatabaseSessionManager`, `_safe_db_operation`, etc.) is removed and all
      remaining imports of those symbols are deleted in the same PR (the rest of the
      codebase will not yet compile — that's fine; M and R phase tasks bring it back
      online module by module).
- [ ] `DATABASE_URL` parsed in `app/config/settings.py`; `settings.runtime` exposes a
      typed `DatabaseConfig(dsn, pool_size=8, max_overflow=4)`.
- [ ] FastAPI dependency `get_session_for_request` opens a transaction per request,
      commits on success, rolls back on exception, always closes.
- [ ] Bot/CLI usage uses the `async with database.session(): …` pattern.
- [ ] `with_serialization_retry` retries up to 3× with exponential backoff, only on
      `sqlalchemy.exc.OperationalError` whose pgcode matches `40001` or `40P01`
      (deadlock).
- [ ] `app/db/runtime/{operation_executor,rw_lock}.py` and `app/db/_models_*.py` are
      deleted in this PR. The build will be red until M1/M2 land.
- [ ] Smoke test: a hand-written empty SQLAlchemy `Base` + a single trivial `Ping`
      table proves `migrate()` (Alembic) and a session round-trip work end-to-end
      against a local Postgres.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Database/session, Pragmas, Healthchecks, and `asyncio.to_thread` sections.
- `expire_on_commit=False` is essential — in async, expired-after-commit attribute
  loads silently trigger lazy I/O outside the session and explode.
- `autoflush=False` because we prefer explicit `await session.flush()` for
  predictable timing in async code.
- This PR will leave `main` red until M1 lands. Land M1 in the same PR-stack /
  same merge train; do not push F3 alone to `main`.
