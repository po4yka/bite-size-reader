"""Alembic environment — Peewee/SQLite hybrid setup.

Reads DB_PATH from the environment and applies the same SQLite PRAGMAs as
DatabaseSessionManager (WAL, synchronous=normal, foreign_keys=on).

autogenerate is disabled (target_metadata = None) because the runtime ORM
is Peewee, not SQLAlchemy. All revisions are written by hand.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _get_db_url() -> str:
    """Resolve the SQLite URL.

    Priority order:
    1. sqlalchemy.url set programmatically via cfg.set_main_option() (used by
       upgrade_to_head() — this is the authoritative source when Alembic is
       invoked from Python code).
    2. DB_PATH env var (used when running the Alembic CLI directly so operators
       don't need to edit alembic.ini).
    3. Hard-coded production default from alembic.ini.
    """
    url = config.get_main_option("sqlalchemy.url", "").strip()
    if url and url != "sqlite:///":
        return url
    path = os.getenv("DB_PATH", "").strip()
    if path:
        return f"sqlite:///{path}"
    return "sqlite:////data/ratatoskr.db"


def _apply_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def run_migrations_offline() -> None:
    """Run migrations against a URL without a live connection (--sql mode)."""
    url = _get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live connection."""
    url = _get_db_url()
    # NullPool: close connections immediately so SQLite WAL is checkpointed and
    # alembic_version DML is not rolled back by SA 2.x pool-return cleanup.
    connectable = create_engine(url, connect_args={"check_same_thread": False}, poolclass=NullPool)
    event.listen(connectable, "connect", _apply_pragmas)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        # SQLite non-transactional DDL mode: begin_transaction() is a no-op,
        # so DML (alembic_version writes) sits in an autobegin transaction that
        # must be committed explicitly before the connection closes.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
