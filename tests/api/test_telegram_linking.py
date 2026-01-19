import pytest

from app.api.exceptions import ValidationError
from app.api.routers import auth
from app.db.database import Database
from app.db.models import User


def _configure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimal env vars for config and Telegram auth."""
    monkeypatch.setenv("BOT_TOKEN", "1000000000:TESTTOKENPLACEHOLDER1234567890ABC")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setenv("API_ID", "1")
    monkeypatch.setenv("API_HASH", "test_api_hash_placeholder_value___")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "dummy-firecrawl-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-openrouter-key")
    auth._cfg = None


def _init_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "linking.db"))
    db.migrate()
    return db


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


@pytest.mark.asyncio
async def test_link_happy_path(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)

    begin_resp = await auth.begin_telegram_link(user={"user_id": user.telegram_user_id})
    nonce = begin_resp["data"]["nonce"]

    payload = {
        "auth_date": int(auth.time.time()),
        "id": 123456789,
        "username": "linked_user",
        "client_id": "android-app",
    }
    auth_hash = _fake_auth_hash("1000000000:TESTTOKENPLACEHOLDER1234567890ABC", payload)

    complete_req = auth.TelegramLinkCompleteRequest(
        id=payload["id"],
        auth_date=payload["auth_date"],
        hash=auth_hash,
        username=payload["username"],
        client_id=payload["client_id"],
        nonce=nonce,
    )
    complete_resp = await auth.complete_telegram_link(
        complete_req, user={"user_id": user.telegram_user_id}
    )
    assert complete_resp["data"]["linked"] is True
    assert complete_resp["data"]["username"] == "linked_user"

    status_resp = await auth.get_telegram_link_status(user={"user_id": user.telegram_user_id})
    assert status_resp["data"]["linked"] is True

    unlink_resp = await auth.unlink_telegram(user={"user_id": user.telegram_user_id})
    assert unlink_resp["data"]["linked"] is False


@pytest.mark.asyncio
async def test_link_invalid_nonce(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _configure_env(monkeypatch)
    _init_db(tmp_path)

    user = User.create(telegram_user_id=123456789, username="owner", is_owner=True)
    await auth.begin_telegram_link(user={"user_id": user.telegram_user_id})

    payload = {
        "auth_date": 9999999,
        "id": 123456789,
        "username": "linked_user",
        "client_id": "android-app",
    }
    auth_hash = _fake_auth_hash("1000000000:TESTTOKENPLACEHOLDER1234567890ABC", payload)

    complete_req = auth.TelegramLinkCompleteRequest(
        id=payload["id"],
        auth_date=payload["auth_date"],
        hash=auth_hash,
        username=payload["username"],
        client_id=payload["client_id"],
        nonce="bad-nonce",
    )
    with pytest.raises(ValidationError):
        await auth.complete_telegram_link(complete_req, user={"user_id": user.telegram_user_id})
