"""MCP-specific pytest plugin: provides the `mcp_test_db` fixture.

Several MCP-targeted test modules declare this module as a `pytest_plugins`
entry. The legacy version of this file built a sqlite DatabaseSessionManager
and pinned the peewee `database_proxy` at it; the async port exposes a
`Database` (the new SQLAlchemy entry point) backed by `TEST_DATABASE_URL`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest_asyncio

from app.config.database import DatabaseConfig

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.db.session import Database


@pytest_asyncio.fixture
async def mcp_test_db() -> AsyncGenerator[Database]:
    """Function-scoped async `Database` for MCP tests.

    Pytest function-scoping is required because pytest-asyncio in `auto`
    mode runs each test on a fresh event loop -- an asyncpg pool bound
    to a previous loop fails with "attached to a different loop".

    Truncates every table before yielding so each test starts from a
    known empty state, mirroring the behaviour of the conftest-level
    `session` fixture.
    """
    import pytest

    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for MCP tests")

    from sqlalchemy import text as sql_text

    from app.db.base import Base
    from app.db.session import Database

    db = Database(config=DatabaseConfig(dsn=dsn, pool_size=2, max_overflow=2))
    await db.migrate()

    table_names = [t.name for t in reversed(Base.metadata.sorted_tables)]
    if table_names:
        quoted = ", ".join(f'"{name}"' for name in table_names)
        async with db.transaction() as cleanup:
            await cleanup.execute(
                sql_text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
            )

    try:
        yield db
    finally:
        await db.dispose()
