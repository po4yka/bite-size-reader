from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from ratatoskr_cli.auth import ensure_authenticated, refresh_if_needed
from ratatoskr_cli.config import RatatoskrConfig
from ratatoskr_cli.exceptions import AuthError


class TestAuth:
    def test_no_refresh_when_token_fresh(self):
        """Don't refresh if token expires in more than 5 minutes."""
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        config = RatatoskrConfig(
            server_url="https://test.com",
            access_token="token",
            refresh_token="refresh",
            token_expires_at=future,
        )
        result = refresh_if_needed(config)
        assert result.access_token == "token"  # Unchanged

    def test_refresh_when_token_near_expiry(self):
        """Refresh if token expires within 5 minutes."""
        near_expiry = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
        config = RatatoskrConfig(
            server_url="https://test.com",
            access_token="old-token",
            refresh_token="refresh",
            token_expires_at=near_expiry,
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "success": True,
            "data": {"tokens": {"access_token": "new-token", "expires_in": 3600}},
        }

        with (
            patch("ratatoskr_cli.auth.httpx.post", return_value=mock_resp),
            patch("ratatoskr_cli.auth.save_config"),
        ):
            result = refresh_if_needed(config)
            assert result.access_token == "new-token"

    def test_ensure_authenticated_raises_without_token(self):
        """Raise AuthError if no access token."""
        config = RatatoskrConfig(server_url="https://test.com")
        with pytest.raises(AuthError):
            ensure_authenticated(config)

    def test_ensure_authenticated_with_valid_token(self):
        """Return config unchanged if token is valid."""
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        config = RatatoskrConfig(
            server_url="https://test.com",
            access_token="valid",
            refresh_token="refresh",
            token_expires_at=future,
        )
        result = ensure_authenticated(config)
        assert result.access_token == "valid"
