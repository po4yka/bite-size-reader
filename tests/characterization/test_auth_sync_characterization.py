from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Avoid importing optional heavy vector deps while loading API routers package.
sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("chromadb.config", MagicMock())
sys.modules.setdefault("chromadb.errors", MagicMock())

from app.api.models.auth import TelegramLoginRequest
from app.api.models.requests import SyncSessionRequest
from app.api.routers import sync as sync_router
from app.api.routers.auth import endpoints_telegram


@pytest.mark.asyncio
async def test_characterization_telegram_login_response_shape_is_stable() -> None:
    login = TelegramLoginRequest(
        id=12345,
        hash="deadbeef",
        auth_date=1700000000,
        username="characterization",
        first_name="Char",
        last_name="Test",
        photo_url=None,
        client_id="mobile-ios",
    )

    mock_user_repo = MagicMock()
    mock_user_repo.async_get_or_create_user = AsyncMock(
        return_value=({"telegram_user_id": 12345, "username": "characterization"}, True)
    )

    with (
        patch.object(endpoints_telegram, "validate_client_id", return_value=None),
        patch.object(endpoints_telegram, "verify_telegram_auth", return_value=None),
        patch.object(endpoints_telegram, "get_user_repository", return_value=mock_user_repo),
        patch.object(endpoints_telegram, "create_access_token", return_value="access-token"),
        patch.object(endpoints_telegram.logger, "info", return_value=None),
        patch.object(
            endpoints_telegram,
            "create_refresh_token",
            AsyncMock(return_value=("refresh-token", 1)),
        ),
    ):
        response = await endpoints_telegram.telegram_login(login, MagicMock())

    assert response["success"] is True
    assert response["data"]["tokens"]["accessToken"] == "access-token"
    assert response["data"]["tokens"]["refreshToken"] == "refresh-token"
    assert response["data"]["tokens"]["tokenType"] == "Bearer"
    assert response["data"]["sessionId"] == 1


@pytest.mark.asyncio
async def test_characterization_sync_session_response_shape_is_stable() -> None:
    from pydantic import BaseModel, Field

    class FakeSyncSession(BaseModel):
        session_id: str = Field(serialization_alias="sessionId")
        server_version: int = Field(serialization_alias="serverVersion")
        expires_at: str = Field(serialization_alias="expiresAt")
        default_limit: int = Field(serialization_alias="defaultLimit")

    fake_session = FakeSyncSession(
        session_id="sync-1",
        server_version=10,
        expires_at="2026-01-01T00:00:00Z",
        default_limit=100,
    )

    fake_service = type(
        "Svc",
        (),
        {
            "start_session": AsyncMock(return_value=fake_session),
        },
    )()

    response = await sync_router.create_sync_session(
        body=SyncSessionRequest(limit=50),
        user={"user_id": 7, "client_id": "mobile-ios"},
        svc=fake_service,
    )

    assert response["success"] is True
    assert response["data"]["sessionId"] == "sync-1"
    assert response["meta"]["pagination"]["limit"] == 100
    assert response["meta"]["pagination"]["hasMore"] is True
