from datetime import datetime, timedelta

import pytest

from app.api.routers.auth.tokens import create_access_token, create_refresh_token
from app.core.time_utils import UTC
from app.db.models import RefreshToken, User


@pytest.fixture
def clean_db(db):
    # Ensure fresh start
    RefreshToken.delete().execute()
    User.delete().execute()
    return db


@pytest.fixture
def auth_user(db):
    return User.create(telegram_user_id=123456789, username="test_auth")


@pytest.mark.asyncio
async def test_create_refresh_token_persists(auth_user):
    token, session_id = await create_refresh_token(
        user_id=auth_user.telegram_user_id,
        client_id="test-client",
        device_info="TestDevice",
        ip_address="127.0.0.1",
    )

    assert token is not None
    assert session_id is not None
    assert RefreshToken.select().count() == 1

    record = RefreshToken.select().first()
    assert record.user == auth_user
    assert record.client_id == "test-client"
    assert record.device_info == "TestDevice"
    assert record.ip_address == "127.0.0.1"
    assert not record.is_revoked


@pytest.mark.asyncio
async def test_logout_revokes_token(client, auth_user):
    # Create persistent token manually via helper (now async)
    token, _ = await create_refresh_token(auth_user.telegram_user_id, "mobile-app")

    access_token = create_access_token(auth_user.telegram_user_id, client_id="mobile-app")

    # Call logout
    response = client.post(
        "/v1/auth/logout",
        json={"refresh_token": token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert "Logged out" in response.json()["data"]["message"]

    # Verify DB
    record = RefreshToken.select().first()
    assert record.is_revoked is True


@pytest.mark.asyncio
async def test_list_sessions(client, auth_user):
    # Create 3 sessions (now async)
    # 1. Active
    await create_refresh_token(auth_user.telegram_user_id, "client-1", device_info="Device 1")
    # 2. Revoked
    await create_refresh_token(auth_user.telegram_user_id, "client-2", device_info="Device 2")
    r2 = RefreshToken.get(RefreshToken.client_id == "client-2")
    r2.is_revoked = True
    r2.save()
    # 3. Expired (manually manipulate)
    await create_refresh_token(auth_user.telegram_user_id, "client-3", device_info="Device 3")
    r3 = RefreshToken.get(RefreshToken.client_id == "client-3")
    r3.expires_at = datetime.now(UTC) - timedelta(days=1)
    r3.save()

    # 4. Another user's session
    other = User.create(telegram_user_id=67890)
    await create_refresh_token(other.telegram_user_id, "other-client")

    # Get sessions
    access_token = create_access_token(auth_user.telegram_user_id, client_id="client-1")

    response = client.get("/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    sessions = response.json()["data"]["sessions"]

    # Should only see session 1
    assert len(sessions) == 1
    assert sessions[0]["clientId"] == "client-1"
    assert sessions[0]["deviceInfo"] == "Device 1"


# ----- Refresh-token rotation regression tests -------------------------------
#
# The 3 tests above were written against the old peewee ORM (User.create(),
# RefreshToken.select(), .save()) and now error at fixture setup since the
# project moved to SQLAlchemy 2.0. These new tests use the modern db /
# user_factory / client fixtures from tests/api/conftest.py.
#
# Test contract: POST /v1/auth/refresh MUST issue a new refresh token AND
# revoke the previous one. Without this, an attacker who steals a single
# refresh token could keep refreshing indefinitely. A revoked token replayed
# against /refresh MUST trigger reuse detection and revoke ALL of that user's
# refresh tokens (defense in depth — assume the original was stolen).


import hashlib
from unittest.mock import MagicMock

from sqlalchemy import select as sa_select

from app.api.dependencies.database import get_auth_repository
from app.api.exceptions import TokenRevokedError
from app.api.models.auth import RefreshTokenRequest
from app.api.routers.auth.endpoints_sessions import (
    refresh_access_token,
)
from app.db.models import RefreshToken as RefreshTokenModel


def _mock_request_response() -> tuple[MagicMock, MagicMock]:
    """Build the minimal Request/Response stubs the refresh handler needs.

    The handler reads `request.cookies.get(...)` (we send the token in the
    request body, so cookies stay empty) and calls `clear_refresh_cookie` /
    `set_refresh_cookie` on the response — MagicMock absorbs both.
    """
    request = MagicMock()
    request.cookies = {}
    return request, MagicMock()


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token_and_revokes_previous(db, user_factory):
    import asyncio

    user = await user_factory(telegram_user_id=987654321, username="rotator")

    old_token, _ = await create_refresh_token(
        user_id=user.telegram_user_id,
        client_id="mobile-app",
    )
    old_hash = hashlib.sha256(old_token.encode()).hexdigest()

    # The current create_refresh_token does not embed a unique jti — JWTs with
    # identical (user_id, client_id, iat-second) payloads collide byte-for-byte.
    # In production a real refresh hits seconds-to-minutes after issuance, so
    # collision is rare; the test sleeps just past the second boundary so iat
    # differs and the rotation is observable as both bytes and DB rows. The
    # JWT-jti gap is a separate hardening issue and out of scope here.
    await asyncio.sleep(1.1)

    request, response = _mock_request_response()
    payload = RefreshTokenRequest(refresh_token=old_token, client_id="mobile-app")
    auth_repo = get_auth_repository()

    result = await refresh_access_token(request, response, payload, auth_repo=auth_repo)
    new_token = result["data"]["tokens"]["refreshToken"]

    # Rotation: returned token differs from the one we sent in.
    assert new_token != old_token

    # Revocation: old hash row flipped to revoked; new hash row exists and live.
    new_hash = hashlib.sha256(new_token.encode()).hexdigest()
    async with db.session() as session:
        old_row = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == old_hash)
        )
        new_row = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == new_hash)
        )

    assert old_row is not None
    assert old_row.is_revoked is True, "previous refresh token must be revoked"
    assert new_row is not None
    assert new_row.is_revoked is False, "new refresh token row must be live"


@pytest.mark.asyncio
async def test_refresh_with_revoked_token_raises_and_revokes_all_user_tokens(
    db, user_factory
):
    user = await user_factory(telegram_user_id=987654322, username="replay-victim")

    revoked_token, _ = await create_refresh_token(
        user_id=user.telegram_user_id,
        client_id="mobile-app",
    )
    other_token, _ = await create_refresh_token(
        user_id=user.telegram_user_id,
        client_id="desktop-app",
    )

    # Pre-revoke one token to simulate a stale/stolen refresh that an attacker
    # later replays. The other token represents the user's still-live session
    # on a different device.
    revoked_hash = hashlib.sha256(revoked_token.encode()).hexdigest()
    async with db.transaction() as session:
        row = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == revoked_hash)
        )
        assert row is not None
        row.is_revoked = True
        await session.flush()

    request, response = _mock_request_response()
    payload = RefreshTokenRequest(refresh_token=revoked_token, client_id="mobile-app")
    auth_repo = get_auth_repository()

    with pytest.raises(TokenRevokedError):
        await refresh_access_token(request, response, payload, auth_repo=auth_repo)

    # Reuse detection: ALL of this user's refresh tokens must now be revoked.
    other_hash = hashlib.sha256(other_token.encode()).hexdigest()
    async with db.session() as session:
        other_row = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == other_hash)
        )
    assert other_row is not None
    assert other_row.is_revoked is True, (
        "reuse-detection must revoke all sibling refresh tokens, not just the replayed one"
    )
