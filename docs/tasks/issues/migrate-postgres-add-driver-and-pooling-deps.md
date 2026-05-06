---
title: Add SQLAlchemy 2.0 and asyncpg dependencies
status: backlog
area: db
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-introduce-database-factory
blocked_by:
  - migrate-postgres-decide-orm-strategy
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Add SQLAlchemy 2.0 and asyncpg dependencies #repo/ratatoskr #area/db #status/backlog ⏫

## Objective

Bring SQLAlchemy 2.0, asyncpg, and the helpers SQLAlchemy needs in async mode into
`pyproject.toml`/`uv.lock` without changing runtime behaviour yet.

## Context

Required deps for the SQLAlchemy 2.0 + asyncpg target:

- `sqlalchemy>=2.0.30,<3.0` — typed `Mapped[T]` declarative + async sessions.
- `asyncpg>=0.29` — async Postgres driver.
- `greenlet>=3.0` — required by SQLAlchemy's async-to-sync bridge for type machinery.
- `alembic>=1.13` — already present; ensure version is current.
- (For tests in T3) `pytest-asyncio`, `pytest-postgresql` — listed there, not here.

`peewee` stays in `pyproject.toml` until phase L1 — the data migrator (T2) uses a
frozen Peewee snapshot to read the SQLite source.

The Pi runs aarch64; `asyncpg` ships aarch64 wheels.

## Acceptance criteria

- [ ] `pyproject.toml` adds `sqlalchemy[asyncio]>=2.0.30,<3.0`, `asyncpg>=0.29`,
      `greenlet>=3.0` to project dependencies. Existing `peewee` and `alembic` lines
      remain.
- [ ] `uv.lock` regenerated via `uv lock` and committed.
- [ ] `make lint` and `make type` still pass; mypy on the new SQLAlchemy plugin
      surface is configured (`[tool.mypy]` adds the `sqlalchemy.ext.mypy.plugin`).
- [ ] Docker build succeeds locally and on aarch64 (`docker buildx build --platform
      linux/arm64 …`) — verifies the binary wheels resolve.
- [ ] No runtime code yet imports SQLAlchemy beyond a smoke import in a test fixture
      that asserts `from sqlalchemy import select` works.

## Notes

- Do **not** add `psycopg2-binary` or `psycopg`. asyncpg is the chosen driver; mixing
  drivers fragments the pool semantics.
- SQLAlchemy 2.0 mypy plugin is required for the typed model port to type-check
  cleanly. Wire it now so M1 lands clean.
