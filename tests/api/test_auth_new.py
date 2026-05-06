import time
from unittest.mock import MagicMock, patch

import pytest

import app.di.database as _di_database
from app.api.dependencies.database import clear_session_manager
from app.api.models.auth import TelegramLoginRequest
from app.api.routers.auth import (
    endpoints_me as auth_endpoints_me,
    endpoints_telegram as auth_endpoints_telegram,
    secret_auth,
)
from app.cli._legacy_peewee_models import User, database_proxy
try:
    from app.db.session import DatabaseSessionManager  # type: ignore[attr-defined]
except ImportError:
    DatabaseSessionManager = None  # type: ignore[assignment,misc]


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "com.example.app")
    secret_auth._cfg = None


def _init_db(tmp_path) -> DatabaseSessionManager:
    clear_session_manager()
    db = DatabaseSessionManager(str(tmp_path / "test-auth-new.db"))
    db.migrate()
    database_proxy.initialize(db._database)
    _di_database._cached_runtime_db = db
    return db


@pytest.mark.asyncio
async def test_delete_account(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    # Create user
    User.create(telegram_user_id=123456789, username="testuser", is_owner=False)

    # Mock user context from current_user dependency
    user_context = {"user_id": 123456789, "username": "testuser", "client_id": "com.example.app"}

    response = await auth_endpoints_me.delete_account(
        user=user_context, x_confirm_delete="DELETE-MY-ACCOUNT"
    )

    assert response["data"]["success"] is True
    assert not User.select().where(User.telegram_user_id == 123456789).exists()


@pytest.mark.asyncio
async def test_telegram_login_does_not_auto_grant_owner(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    payload = TelegramLoginRequest(
        id=123456789,
        hash="test-hash",
        auth_date=int(time.time()),
        username="testuser",
        client_id="com.example.app",
    )

    with patch.object(auth_endpoints_telegram, "verify_telegram_auth", return_value=True):
        response = await auth_endpoints_telegram.telegram_login(payload, MagicMock())

    tokens = response["data"]["tokens"]
    assert tokens["accessToken"]
    assert tokens["refreshToken"]

    user = User.get(User.telegram_user_id == 123456789)
    assert user.is_owner is False
