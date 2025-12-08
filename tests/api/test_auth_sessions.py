from datetime import datetime, timedelta

import pytest

from app.api.routers.auth import create_refresh_token
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


def test_create_refresh_token_persists(auth_user):
    token = create_refresh_token(
        user_id=auth_user.telegram_user_id,
        client_id="test-client",
        device_info="TestDevice",
        ip_address="127.0.0.1",
    )

    assert token is not None
    assert RefreshToken.select().count() == 1

    record = RefreshToken.select().first()
    assert record.user == auth_user
    assert record.client_id == "test-client"
    assert record.device_info == "TestDevice"
    assert record.ip_address == "127.0.0.1"
    assert not record.is_revoked


def test_logout_revokes_token(client, auth_user):
    # Create persistent token manually via helper
    token = create_refresh_token(auth_user.telegram_user_id, "mobile-app")

    # Login to get access token for headers
    # We can skip full login flow and just mock the dependency if valid token is complex to get
    # But let's try to use the auth token.
    from app.api.routers.auth import create_access_token

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


def test_list_sessions(client, auth_user):
    # Create 3 sessions
    # 1. Active
    create_refresh_token(auth_user.telegram_user_id, "client-1", device_info="Device 1")
    # 2. Revoked
    t2 = create_refresh_token(auth_user.telegram_user_id, "client-2", device_info="Device 2")
    r2 = RefreshToken.get(RefreshToken.client_id == "client-2")
    r2.is_revoked = True
    r2.save()
    # 3. Expired (manually manipulate)
    t3 = create_refresh_token(auth_user.telegram_user_id, "client-3", device_info="Device 3")
    r3 = RefreshToken.get(RefreshToken.client_id == "client-3")
    r3.expires_at = datetime.now(UTC) - timedelta(days=1)
    r3.save()

    # 4. Another user's session
    other = User.create(telegram_user_id=67890)
    create_refresh_token(other.telegram_user_id, "other-client")

    # Get sessions
    from app.api.routers.auth import create_access_token

    access_token = create_access_token(auth_user.telegram_user_id, client_id="client-1")

    response = client.get("/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    sessions = response.json()["data"]["sessions"]

    # Should only see session 1
    assert len(sessions) == 1
    assert sessions[0]["client_id"] == "client-1"
    assert sessions[0]["device_info"] == "Device 1"
