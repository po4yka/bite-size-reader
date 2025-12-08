import logging
import sys
from unittest.mock import MagicMock

import pytest

from app.db.database import Database
from app.db.models import Request, Summary, User

# Mock chromadb to avoid Pydantic V2 compatibility issues in tests
sys.modules["chromadb"] = MagicMock()
sys.modules["chromadb.config"] = MagicMock()
sys.modules["chromadb.errors"] = MagicMock()

logger = logging.getLogger("peewee")
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.WARNING)


@pytest.fixture
def db(tmp_path, monkeypatch):
    # Set config to avoid production DB usage
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-at-least-32-chars-long-string")

    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    database.migrate()

    yield database
    database._database.close()


@pytest.fixture
def client(db):
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        # Fallback if specific test env issues, but should not happen now
        from starlette.testclient import TestClient

    from app.api.main import app

    return TestClient(app)


@pytest.fixture
def user_factory():
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
        req = Request.create(
            user_id=user.telegram_user_id,
            input_url=f"http://test{rand_id}.com",
            status="completed",
            type="url",
        )

        # Defaults
        params = {
            "request": req.id,
            "lang": "en",
            "is_read": False,
            "version": 1,
            "json_payload": None,
        }
        params.update(kwargs)

        return Summary.create(**params)

    return create_summary
