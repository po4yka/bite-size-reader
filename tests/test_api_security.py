"""
Security tests for Mobile API.

Tests critical security fixes:
1. Telegram authentication verification
2. CORS configuration
3. Authorization checks
4. JWT secret validation
"""

import pytest
import hmac
import hashlib
import time
from unittest.mock import patch, MagicMock

# Note: These tests require the API to be importable
# Run with: pytest tests/test_api_security.py -v


class TestTelegramAuth:
    """Test Telegram authentication verification."""

    def test_telegram_auth_verifies_hash(self):
        """Test that Telegram auth hash is properly verified."""
        from app.api.routers.auth import verify_telegram_auth

        # This should raise HTTPException with invalid hash
        with pytest.raises(Exception) as exc_info:
            verify_telegram_auth(
                user_id=123456789,
                auth_hash="invalid_hash",
                auth_date=int(time.time()),
                username="testuser",
            )

        assert exc_info.value.status_code == 401
        assert "Invalid authentication hash" in str(exc_info.value.detail)

    def test_telegram_auth_checks_timestamp(self):
        """Test that expired timestamps are rejected."""
        from app.api.routers.auth import verify_telegram_auth

        # Timestamp from 1 hour ago (should fail)
        old_timestamp = int(time.time()) - 3600

        with pytest.raises(Exception) as exc_info:
            verify_telegram_auth(
                user_id=123456789,
                auth_hash="any_hash",
                auth_date=old_timestamp,
                username="testuser",
            )

        assert exc_info.value.status_code == 401
        assert "expired" in str(exc_info.value.detail).lower()

    def test_telegram_auth_requires_whitelist(self):
        """Test that users must be in whitelist."""
        from app.api.routers.auth import verify_telegram_auth
        from app.config import Config

        # Create valid hash for non-whitelisted user
        user_id = 999999999  # Not in whitelist
        auth_date = int(time.time())

        # Build data check string
        data_check_arr = [f"auth_date={auth_date}", f"id={user_id}", "username=hacker"]
        data_check_arr.sort()
        data_check_string = "\n".join(data_check_arr)

        # Compute valid hash
        bot_token = Config.get("BOT_TOKEN", "test_token")
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        valid_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # Even with valid hash, should fail if not in whitelist
        with pytest.raises(Exception) as exc_info:
            verify_telegram_auth(
                user_id=user_id,
                auth_hash=valid_hash,
                auth_date=auth_date,
                username="hacker",
            )

        assert exc_info.value.status_code == 403
        assert "not authorized" in str(exc_info.value.detail).lower()


class TestCORSConfiguration:
    """Test CORS configuration."""

    def test_cors_not_wildcard(self):
        """Test that CORS does not allow all origins."""
        from app.api.main import ALLOWED_ORIGINS

        # Should not contain wildcard
        assert "*" not in ALLOWED_ORIGINS
        assert len(ALLOWED_ORIGINS) > 0

    def test_cors_allows_specific_origins_only(self):
        """Test that only specific origins are allowed."""
        from app.api.main import ALLOWED_ORIGINS

        # Should only contain localhost or configured origins
        for origin in ALLOWED_ORIGINS:
            assert origin.startswith(
                ("http://localhost", "http://127.0.0.1", "https://")
            ), f"Suspicious origin: {origin}"


class TestAuthorizationChecks:
    """Test authorization checks on endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        return {"user_id": 123456789, "username": "testuser"}

    @pytest.fixture
    def other_user(self):
        """Mock different user."""
        return {"user_id": 987654321, "username": "otheruser"}

    def test_cannot_access_other_users_summary(self, mock_user, other_user):
        """Test that users cannot access each other's summaries."""
        from app.api.routers.summaries import get_summary
        from fastapi import HTTPException

        # Create summary for user 123456789
        with patch("app.api.routers.summaries.Summary") as MockSummary:
            with patch("app.api.routers.summaries.RequestModel") as MockRequest:
                # Mock query that returns no results (authorization failed)
                mock_query = MagicMock()
                mock_query.first.return_value = None
                MockSummary.select.return_value.join.return_value.where.return_value = mock_query

                # Try to access as different user
                with pytest.raises(HTTPException) as exc_info:
                    # This should fail because user_id doesn't match
                    import asyncio

                    asyncio.run(get_summary(summary_id=42, user=other_user))

                assert exc_info.value.status_code == 404
                assert "access denied" in str(exc_info.value.detail).lower()

    def test_cannot_access_other_users_request(self, mock_user, other_user):
        """Test that users cannot access each other's requests."""
        from app.api.routers.requests import get_request
        from fastapi import HTTPException

        with patch("app.api.routers.requests.RequestModel") as MockRequest:
            # Mock query that returns no results (authorization failed)
            mock_query = MagicMock()
            mock_query.first.return_value = None
            MockRequest.select.return_value.where.return_value = mock_query

            # Try to access as different user
            with pytest.raises(HTTPException) as exc_info:
                import asyncio

                asyncio.run(get_request(request_id=100, user=other_user))

            assert exc_info.value.status_code == 404
            assert "access denied" in str(exc_info.value.detail).lower()


class TestJWTSecretValidation:
    """Test JWT secret validation."""

    def test_jwt_secret_required(self):
        """Test that JWT_SECRET_KEY must be configured."""
        # This test should be run in isolation or with proper mocking
        # as it affects module import

        with patch("app.config.Config.get") as mock_config:
            mock_config.return_value = None

            with pytest.raises(RuntimeError) as exc_info:
                # Re-import to trigger validation
                import importlib
                import app.api.routers.auth

                importlib.reload(app.api.routers.auth)

            assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_jwt_secret_minimum_length(self):
        """Test that JWT_SECRET_KEY must be at least 32 characters."""
        with patch("app.config.Config.get") as mock_config:
            mock_config.return_value = "short"  # Too short

            with pytest.raises(RuntimeError) as exc_info:
                import importlib
                import app.api.routers.auth

                importlib.reload(app.api.routers.auth)

            assert "at least 32 characters" in str(exc_info.value)


class TestSecurityHeaders:
    """Test security headers and configurations."""

    def test_cors_headers_specific(self):
        """Test that CORS headers are specific, not wildcards."""
        from app.api.main import app

        # Check middleware configuration
        for middleware in app.user_middleware:
            if "CORSMiddleware" in str(middleware):
                # Middleware should not allow all origins
                assert middleware.kwargs.get("allow_origins") != ["*"]

                # Should have specific methods
                methods = middleware.kwargs.get("allow_methods", [])
                assert "*" not in methods

                # Should have specific headers
                headers = middleware.kwargs.get("allow_headers", [])
                assert "*" not in headers


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
