import importlib
import logging
import sys
from enum import Enum
from typing import Any
from unittest.mock import MagicMock

import pytest

# All API tests require optional 'api' extras (fastapi, pyjwt, starlette).
# Skip the entire directory when these are not installed.
pytest.importorskip("jwt", reason="PyJWT not installed (install with: pip install .[api])")
pytest.importorskip("fastapi", reason="FastAPI not installed (install with: pip install .[api])")


# Python 3.10 compatibility shims (must be before app imports)
class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""


class _NotRequiredMeta(type):
    def __getitem__(cls, item: Any) -> Any:
        return item


class NotRequired(metaclass=_NotRequiredMeta):
    """Compatibility shim for NotRequired (Python 3.11+)."""


# Note: These shims are also set up in tests/conftest.py (root)
# No need to set them up again here as conftest.py is loaded first

import app.di.database as _di_database
from app.api.dependencies.database import clear_session_manager
from app.db.models import Request, Summary, User, database_proxy
from app.db.session import DatabaseSessionManager

# Mock chromadb to avoid Pydantic V2 compatibility issues in tests
sys.modules["chromadb"] = MagicMock()
sys.modules["chromadb.config"] = MagicMock()
sys.modules["chromadb.errors"] = MagicMock()

logger = logging.getLogger("peewee")
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.WARNING)


@pytest.fixture
def db(tmp_path, monkeypatch):
    # Save the original database_proxy object to restore later
    old_proxy_obj = database_proxy.obj

    # Set config to avoid production DB usage
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-at-least-32-chars-long-string")
    monkeypatch.setenv("REDIS_ENABLED", "0")  # Disable Redis for tests

    # Clear cached runtime DB so get_session_manager() will use DB_PATH
    clear_session_manager()

    db_path = tmp_path / "test.db"
    database = DatabaseSessionManager(str(db_path))
    database.migrate()

    # Register the test DatabaseSessionManager as the cached runtime DB so
    # resolve_repository_session() returns it instead of the raw peewee proxy.
    _di_database._cached_runtime_db = database

    # Explicitly ensure database_proxy points to this test database
    # This is needed because previous tests or imports may have changed it
    database_proxy.initialize(database._database)

    yield database

    # Restore session and proxy state
    clear_session_manager()
    database._database.close()
    database_proxy.initialize(old_proxy_obj)


@pytest.fixture
def collection_service(db):
    """Configure CollectionService repo factory. Request this fixture in collection tests."""
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

    # Force proxy to point to the migrated database instance from db fixture
    # This fixes OperationalError: no such table when app re-initializes DB
    database_proxy.initialize(db._database)

    # Clear in-memory rate limit state accumulated from previous tests
    try:
        from app.api import middleware as _mw

        _mw._local_rate_limits.clear()
    except Exception:
        pass

    return TestClient(app)


@pytest.fixture
def user_factory(db):
    """Factory for creating test users. Depends on db fixture to ensure database is initialized."""

    def create_user(username="testuser", telegram_user_id=None, **kwargs):
        if telegram_user_id is None:
            import random

            telegram_user_id = random.randint(1, 1000000)

        try:
            return User.get(telegram_user_id=telegram_user_id)
        except Exception as e:
            logger.debug(f"User {telegram_user_id} not found, creating new: {e}")

        return User.create(telegram_user_id=telegram_user_id, username=username, **kwargs)

    return create_user


@pytest.fixture
def summary_factory(user_factory):
    def create_summary(user=None, **kwargs):
        if user is None:
            user = user_factory()

        # Need a Request for Summary
        import random

        rand_id = random.randint(1, 100000)
        url = f"http://test{rand_id}.com"
        req = Request.create(
            user_id=user.telegram_user_id,
            input_url=url,
            normalized_url=url,
            status="completed",
            type="url",
        )

        # Full payload to satisfy API response models
        full_payload = {
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

        # Merge with provided payload if any
        if kwargs.get("json_payload"):
            full_payload.update(kwargs["json_payload"])

        kwargs["json_payload"] = full_payload

        # Defaults
        params = {
            "request": req.id,
            "lang": "en",
            "is_read": False,
            "version": 1,
        }
        params.update(kwargs)

        return Summary.create(**params)

    return create_summary
