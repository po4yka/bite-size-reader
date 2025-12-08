import hashlib

import pytest

from app.api.routers import auth
from app.db.database import Database
from app.db.models import User


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "com.example.app")
    auth._cfg = None


def _init_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "test-auth-new.db"))
    db.migrate()
    return db


@pytest.mark.asyncio
async def test_delete_account(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    # Create user
    User.create(telegram_user_id=123456789, username="testuser", is_owner=False)

    # Mock user context from current_user dependency
    user_context = {"user_id": 123456789, "username": "testuser", "client_id": "com.example.app"}

    response = await auth.delete_account(user=user_context)

    assert response["data"]["success"] is True
    assert not User.select().where(User.telegram_user_id == 123456789).exists()


@pytest.mark.asyncio
async def test_apple_login(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    payload = auth.AppleLoginRequest(id_token="apple_test_token", client_id="com.example.app")

    apple_user_id = int(hashlib.sha256(b"apple_test_token").hexdigest(), 16) % 1000000
    assert not User.select().where(User.telegram_user_id == apple_user_id).exists()

    response = await auth.apple_login(payload)

    tokens = response["data"]["tokens"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    assert User.select().where(User.telegram_user_id == apple_user_id).exists()
    user = User.get(User.telegram_user_id == apple_user_id)
    assert user.username == f"apple_{apple_user_id}"


@pytest.mark.asyncio
async def test_google_login(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    payload = auth.GoogleLoginRequest(id_token="google_test_token", client_id="com.example.app")

    google_user_id = int(hashlib.sha256(b"google_test_token").hexdigest(), 16) % 1000000
    assert not User.select().where(User.telegram_user_id == google_user_id).exists()

    response = await auth.google_login(payload)

    tokens = response["data"]["tokens"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    assert User.select().where(User.telegram_user_id == google_user_id).exists()
    user = User.get(User.telegram_user_id == google_user_id)
    assert user.username == f"google_{google_user_id}"
