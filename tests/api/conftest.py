import importlib
import logging
import sys
from unittest.mock import MagicMock

import pytest

from app.db.database import Database
from app.db.models import Request, Summary, User, database_proxy

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

    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    database.migrate()

    # Explicitly ensure database_proxy points to this test database
    # This is needed because previous tests or imports may have changed it
    database_proxy.initialize(database._database)

    yield database

    # Close and restore the original database_proxy
    database._database.close()
    database_proxy.initialize(old_proxy_obj)


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
