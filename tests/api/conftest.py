"""API test fixtures: async Database, FastAPI TestClient, factories.

Replaces the legacy DatabaseSessionManager + database_proxy wiring with
the async SQLAlchemy port. Each `db`-using test gets a freshly-truncated
Postgres registered as the runtime cache so FastAPI dependencies pick
it up.
"""

from __future__ import annotations

import importlib
import logging
import os
from enum import Enum
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

# All API tests require optional 'api' extras (fastapi, pyjwt, starlette).
# Skip the entire directory when these are not installed.
pytest.importorskip("jwt", reason="PyJWT not installed (install with: pip install .[api])")
pytest.importorskip("fastapi", reason="FastAPI not installed (install with: pip install .[api])")


class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""


class _NotRequiredMeta(type):
    def __getitem__(cls, item: Any) -> Any:
        return item


class NotRequired(metaclass=_NotRequiredMeta):
    """Compatibility shim for NotRequired (Python 3.11+)."""


import app.di.database as _di_database
from app.api.dependencies.database import clear_session_manager
from app.config.database import DatabaseConfig
from app.db.base import Base
from app.db.models import Request, Summary, User

if TYPE_CHECKING:
    from app.db.session import Database

logger = logging.getLogger("test.api")


async def _truncate_all_tables(database: Database) -> None:
    """Async helper: TRUNCATE every model table to reset DB state."""
    from sqlalchemy import text as sql_text

    table_names = [t.name for t in reversed(Base.metadata.sorted_tables)]
    if not table_names:
        return
    quoted = ", ".join(f'"{name}"' for name in table_names)
    async with database.transaction() as cleanup:
        await cleanup.execute(sql_text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db(monkeypatch):
    """Provide a freshly-truncated async Database, registered as the runtime cache.

    Function-scoped + async so the asyncpg pool is bound to the same
    event loop the test runs on (pytest-asyncio in `auto` mode creates
    a fresh loop per test). Skips when TEST_DATABASE_URL is unset so
    unit-only runs do not require Postgres.
    """
    from app.db.session import Database

    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for API tests against Postgres")

    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-at-least-32-chars-long-string")
    monkeypatch.setenv("REDIS_ENABLED", "0")
    monkeypatch.setenv("DATABASE_URL", dsn)

    clear_session_manager()

    database = Database(config=DatabaseConfig(dsn=dsn, pool_size=2, max_overflow=2))
    await database.migrate()
    await _truncate_all_tables(database)

    # Register as the runtime cache so FastAPI dependencies (and any
    # internal `get_or_create_runtime_database_from_env()` lookup) use it.
    _di_database._cached_runtime_db = database

    try:
        yield database
    finally:
        _di_database._cached_runtime_db = None
        clear_session_manager()
        await database.dispose()


@pytest.fixture(autouse=True)
def collection_service():
    """Configure CollectionService repo factory for every API test.

    Wires up the module-level repo factory so any router/service path that
    reaches into ``CollectionService`` finds a factory. The factory itself
    resolves the active session manager lazily, so this fixture
    intentionally does *not* depend on the ``db`` fixture -- forcing
    ``db`` here would change the env-var setup order for tests that
    bring their own database (e.g., ``tests/api/test_secret_login.py``).
    """
    from app.api.dependencies.database import get_collection_repository
    from app.api.services.collection_service import CollectionService

    CollectionService.configure(get_collection_repository)
    return CollectionService


@pytest.fixture
def client(db):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        from starlette.testclient import TestClient

    import app.api.main

    importlib.reload(app.api.main)
    from app.api.main import app

    # Clear in-memory rate limit state accumulated from previous tests
    try:
        from app.api import middleware as _mw

        _mw._local_rate_limits.clear()
    except Exception:  # pragma: no cover
        pass

    return TestClient(app)


@pytest.fixture
def user_factory(db: Database):
    """Async factory for creating test users.

    Returns a coroutine: tests should `await user_factory(...)`. The legacy
    sync version (`user_factory()` returns User) only worked because the
    Peewee proxy was bound to a sync sqlite connection. With the async
    SQLAlchemy port the factory must run in the test's event loop.
    """
    import random

    async def create_user(
        username: str = "testuser",
        telegram_user_id: int | None = None,
        **kwargs: Any,
    ) -> User:
        if telegram_user_id is None:
            telegram_user_id = random.randint(1, 1_000_000)
        async with db.transaction() as session:
            from sqlalchemy import select

            existing = await session.scalar(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
            if existing is not None:
                return existing
            user = User(telegram_user_id=telegram_user_id, username=username, **kwargs)
            session.add(user)
            await session.flush()
            return user

    return create_user


@pytest.fixture
def summary_factory(db: Database, user_factory):
    """Async factory for creating test summaries with full payloads.

    Returns a coroutine. Default payload includes every field the API
    response models declare.
    """
    import random

    async def create_summary(user: User | None = None, **kwargs: Any) -> Summary:
        if user is None:
            user = await user_factory()

        full_payload: dict[str, Any] = {
            "summary_250": "Short summary",
            "summary_1000": "Long summary",
            "tldr": "TLDR",
            "key_ideas": ["Idea 1", "Idea 2"],
            "topic_tags": ["tag1", "tag2"],
            "entities": {"people": ["Person"], "organizations": ["Org"], "locations": ["Loc"]},
            "estimated_reading_time_min": 5,
            "key_stats": [{"label": "Stat", "value": 10, "unit": "%", "sourceExcerpt": "source"}],
            "answered_questions": ["Q1?"],
            "readability": {"method": "FK", "score": 50.0, "level": "Easy"},
            "seo_keywords": ["keyword"],
            "metadata": {
                "title": "Test Title",
                "domain": "example.com",
                "author": "Author",
                "published_at": "2023-01-01",
            },
            "confidence": 0.9,
            "hallucination_risk": "low",
        }

        if kwargs.get("json_payload"):
            full_payload.update(kwargs["json_payload"])
        kwargs["json_payload"] = full_payload

        params: dict[str, Any] = {
            "lang": "en",
            "is_read": False,
            "version": 1,
        }
        params.update(kwargs)

        async with db.transaction() as session:
            rand_id = random.randint(1, 100_000)
            url = f"http://test{rand_id}.com"
            request = Request(
                user_id=user.telegram_user_id,
                input_url=url,
                normalized_url=url,
                status="completed",
                type="url",
            )
            session.add(request)
            await session.flush()
            summary_kwargs: dict[str, Any] = dict(params)
            summary_kwargs["request_id"] = request.id
            summary = Summary(**summary_kwargs)
            session.add(summary)
            await session.flush()
            return summary

    return create_summary
