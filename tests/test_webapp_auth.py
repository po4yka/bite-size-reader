"""Tests for Telegram WebApp initData HMAC validation."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

# Fixed reference timestamp — avoids clock-skew flakiness in CI.
_FIXED_NOW = 1700000000


def _build_init_data(
    bot_token: str,
    user_data: dict | None = None,
    auth_date: int | None = None,
    extra_fields: dict | None = None,
    tamper_hash: str | None = None,
) -> str:
    """Build a valid Telegram initData string for testing."""
    if user_data is None:
        user_data = {"id": 123456789, "first_name": "Test", "username": "testuser"}

    if auth_date is None:
        auth_date = _FIXED_NOW

    fields = {
        "user": json.dumps(user_data),
        "auth_date": str(auth_date),
    }
    if extra_fields:
        fields.update(extra_fields)

    # Build data-check-string
    data_check_pairs = sorted(f"{k}={v}" for k, v in fields.items())
    data_check_string = "\n".join(data_check_pairs)

    # Compute HMAC
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    fields["hash"] = tamper_hash if tamper_hash else computed_hash
    return urlencode(fields)


@pytest.fixture(autouse=True)
def _mock_config(monkeypatch):
    """Mock Config and freeze time.time() in the auth module to _FIXED_NOW."""
    monkeypatch.setenv("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123456789")
    monkeypatch.setattr(
        "app.api.routers.auth.webapp_auth.time.time",
        lambda: _FIXED_NOW,
    )


class TestVerifyInitData:
    """Tests for verify_telegram_webapp_init_data."""

    def test_valid_init_data(self):
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        init_data = _build_init_data(token)

        result = verify_telegram_webapp_init_data(init_data)
        assert result["user_id"] == 123456789
        assert result["username"] == "testuser"

    def test_empty_init_data(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        with pytest.raises(AuthenticationError, match="Empty initData"):
            verify_telegram_webapp_init_data("")

    def test_missing_hash(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        init_data = urlencode({"user": "{}", "auth_date": "123"})
        with pytest.raises(AuthenticationError, match="Missing hash"):
            verify_telegram_webapp_init_data(init_data)

    def test_invalid_signature(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        init_data = _build_init_data(token, tamper_hash="deadbeef" * 8)

        with pytest.raises(AuthenticationError, match="Invalid initData signature"):
            verify_telegram_webapp_init_data(init_data)

    def test_expired_init_data(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        old_date = _FIXED_NOW - 3600  # 1 hour before _FIXED_NOW
        init_data = _build_init_data(token, auth_date=old_date)

        with pytest.raises(AuthenticationError, match="expired"):
            verify_telegram_webapp_init_data(init_data)

    def test_future_auth_date(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        future = _FIXED_NOW + 600  # 10 min after _FIXED_NOW
        init_data = _build_init_data(token, auth_date=future)

        with pytest.raises(AuthenticationError, match="future"):
            verify_telegram_webapp_init_data(init_data)

    def test_unauthorized_user(self, monkeypatch):
        from app.api.exceptions import AuthorizationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        monkeypatch.setenv("ALLOWED_USER_IDS", "999999")  # Different user

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        init_data = _build_init_data(token)

        with pytest.raises(AuthorizationError, match="not authorized"):
            verify_telegram_webapp_init_data(init_data)

    def test_empty_allowlist_fails_closed(self, monkeypatch):
        from app.api.exceptions import AuthorizationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        monkeypatch.setenv("ALLOWED_USER_IDS", "")

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        init_data = _build_init_data(token)

        with pytest.raises(AuthorizationError, match="No authorized users configured"):
            verify_telegram_webapp_init_data(init_data)

    def test_missing_user_field(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        # Build without user field
        auth_date = str(_FIXED_NOW)
        fields = {"auth_date": auth_date}
        data_check_string = f"auth_date={auth_date}"
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        fields["hash"] = h

        init_data = urlencode(fields)
        with pytest.raises(AuthenticationError, match="Missing user"):
            verify_telegram_webapp_init_data(init_data)

    def test_malformed_user_json(self):
        from app.api.exceptions import AuthenticationError
        from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        # Build with invalid JSON user
        auth_date = str(_FIXED_NOW)
        fields = {"user": "not-json", "auth_date": auth_date}
        data_check_pairs = sorted(f"{k}={v}" for k, v in fields.items())
        data_check_string = "\n".join(data_check_pairs)
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        fields["hash"] = h

        init_data = urlencode(fields)
        with pytest.raises(AuthenticationError, match="Invalid user JSON"):
            verify_telegram_webapp_init_data(init_data)
