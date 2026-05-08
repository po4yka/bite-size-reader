"""Telegram link/unlink + invalid-nonce coverage for the auth endpoints."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from app.api.exceptions import ValidationError
from app.api.models.auth import TelegramLinkCompleteRequest
from app.api.routers.auth import endpoints as auth_endpoints, secret_auth
from app.db.models import User

if TYPE_CHECKING:
    from app.db.session import Database


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "1000000000:TESTTOKENPLACEHOLDER1234567890ABC")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("API_ID", "1")
    monkeypatch.setenv("API_HASH", "test_api_hash_placeholder_value___")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "dummy-firecrawl-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-openrouter-key")
    secret_auth._cfg = None  # type: ignore[attr-defined]


def _fake_auth_hash(bot_token: str, payload: dict) -> str:
    import hashlib
    import hmac

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    filtered = {
        k: v
        for k, v in payload.items()
        if k in {"id", "auth_date", "first_name", "last_name", "photo_url", "username"}
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(filtered.items()))
    return hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()


async def _create_owner(db: Database) -> User:
    async with db.transaction() as session:
        user = User(telegram_user_id=123456789, username="owner", is_owner=True)
        session.add(user)
        await session.flush()
        return user


async def test_link_happy_path(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch)
    user = await _create_owner(db)

    begin_resp = await auth_endpoints.begin_telegram_link(user={"user_id": user.telegram_user_id})
    nonce = begin_resp["data"]["nonce"]

    payload = {
        "auth_date": int(time.time()),
        "id": 123456789,
        "username": "linked_user",
        "client_id": "android-app",
    }
    auth_hash = _fake_auth_hash("1000000000:TESTTOKENPLACEHOLDER1234567890ABC", payload)

    complete_req = TelegramLinkCompleteRequest(
        id=payload["id"],  # type: ignore[arg-type]
        auth_date=payload["auth_date"],  # type: ignore[arg-type]
        hash=auth_hash,
        username=payload["username"],  # type: ignore[arg-type]
        client_id=payload["client_id"],  # type: ignore[arg-type]
        nonce=nonce,
    )
    complete_resp = await auth_endpoints.complete_telegram_link(
        complete_req, user={"user_id": user.telegram_user_id}
    )
    assert complete_resp["data"]["linked"] is True
    assert complete_resp["data"]["username"] == "linked_user"

    status_resp = await auth_endpoints.get_telegram_link_status(
        user={"user_id": user.telegram_user_id}
    )
    assert status_resp["data"]["linked"] is True

    unlink_resp = await auth_endpoints.unlink_telegram(user={"user_id": user.telegram_user_id})
    assert unlink_resp["data"]["linked"] is False


async def test_link_uses_constant_time_nonce_compare(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: nonce comparison must go through hmac.compare_digest."""
    _configure_env(monkeypatch)
    user = await _create_owner(db)

    begin_resp = await auth_endpoints.begin_telegram_link(user={"user_id": user.telegram_user_id})
    nonce = begin_resp["data"]["nonce"]

    from app.api.routers.auth import endpoints_telegram

    calls: list[tuple[str, str]] = []
    real_compare = endpoints_telegram.hmac.compare_digest

    def spy_compare(a, b):  # type: ignore[no-untyped-def]
        calls.append((a, b))
        return real_compare(a, b)

    monkeypatch.setattr(endpoints_telegram.hmac, "compare_digest", spy_compare)

    payload = {
        "auth_date": int(time.time()),
        "id": 123456789,
        "username": "linked_user",
        "client_id": "android-app",
    }
    auth_hash = _fake_auth_hash("1000000000:TESTTOKENPLACEHOLDER1234567890ABC", payload)
    complete_req = TelegramLinkCompleteRequest(
        id=payload["id"],  # type: ignore[arg-type]
        auth_date=payload["auth_date"],  # type: ignore[arg-type]
        hash=auth_hash,
        username=payload["username"],  # type: ignore[arg-type]
        client_id=payload["client_id"],  # type: ignore[arg-type]
        nonce=nonce,
    )
    await auth_endpoints.complete_telegram_link(
        complete_req, user={"user_id": user.telegram_user_id}
    )

    assert any(a == nonce and b == nonce for a, b in calls), (
        f"compare_digest not called with nonce; calls={calls!r}"
    )


async def test_link_invalid_nonce(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch)
    user = await _create_owner(db)

    await auth_endpoints.begin_telegram_link(user={"user_id": user.telegram_user_id})

    payload = {
        "auth_date": 9999999,
        "id": 123456789,
        "username": "linked_user",
        "client_id": "android-app",
    }
    auth_hash = _fake_auth_hash("1000000000:TESTTOKENPLACEHOLDER1234567890ABC", payload)

    complete_req = TelegramLinkCompleteRequest(
        id=payload["id"],  # type: ignore[arg-type]
        auth_date=payload["auth_date"],  # type: ignore[arg-type]
        hash=auth_hash,
        username=payload["username"],  # type: ignore[arg-type]
        client_id=payload["client_id"],  # type: ignore[arg-type]
        nonce="bad-nonce",
    )

    with pytest.raises(ValidationError):
        await auth_endpoints.complete_telegram_link(
            complete_req, user={"user_id": user.telegram_user_id}
        )
