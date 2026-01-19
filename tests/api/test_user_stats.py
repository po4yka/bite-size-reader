"""Tests for user stats endpoint with ensure_mapping safety."""

import sys
from unittest.mock import MagicMock

import pytest

# Mock redis before any app imports
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()

from app.api.routers import auth
from app.db.database import Database
from app.db.models import Request, Summary, User, database_proxy


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "com.example.app")
    auth._cfg = None


@pytest.fixture
def user_stats_db(tmp_path):
    """Create an isolated test database with proper database_proxy handling."""
    # Save the original database proxy state
    old_proxy_obj = database_proxy.obj

    db = Database(str(tmp_path / "test-user-stats.db"))
    db.migrate()
    # Initialize the global database proxy so models use this database
    database_proxy.initialize(db._database)

    yield db

    # Close the database and restore original proxy
    db._database.close()
    database_proxy.initialize(old_proxy_obj)


@pytest.mark.asyncio
async def test_user_stats_with_valid_json_payload(user_stats_db, monkeypatch: pytest.MonkeyPatch):
    """Test user stats with properly formatted json_payload."""
    _configure_env(monkeypatch)

    # Create user and summary with valid json_payload
    user = User.create(telegram_user_id=123456789, username="testuser")
    request = Request.create(
        user_id=user.telegram_user_id,
        input_url="http://test.com",
        status="completed",
        type="url",
    )
    Summary.create(
        request=request.id,
        lang="en",
        json_payload={
            "estimated_reading_time_min": 5,
            "topic_tags": ["tech", "ai"],
            "metadata": {"title": "Test Article", "domain": "test.com"},
        },
    )

    from app.api.routers.user import get_user_stats

    user_context = {"user_id": 123456789}
    response = await get_user_stats(user=user_context)

    # Response uses camelCase (Pydantic alias)
    assert response["data"]["totalSummaries"] == 1
    assert response["data"]["totalReadingTimeMin"] == 5


@pytest.mark.asyncio
async def test_user_stats_with_none_json_payload(user_stats_db, monkeypatch: pytest.MonkeyPatch):
    """Test user stats handles None json_payload gracefully."""
    _configure_env(monkeypatch)

    user = User.create(telegram_user_id=123456790, username="testuser2")
    request = Request.create(
        user_id=user.telegram_user_id,
        input_url="http://test2.com",
        status="completed",
        type="url",
    )
    Summary.create(
        request=request.id,
        lang="en",
        json_payload=None,  # None payload
    )

    from app.api.routers.user import get_user_stats

    user_context = {"user_id": 123456790}
    response = await get_user_stats(user=user_context)

    # Response uses camelCase (Pydantic alias)
    assert response["data"]["totalSummaries"] == 1
    assert response["data"]["totalReadingTimeMin"] == 0


@pytest.mark.asyncio
async def test_user_stats_with_string_json_payload(user_stats_db, monkeypatch: pytest.MonkeyPatch):
    """Test user stats handles string json_payload (legacy data) gracefully."""
    _configure_env(monkeypatch)
    db = user_stats_db

    user = User.create(telegram_user_id=123456791, username="testuser3")
    request = Request.create(
        user_id=user.telegram_user_id,
        input_url="http://test3.com",
        status="completed",
        type="url",
    )
    summary = Summary.create(
        request=request.id,
        lang="en",
        json_payload={},  # Create with empty dict first
    )

    # Manually set json_payload to a JSON string to simulate legacy data
    db._database.execute_sql(
        "UPDATE summaries SET json_payload = ? WHERE id = ?",
        ('{"estimated_reading_time_min": 10, "topic_tags": ["python"]}', summary.id),
    )

    from app.api.routers.user import get_user_stats

    user_context = {"user_id": 123456791}
    # This should not raise an error - ensure_mapping handles string JSON
    response = await get_user_stats(user=user_context)

    # Response uses camelCase (Pydantic alias)
    assert response["data"]["totalSummaries"] == 1


@pytest.mark.asyncio
async def test_user_stats_with_invalid_topic_tags(user_stats_db, monkeypatch: pytest.MonkeyPatch):
    """Test user stats handles invalid topic_tags type gracefully."""
    _configure_env(monkeypatch)

    user = User.create(telegram_user_id=123456792, username="testuser4")
    request = Request.create(
        user_id=user.telegram_user_id,
        input_url="http://test4.com",
        status="completed",
        type="url",
    )
    Summary.create(
        request=request.id,
        lang="en",
        json_payload={
            "estimated_reading_time_min": 3,
            "topic_tags": "not-a-list",  # Invalid: should be list
            "metadata": {"title": "Test"},
        },
    )

    from app.api.routers.user import get_user_stats

    user_context = {"user_id": 123456792}
    # Should not raise - isinstance check handles this
    response = await get_user_stats(user=user_context)

    # Response uses camelCase (Pydantic alias)
    assert response["data"]["totalSummaries"] == 1
    assert response["data"]["favoriteTopics"] == []  # No valid tags
