"""SQLAlchemy async database session management."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from app.config.database import DatabaseConfig

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

_RETRYABLE_SQLSTATES = {"40001", "40P01"}


@dataclass(slots=True)
class Database:
    """Async SQLAlchemy database facade for bot, CLI, and FastAPI callers."""

    config: DatabaseConfig
    _engine: AsyncEngine = field(init=False, repr=False)
    _session_maker: async_sessionmaker[AsyncSession] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._engine = create_async_engine(
            self.config.dsn,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_pre_ping=True,
            pool_recycle=self.config.pool_recycle_seconds,
        )
        self._session_maker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        return self._session_maker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session without starting an implicit transaction block."""
        async with self._session_maker() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Yield a session inside a transaction, committing only on success."""
        async with self._session_maker() as session, session.begin():
            yield session

    async def healthcheck(self) -> None:
        async with self.session() as session:
            await session.execute(text("SELECT 1"))

    async def migrate(self) -> None:
        """Run Alembic migrations for the configured database.

        Alembic's command API is synchronous; it is isolated in a worker thread until
        the migration environment is converted to SQLAlchemy async in O5.
        """
        await asyncio.to_thread(_run_alembic_upgrade, self.config.dsn)

    async def dispose(self) -> None:
        await self._engine.dispose()


@asynccontextmanager
async def get_session(database: Database) -> AsyncIterator[AsyncSession]:
    """Open a short-lived bot/CLI session."""
    async with database.session() as session:
        yield session


async def get_session_for_request(database: Database) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that wraps each request in one transaction."""
    async with database.transaction() as session:
        yield session


def _sqlstate(exc: OperationalError) -> str | None:
    original = exc.orig
    for attr_name in ("sqlstate", "pgcode"):
        value = getattr(original, attr_name, None)
        if value:
            return str(value)
    return None


def _is_retryable_serialization_error(exc: OperationalError) -> bool:
    return _sqlstate(exc) in _RETRYABLE_SQLSTATES


def _run_alembic_upgrade(dsn: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(cfg, "head")


def with_serialization_retry(
    func: Callable[P, Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.05,
) -> Callable[P, Awaitable[T]]:
    """Retry an async operation on Postgres serialization/deadlock failures."""

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        last_error: OperationalError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await func(*args, **kwargs)
            except OperationalError as exc:
                if not _is_retryable_serialization_error(exc) or attempt >= attempts:
                    raise
                last_error = exc
                delay = base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "db_serialization_retry",
                    extra={"attempt": attempt, "sqlstate": _sqlstate(exc), "delay": delay},
                )
                await asyncio.sleep(delay)
        if last_error is not None:  # pragma: no cover - loop exits by raise/return.
            raise last_error
        msg = "with_serialization_retry requires at least one attempt"
        raise ValueError(msg)

    return wrapper
