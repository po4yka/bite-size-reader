import pytest
from fastapi import HTTPException

from app.api.routers import auth
from app.db.database import Database
from app.db.models import ClientSecret, User


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable secret login and reset cached config."""
    monkeypatch.setenv("SECRET_LOGIN_ENABLED", "1")
    monkeypatch.setenv("SECRET_LOGIN_MIN_LENGTH", "12")
    monkeypatch.setenv("SECRET_LOGIN_MAX_LENGTH", "128")
    monkeypatch.setenv("SECRET_LOGIN_MAX_FAILED_ATTEMPTS", "2")
    monkeypatch.setenv("SECRET_LOGIN_LOCKOUT_MINUTES", "1")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "")
    monkeypatch.setenv("API_ID", "1")
    monkeypatch.setenv("API_HASH", "test_api_hash_placeholder_value___")
    monkeypatch.setenv("BOT_TOKEN", "1000000000:TESTTOKENPLACEHOLDER1234567890ABC")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "dummy-firecrawl-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-openrouter-key")
    auth._cfg = None


def _init_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "secret-login.db"))
    db.migrate()
    return db


@pytest.mark.asyncio
async def test_secret_login_success(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    secret_value, record = auth._build_secret_record(
        user,
        "mobile-client",
        provided_secret="secret-value-strong",
        label="primary",
        description=None,
        expires_at=None,
    )

    response = await auth.secret_login(
        auth.SecretLoginRequest(
            user_id=123456789,
            client_id="mobile-client",
            secret=secret_value,
            username="owner",
        )
    )

    tokens = response["data"]["tokens"]
    assert tokens["access_token"]
    assert "session_id" in response["data"]
    assert response["data"]["session_id"] is not None
    reloaded = ClientSecret.get_by_id(record.id)
    assert reloaded.last_used_at is not None
    assert reloaded.failed_attempts == 0
    assert reloaded.status == "active"


@pytest.mark.asyncio
async def test_secret_login_lockout(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    auth._build_secret_record(
        user,
        "mobile-client",
        provided_secret="secret-value-strong",
        label="primary",
        description=None,
        expires_at=None,
    )

    bad_request = auth.SecretLoginRequest(
        user_id=123456789, client_id="mobile-client", secret="wrong-secret", username="owner"
    )

    with pytest.raises(HTTPException):
        await auth.secret_login(bad_request)
    with pytest.raises(HTTPException):
        await auth.secret_login(bad_request)

    record = ClientSecret.select().first()
    assert record.status == "locked"
    assert record.failed_attempts >= 2
    assert record.locked_until is not None


@pytest.mark.asyncio
async def test_secret_key_management(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    owner = User.create(telegram_user_id=123456789, username="owner", is_owner=True)

    create_payload = auth.SecretKeyCreateRequest(
        user_id=owner.telegram_user_id,
        client_id="mobile-client",
        label="primary",
        description="first key",
        expires_at=None,
        secret="management-secret-strong",
        username="owner",
    )

    owner_context = {"user_id": owner.telegram_user_id, "client_id": "admin", "username": "owner"}

    create_resp = await auth.create_secret_key(create_payload, user=owner_context)
    key = create_resp["data"]["key"]
    assert key["client_id"] == "mobile-client"
    assert key["status"] == "active"

    rotate_payload = auth.SecretKeyRotateRequest(secret="rotated-secret-value")
    rotate_resp = await auth.rotate_secret_key(key["id"], rotate_payload, user=owner_context)
    rotated_secret = rotate_resp["data"]["secret"]
    assert rotated_secret == "rotated-secret-value"

    revoke_resp = await auth.revoke_secret_key(
        key["id"], auth.SecretKeyRevokeRequest(reason="cleanup"), user=owner_context
    )
    revoked_key = revoke_resp["data"]["key"]
    assert revoked_key["status"] == "revoked"

    list_resp = await auth.list_secret_keys(user=owner_context)
    assert len(list_resp["data"]["keys"]) == 1
