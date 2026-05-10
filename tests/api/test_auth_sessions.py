import hashlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import func, select as sa_select

from app.api.dependencies.database import get_auth_repository
from app.api.exceptions import TokenRevokedError
from app.api.models.auth import RefreshTokenRequest
from app.api.routers.auth.endpoints_sessions import refresh_access_token
from app.api.routers.auth.tokens import create_refresh_token
from app.core.time_utils import UTC
from app.db.models import RefreshToken as RefreshTokenModel


@pytest_asyncio.fixture
async def auth_user(db, user_factory):
    return await user_factory(telegram_user_id=123456789, username="test_auth")


@pytest.mark.asyncio
async def test_create_refresh_token_persists(db, auth_user):
    token, session_id = await create_refresh_token(
        user_id=auth_user.telegram_user_id,
        client_id="test-client",
        device_info="TestDevice",
        ip_address="127.0.0.1",
    )

    assert token is not None
    assert session_id is not None

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    async with db.session() as session:
        count = await session.scalar(sa_select(func.count()).select_from(RefreshTokenModel))
        record = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )

    assert count == 1
    assert record is not None
    assert record.user_id == auth_user.telegram_user_id
    assert record.client_id == "test-client"
    assert record.device_info == "TestDevice"
    assert record.ip_address == "127.0.0.1"
    assert not record.is_revoked


@pytest.mark.asyncio
async def test_logout_revokes_token(db, auth_user):
    from app.api.dependencies.database import get_auth_repository
    from app.api.models.auth import RefreshTokenRequest
    from app.api.routers.auth.endpoints_sessions import logout

    token, _ = await create_refresh_token(auth_user.telegram_user_id, "mobile-app")

    http_request = MagicMock()
    http_request.cookies = {}
    response = MagicMock()
    body = RefreshTokenRequest(refresh_token=token)
    current_user = {"user_id": auth_user.telegram_user_id}
    auth_repo = get_auth_repository()

    result = await logout(
        http_request=http_request,
        response=response,
        request=body,
        current_user=current_user,
        auth_repo=auth_repo,
    )

    assert "Logged out" in result["data"]["message"]

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    async with db.session() as session:
        record = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        )
    assert record is not None
    assert record.is_revoked is True


@pytest.mark.asyncio
async def test_list_sessions(db, auth_user, user_factory):
    from app.api.dependencies.database import get_auth_repository
    from app.api.routers.auth.endpoints_sessions import list_sessions

    # 1. Active session
    await create_refresh_token(auth_user.telegram_user_id, "client-1", device_info="Device 1")

    # 2. Revoked session
    _, _ = await create_refresh_token(
        auth_user.telegram_user_id, "client-2", device_info="Device 2"
    )
    async with db.transaction() as session:
        r2 = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.client_id == "client-2")
        )
        r2.is_revoked = True
        await session.flush()

    # 3. Expired session
    await create_refresh_token(auth_user.telegram_user_id, "client-3", device_info="Device 3")
    async with db.transaction() as session:
        r3 = await session.scalar(
            sa_select(RefreshTokenModel).where(RefreshTokenModel.client_id == "client-3")
        )
        r3.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.flush()

    # 4. Another user's session (should not appear in auth_user's list)
    other = await user_factory(telegram_user_id=67890)
    await create_refresh_token(other.telegram_user_id, "other-client")

    current_user = {"user_id": auth_user.telegram_user_id}
    auth_repo = get_auth_repository()

    result = await list_sessions(current_user=current_user, auth_repo=auth_repo)

    sessions = result["data"]["sessions"]
    # Should only see the single active, non-expired session (client-1)
    assert len(sessions) == 1
    assert sessions[0]["clientId"] == "client-1"
    assert sessions[0]["deviceInfo"] == "Device 1"


# ----- Refresh-token rotation regression tests -------------------------------
#
# All tests above and below use the modern db / user_factory fixtures from
# tests/api/conftest.py and call endpoint functions directly to avoid the
# TestClient / asyncpg event-loop conflict.
#
# Test contract: POST /v1/auth/refresh MUST issue a new refresh token AND
# revoke the previous one. Without this, an attacker who steals a single
# refresh token could keep refreshing indefinitely. A revoked token replayed
# against /refresh MUST trigger reuse detection and revoke ALL of that user's
# refresh tokens (defense in depth — assume the original was stolen).


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
    user = await user_factory(telegram_user_id=987654321, username="rotator")

    old_token, _ = await create_refresh_token(
        user_id=user.telegram_user_id,
        client_id="mobile-app",
    )
    old_hash = hashlib.sha256(old_token.encode()).hexdigest()

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
async def test_refresh_with_revoked_token_raises_and_revokes_all_user_tokens(db, user_factory):
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
