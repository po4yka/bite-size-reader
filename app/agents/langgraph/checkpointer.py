"""Async context manager for LangGraph's Postgres checkpointer.

Usage (in bot startup or FastAPI lifespan)::

    from app.agents.langgraph.checkpointer import create_checkpointer

    async with create_checkpointer(settings.DATABASE_URL) as checkpointer:
        graph = SummarizationGraph(..., checkpointer=checkpointer)
        ...

The checkpointer uses psycopg3 (``psycopg[binary]``), which is a separate
driver from the asyncpg pool used by SQLAlchemy. Both coexist without conflict
but count against the Postgres ``max_connections`` budget — size each pool
accordingly (default psycopg3 pool: min=1, max=10).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from app.core.logging_utils import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def create_checkpointer(connection_string: str) -> AsyncIterator:
    """Yield a ready-to-use ``AsyncPostgresSaver``.

    Calls ``checkpointer.setup()`` on entry (idempotent — creates four tables
    the first time, is a no-op on subsequent calls).  The psycopg3 connection
    pool is closed on context exit.

    Args:
        connection_string: PostgreSQL DSN accepted by psycopg3, e.g.
            ``postgresql://user:pass@host/db`` or the asyncpg-style
            ``postgresql+asyncpg://…`` after stripping the driver suffix.

    Raises:
        ImportError: If ``langgraph-checkpoint-postgres`` or ``psycopg`` are
            not installed.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise ImportError(
            "Postgres checkpointing requires langgraph-checkpoint-postgres and psycopg. "
            "Install them with: pip install langgraph-checkpoint-postgres 'psycopg[binary]'"
        ) from exc

    # psycopg3 does not understand the SQLAlchemy driver prefix
    dsn = connection_string.replace("postgresql+asyncpg://", "postgresql://")

    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        await checkpointer.setup()
        logger.info("[LangGraph] Postgres checkpointer initialised")
        yield checkpointer
        logger.info("[LangGraph] Postgres checkpointer closed")
