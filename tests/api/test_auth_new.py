from unittest.mock import patch

import pytest

from app.api.models.auth import AppleLoginRequest, GoogleLoginRequest
from app.api.routers.auth import endpoints as auth_endpoints, oauth as auth_oauth, secret_auth
from app.db.database import Database
from app.db.models import User


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "com.example.app")
    secret_auth._cfg = None


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

    response = await auth_endpoints.delete_account(user=user_context)

    assert response["data"]["success"] is True
    assert not User.select().where(User.telegram_user_id == 123456789).exists()


@pytest.mark.asyncio
async def test_apple_login(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    # Mock verify_apple_id_token to return fake claims
    fake_apple_sub = "test_apple_sub_123"
    mock_claims = {"sub": fake_apple_sub, "email": "test@example.com"}

    with patch.object(auth_endpoints, "verify_apple_id_token", return_value=mock_claims):
        payload = AppleLoginRequest(id_token="apple_test_token", client_id="com.example.app")

        # Calculate expected user_id using the same derivation as the code
        apple_user_id = auth_oauth.derive_user_id_from_sub("apple", fake_apple_sub)

        # Allow this user ID in whitelist
        monkeypatch.setenv("ALLOWED_USER_IDS", f"123456789,{apple_user_id}")
        secret_auth._cfg = None

        assert not User.select().where(User.telegram_user_id == apple_user_id).exists()

        response = await auth_endpoints.apple_login(payload)

        tokens = response["data"]["tokens"]
        # Response uses camelCase (Pydantic alias)
        assert tokens["accessToken"]
        assert tokens["refreshToken"]

        assert User.select().where(User.telegram_user_id == apple_user_id).exists()
        user = User.get(User.telegram_user_id == apple_user_id)
        assert user.username == "test@example.com"


@pytest.mark.asyncio
async def test_google_login(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    # Mock verify_google_id_token to return fake claims
    fake_google_sub = "test_google_sub_456"
    mock_claims = {"sub": fake_google_sub, "email": "user@gmail.com", "name": "Test User"}

    with patch.object(auth_endpoints, "verify_google_id_token", return_value=mock_claims):
        payload = GoogleLoginRequest(id_token="google_test_token", client_id="com.example.app")

        # Calculate expected user_id using the same derivation as the code
        google_user_id = auth_oauth.derive_user_id_from_sub("google", fake_google_sub)

        # Allow this user ID in whitelist
        monkeypatch.setenv("ALLOWED_USER_IDS", f"123456789,{google_user_id}")
        secret_auth._cfg = None

        assert not User.select().where(User.telegram_user_id == google_user_id).exists()

        response = await auth_endpoints.google_login(payload)

        tokens = response["data"]["tokens"]
        # Response uses camelCase (Pydantic alias)
        assert tokens["accessToken"]
        assert tokens["refreshToken"]

        assert User.select().where(User.telegram_user_id == google_user_id).exists()
        user = User.get(User.telegram_user_id == google_user_id)
        assert user.username == "Test User"
