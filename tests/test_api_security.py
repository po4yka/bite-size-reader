"""
Security tests for Mobile API.

Tests critical security fixes:
1. Telegram authentication verification
2. CORS configuration
3. Authorization checks
4. JWT secret validation
"""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        assert "Invalid authentication hash" in str(exc_info.value.message)

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
        assert "expired" in str(exc_info.value.message).lower()

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
        assert "not authorized" in str(exc_info.value.message).lower()


class TestCORSConfiguration:
    """Test CORS configuration values."""

    def test_cors_not_wildcard(self):
        """Test that CORS does not allow all origins by checking config values."""
        from app.config import Config

        # Get the raw CORS config - this doesn't require loading the full API
        allowed_origins = Config.get("ALLOWED_ORIGINS", "")
        origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]

        # If explicitly configured, should not contain wildcard
        if origins:
            assert "*" not in origins, "ALLOWED_ORIGINS should not contain wildcard '*'"

    def test_cors_allows_specific_origins_only(self):
        """Test that configured origins are specific, not wildcards."""
        from app.config import Config

        allowed_origins = Config.get("ALLOWED_ORIGINS", "")
        origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]

        # If explicitly configured, check that origins are specific
        for origin in origins:
            assert origin.startswith(("http://", "https://")), (
                f"Origin must start with http:// or https://: {origin}"
            )
            assert "*" not in origin, f"Origin should not contain wildcard: {origin}"


class TestAuthorizationChecks:
    """Test authorization checks on services."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        return {"user_id": 123456789, "username": "testuser"}

    @pytest.fixture
    def other_user(self):
        """Mock different user."""
        return {"user_id": 987654321, "username": "otheruser"}

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_summary(self, mock_user, other_user):
        """Test that users cannot access each other's summaries via service layer."""
        from app.api.exceptions import ResourceNotFoundError
        from app.api.services.summary_service import SummaryService

        # Mock the repository to return a summary owned by a different user
        with patch("app.api.services.summary_service.SqliteSummaryRepositoryAdapter") as MockRepo:
            mock_repo_instance = MagicMock()
            # Return summary owned by mock_user, not other_user
            mock_repo_instance.async_get_summary_by_id = AsyncMock(
                return_value={
                    "id": 42,
                    "user_id": mock_user["user_id"],  # Owned by mock_user
                    "is_deleted": False,
                    "json_payload": {"summary_250": "test"},
                }
            )
            MockRepo.return_value = mock_repo_instance

            # Try to access as other_user - should raise ResourceNotFoundError
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await SummaryService.get_summary_by_id(
                    user_id=other_user["user_id"],  # Different user
                    summary_id=42,
                )

            assert exc_info.value.status_code == 404
            assert "42" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_request(self, mock_user, other_user):
        """Test that users cannot access each other's requests via service layer."""
        from app.api.exceptions import ResourceNotFoundError
        from app.api.services.request_service import RequestService

        # Mock the repository to return a request owned by a different user
        with patch("app.api.services.request_service.SqliteRequestRepositoryAdapter") as MockRepo:
            mock_repo_instance = MagicMock()
            # Return request owned by mock_user, not other_user
            mock_repo_instance.async_get_request_by_id = AsyncMock(
                return_value={
                    "id": 100,
                    "user_id": mock_user["user_id"],  # Owned by mock_user
                    "status": "ok",
                }
            )
            MockRepo.return_value = mock_repo_instance

            # Try to access as other_user - should raise ResourceNotFoundError
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await RequestService.get_request_by_id(
                    user_id=other_user["user_id"],  # Different user
                    request_id=100,
                )

            assert exc_info.value.status_code == 404
            assert "100" in str(exc_info.value.message)


class TestJWTSecretValidation:
    """Test JWT secret validation."""

    def test_jwt_secret_required(self):
        """Test that JWT_SECRET_KEY must be configured."""
        # This test should be run in isolation or with proper mocking
        # as it affects module import

        with patch("app.api.routers.auth.tokens.Config.get") as mock_config:
            mock_config.return_value = ""  # Empty secret

            with pytest.raises(RuntimeError) as exc_info:
                # Re-import to trigger validation
                import importlib

                import app.api.routers.auth.tokens

                importlib.reload(app.api.routers.auth.tokens)

            assert "JWT_SECRET_KEY" in str(exc_info.value)

    def test_jwt_secret_minimum_length(self):
        """Test that JWT_SECRET_KEY must be at least 32 characters."""
        with patch("app.api.routers.auth.tokens.Config.get") as mock_config:
            mock_config.return_value = "short"  # Too short

            with pytest.raises(RuntimeError) as exc_info:
                import importlib

                import app.api.routers.auth.tokens

                importlib.reload(app.api.routers.auth.tokens)

            assert "at least 32 characters" in str(exc_info.value)


class TestSecurityHeaders:
    """Test security headers and configurations."""

    def test_cors_middleware_not_permissive(self):
        """Test that CORS middleware is configured properly via config check."""
        from app.config import Config

        # Verify that if ALLOWED_ORIGINS is set, it doesn't contain permissive values
        allowed_origins = Config.get("ALLOWED_ORIGINS", "")

        # If configured, should not be overly permissive
        if allowed_origins:
            assert allowed_origins != "*", "ALLOWED_ORIGINS should not be wildcard"
            # Split and check each origin
            origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
            for origin in origins:
                # Should not be a wildcard pattern
                assert not origin.endswith("*"), f"Origin should not use wildcard: {origin}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
