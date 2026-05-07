"""Auth endpoints: delete account + telegram login does-not-grant-owner."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.api.models.auth import TelegramLoginRequest
from app.api.routers.auth import (
    endpoints_me as auth_endpoints_me,
    endpoints_telegram as auth_endpoints_telegram,
    secret_auth,
)
from app.db.models import User

if TYPE_CHECKING:
    from app.db.session import Database


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", "com.example.app")
    secret_auth._cfg = None  # type: ignore[attr-defined]


async def test_delete_account(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch)

    async with db.transaction() as session:
        session.add(User(telegram_user_id=123456789, username="testuser", is_owner=False))

    user_context = {
        "user_id": 123456789,
        "username": "testuser",
        "client_id": "com.example.app",
    }

    response = await auth_endpoints_me.delete_account(
        user=user_context, x_confirm_delete="DELETE-MY-ACCOUNT"
    )

    assert response["data"]["success"] is True

    async with db.session() as session:
        remaining = await session.scalar(
            select(User).where(User.telegram_user_id == 123456789)
        )
    assert remaining is None


async def test_telegram_login_does_not_auto_grant_owner(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch)

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

    async with db.session() as session:
        user = await session.scalar(select(User).where(User.telegram_user_id == 123456789))
    assert user is not None
    assert user.is_owner is False
