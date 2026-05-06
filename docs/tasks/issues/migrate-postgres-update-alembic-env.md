---
title: Make Alembic env SQLAlchemy-native and async
status: backlog
area: db
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-build-data-migrator
blocked_by:
  - migrate-postgres-baseline-alembic-revision
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Make Alembic env SQLAlchemy-native and async #repo/ratatoskr #area/db #status/backlog ⏫

## Objective

Rewrite `app/db/alembic/env.py` and shrink `app/db/alembic_runner.py` to a
SQLAlchemy-native, asyncpg-aware setup that drives Alembic from
`Base.metadata` for autogenerate.

## Context

Today:

- `alembic.ini` has sentinel `sqlalchemy.url = sqlite:///`.
- `app/db/alembic/env.py` reads `DB_PATH` and builds a SQLite URL.
- `app/db/alembic_runner.py` (~130 LOC) handles cohabitation with the legacy
  `migration_history` table and stamp-on-fresh-DB semantics for SQLite.

After M4, all of that goes away:

- The legacy SQLite revisions live under
  `app/db/alembic/versions/_legacy_sqlite/` and are excluded from
  `version_locations`.
- The new baseline `0001_baseline_sqlalchemy.py` is the single root.
- `migration_history` table never existed on Postgres.

Target shape for `env.py`:

```python
from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.config.settings import settings
from app.db.base import Base
import app.db.models  # noqa: F401 — import all model classes for metadata registration

config = context.config
config.set_main_option("sqlalchemy.url", settings.runtime.database.dsn)
target_metadata = Base.metadata

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

# Runs sync migrations against an open async connection (Alembic's contract).
def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

`alembic_runner.py` collapses to:

```python
def upgrade_to_head(dsn: str) -> None:
    cfg = _build_alembic_config(dsn)
    command.upgrade(cfg, "head")
```

## Acceptance criteria

- [ ] `app/db/alembic/env.py` rewritten per the structure above; supports
      `postgresql+asyncpg://…` URLs.
- [ ] `app/db/alembic_runner.py` reduced to `_build_alembic_config`,
      `upgrade_to_head`, and `print_status`. No `sqlite_master`, no
      `migration_history` cohabitation, no SQLite stamping.
- [ ] `python -m app.cli.migrate_db` runs `alembic upgrade head` cleanly against
      a fresh Postgres and reports head.
- [ ] `alembic revision --autogenerate -m "test"` against a no-op state
      generates an empty migration (proves metadata is loaded correctly).
- [ ] No reference to `DB_PATH` remains in Alembic code; the URL comes from
      `DATABASE_URL` via `settings.runtime`.

## Notes

- The async-engine pattern uses Alembic's `connection.run_sync` bridge — that's
  the canonical async-Alembic approach in SQLAlchemy 2.0.
- Verify on aarch64 in CI; asyncpg's binary protocol behaviour can differ from
  psycopg's.
