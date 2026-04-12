from unittest.mock import MagicMock

import pytest

import app.di.database as _di_database
from app.api.dependencies.database import clear_session_manager
from app.api.exceptions import AuthenticationError, AuthorizationError
from app.api.models.auth import (
    SecretKeyCreateRequest,
    SecretKeyRevokeRequest,
    SecretKeyRotateRequest,
    SecretLoginRequest,
)
from app.api.routers.auth import endpoints as auth_endpoints, secret_auth
from app.db.models import ClientSecret, User, database_proxy
from app.db.session import DatabaseSessionManager


def _mock_response() -> MagicMock:
    """Create a mock starlette Response for cookie-setting endpoints."""
    return MagicMock()


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
    secret_auth._cfg = None


def _init_db(tmp_path) -> DatabaseSessionManager:
    clear_session_manager()
    db = DatabaseSessionManager(str(tmp_path / "secret-login.db"))
    db.migrate()
    database_proxy.initialize(db._database)
    _di_database._cached_runtime_db = db
    return db


@pytest.mark.asyncio
async def test_secret_login_success(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    # build_secret_record is now async and takes user_id (int) not user object
    secret_value, record = await secret_auth.build_secret_record(
        user.telegram_user_id,
        "mobile-client",
        provided_secret="secret-value-strong",
        label="primary",
        description=None,
        expires_at=None,
    )

    response = await auth_endpoints.secret_login(
        SecretLoginRequest(
            user_id=123456789,
            client_id="mobile-client",
            secret=secret_value,
            username="owner",
        ),
        _mock_response(),
    )

    tokens = response["data"]["tokens"]
    # Response uses camelCase (Pydantic alias)
    assert tokens["accessToken"]
    assert "sessionId" in response["data"]
    assert response["data"]["sessionId"] is not None
    reloaded = ClientSecret.get_by_id(record["id"])
    assert reloaded.last_used_at is not None
    assert reloaded.failed_attempts == 0
    assert reloaded.status == "active"


@pytest.mark.asyncio
async def test_secret_login_lockout(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    # build_secret_record is now async and takes user_id (int) not user object
    await secret_auth.build_secret_record(
        user.telegram_user_id,
        "mobile-client",
        provided_secret="secret-value-strong",
        label="primary",
        description=None,
        expires_at=None,
    )

    bad_request = SecretLoginRequest(
        user_id=123456789, client_id="mobile-client", secret="wrong-secret-12", username="owner"
    )

    # First failed attempt should raise AuthenticationError
    with pytest.raises(AuthenticationError):
        await auth_endpoints.secret_login(bad_request, _mock_response())

    # Second failed attempt should also raise AuthenticationError
    # (the lockout happens after enough failures)
    with pytest.raises((AuthenticationError, AuthorizationError)):
        await auth_endpoints.secret_login(bad_request, _mock_response())

    record = ClientSecret.select().first()
    assert record.status == "locked"
    assert record.failed_attempts >= 2
    assert record.locked_until is not None


@pytest.mark.asyncio
async def test_secret_key_management(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    owner = User.create(telegram_user_id=123456789, username="owner", is_owner=True)

    create_payload = SecretKeyCreateRequest(
        user_id=owner.telegram_user_id,
        client_id="mobile-client",
        label="primary",
        description="first key",
        expires_at=None,
        secret="management-secret-strong",
        username="owner",
    )

    owner_context = {"user_id": owner.telegram_user_id, "client_id": "admin", "username": "owner"}

    create_resp = await auth_endpoints.create_secret_key(create_payload, user=owner_context)
    key = create_resp["data"]["key"]
    assert key["client_id"] == "mobile-client"
    assert key["status"] == "active"

    rotate_payload = SecretKeyRotateRequest(secret="rotated-secret-value")
    rotate_resp = await auth_endpoints.rotate_secret_key(
        key["id"], rotate_payload, user=owner_context
    )
    rotated_secret = rotate_resp["data"]["secret"]
    assert rotated_secret == "rotated-secret-value"

    revoke_resp = await auth_endpoints.revoke_secret_key(
        key["id"], SecretKeyRevokeRequest(reason="cleanup"), user=owner_context
    )
    revoked_key = revoke_resp["data"]["key"]
    assert revoked_key["status"] == "revoked"

    list_resp = await auth_endpoints.list_secret_keys(user=owner_context)
    assert len(list_resp["data"]["keys"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("client_id", ["cli-client", "mcp-client", "automation-client"])
async def test_self_service_secret_key_management_round_trip_for_supported_client_types(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    client_id: str,
):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=222222222, username="regular-user", is_owner=False)
    user_context = {"user_id": user.telegram_user_id, "client_id": client_id, "username": "regular"}

    create_payload = SecretKeyCreateRequest(
        user_id=user.telegram_user_id,
        client_id=client_id,
        label="self-service",
        description="secondary key",
        expires_at=None,
        secret="self-service-secret-strong",
        username="regular-user",
    )

    create_resp = await auth_endpoints.create_secret_key(create_payload, user=user_context)
    created_key = create_resp["data"]["key"]
    assert created_key["user_id"] == user.telegram_user_id
    assert created_key["client_id"] == client_id
    assert created_key["status"] == "active"

    list_resp = await auth_endpoints.list_secret_keys(user=user_context)
    assert [key["id"] for key in list_resp["data"]["keys"]] == [created_key["id"]]

    rotate_resp = await auth_endpoints.rotate_secret_key(
        created_key["id"],
        SecretKeyRotateRequest(secret="rotated-secret-value"),
        user=user_context,
    )
    assert rotate_resp["data"]["secret"] == "rotated-secret-value"

    revoke_resp = await auth_endpoints.revoke_secret_key(
        created_key["id"],
        SecretKeyRevokeRequest(reason="cleanup"),
        user=user_context,
    )
    revoked_key = revoke_resp["data"]["key"]
    assert revoked_key["status"] == "revoked"

    with pytest.raises(AuthenticationError, match="Only active secrets can be rotated"):
        await auth_endpoints.rotate_secret_key(
            created_key["id"],
            SecretKeyRotateRequest(secret="another-rotated-secret"),
            user=user_context,
        )

    second_revoke_resp = await auth_endpoints.revoke_secret_key(
        created_key["id"],
        SecretKeyRevokeRequest(reason="cleanup-again"),
        user=user_context,
    )
    assert second_revoke_resp["data"]["key"]["status"] == "revoked"

    reloaded = ClientSecret.get_by_id(created_key["id"])
    assert reloaded.status == "revoked"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_user_id", "client_id"),
    [
        (222222222, "mobile-client"),
        (333333333, "cli-client"),
    ],
)
async def test_self_service_secret_key_management_rejects_invalid_scope(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    payload_user_id: int,
    client_id: str,
):
    _configure_env(monkeypatch)
    _db = _init_db(tmp_path)

    user = User.create(telegram_user_id=222222222, username="regular-user", is_owner=False)
    user_context = {
        "user_id": user.telegram_user_id,
        "client_id": "cli-client",
        "username": "regular",
    }

    create_payload = SecretKeyCreateRequest(
        user_id=payload_user_id,
        client_id=client_id,
        label="self-service",
        description=None,
        expires_at=None,
        secret="self-service-secret-strong",
        username="regular-user",
    )

    with pytest.raises(AuthorizationError):
        await auth_endpoints.create_secret_key(create_payload, user=user_context)


@pytest.mark.asyncio
async def test_secret_key_creation_does_not_promote_target_to_owner(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _configure_env(monkeypatch)
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789,222222222")
    secret_auth._cfg = None
    _db = _init_db(tmp_path)

    owner = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    owner_context = {"user_id": owner.telegram_user_id, "client_id": "admin", "username": "owner"}

    create_payload = SecretKeyCreateRequest(
        user_id=222222222,
        client_id="mobile-client",
        label="target-user-key",
        description=None,
        expires_at=None,
        secret="target-user-secret-strong",
        username="target-user",
    )

    create_resp = await auth_endpoints.create_secret_key(create_payload, user=owner_context)
    assert create_resp["data"]["key"]["client_id"] == "mobile-client"

    target_user = User.get(User.telegram_user_id == 222222222)
    assert target_user.is_owner is False
