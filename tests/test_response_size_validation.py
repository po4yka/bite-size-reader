"""Tests for HTTP response size validation."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

import httpx
import pytest

from app.core.http_utils import ResponseSizeError, bytes_to_mb, validate_response_size


class TestResponseSizeValidation(unittest.TestCase):
    """Test response size validation function."""

    def setUp(self):
        """Set up test fixtures."""
        self.max_size = 10 * 1024 * 1024  # 10 MB

    async def test_valid_response_under_limit(self):
        """Test that responses under the limit pass validation."""
        # Create mock response with Content-Length header
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": "1000000"}  # 1 MB

        # Should not raise
        await validate_response_size(response, self.max_size, "TestService")

    async def test_response_exceeds_limit_with_header(self):
        """Test that responses exceeding limit with Content-Length header raise error."""
        # Create mock response with large Content-Length
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(self.max_size + 1)}

        # Should raise ResponseSizeError
        with pytest.raises(ResponseSizeError) as exc_info:
            await validate_response_size(response, self.max_size, "TestService")

        error = exc_info.value
        assert error.actual_size == self.max_size + 1
        assert error.max_size == self.max_size
        assert "exceeds limit" in str(error)

    async def test_response_no_content_length_header(self):
        """Test response without Content-Length header."""
        # Create mock response without Content-Length
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {}
        response._content = b"test content"

        # Should not raise (small content)
        await validate_response_size(response, self.max_size, "TestService")

    async def test_response_no_content_length_exceeds_limit(self):
        """Test response without Content-Length but with large content."""
        # Create mock response with large content but no header
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {}
        response._content = b"x" * (self.max_size + 1)

        # Should raise ResponseSizeError
        with pytest.raises(ResponseSizeError) as exc_info:
            await validate_response_size(response, self.max_size, "TestService")

        error = exc_info.value
        assert error.actual_size == self.max_size + 1
        assert error.max_size == self.max_size

    async def test_invalid_content_length_header(self):
        """Test response with invalid Content-Length header."""
        # Create mock response with invalid Content-Length
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": "not-a-number"}
        response._content = b"test content"

        # Should not raise (validation skipped for invalid header)
        await validate_response_size(response, self.max_size, "TestService")

    async def test_invalid_max_size_negative(self):
        """Test that negative max_size raises ValueError."""
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": "1000"}

        with pytest.raises(ValueError) as exc_info:
            await validate_response_size(response, -1, "TestService")

        assert "positive integer" in str(exc_info.value)

    async def test_invalid_max_size_zero(self):
        """Test that zero max_size raises ValueError."""
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": "1000"}

        with pytest.raises(ValueError) as exc_info:
            await validate_response_size(response, 0, "TestService")

        assert "positive integer" in str(exc_info.value)

    async def test_invalid_max_size_too_large(self):
        """Test that excessively large max_size raises ValueError."""
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": "1000"}

        # More than 1GB
        with pytest.raises(ValueError) as exc_info:
            await validate_response_size(response, 2 * 1024 * 1024 * 1024, "TestService")

        assert "too large" in str(exc_info.value)

    async def test_response_at_exact_limit(self):
        """Test response exactly at the limit."""
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(self.max_size)}

        # Should not raise (exactly at limit)
        await validate_response_size(response, self.max_size, "TestService")

    async def test_response_one_byte_over_limit(self):
        """Test response one byte over the limit."""
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(self.max_size + 1)}

        # Should raise
        with pytest.raises(ResponseSizeError):
            await validate_response_size(response, self.max_size, "TestService")

    async def test_large_response_warning_threshold(self):
        """Test that large responses (>50% of limit) log warning."""
        # This test verifies behavior but doesn't check logging directly
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        # 60% of limit
        response.headers = {"content-length": str(int(self.max_size * 0.6))}

        # Should not raise but would log warning
        await validate_response_size(response, self.max_size, "TestService")


class TestBytesToMB(unittest.TestCase):
    """Test bytes to MB conversion utility."""

    def test_bytes_to_mb_conversion(self):
        """Test basic conversion."""
        assert bytes_to_mb(1024 * 1024) == 1.0
        assert bytes_to_mb(5 * 1024 * 1024) == 5.0
        assert bytes_to_mb(1536 * 1024) == 1.5

    def test_bytes_to_mb_rounding(self):
        """Test that conversion rounds to 2 decimal places."""
        assert bytes_to_mb(1234567) == 1.18
        assert bytes_to_mb(12345678) == 11.77

    def test_bytes_to_mb_zero(self):
        """Test zero bytes."""
        assert bytes_to_mb(0) == 0.0

    def test_bytes_to_mb_small_values(self):
        """Test small byte values."""
        assert bytes_to_mb(1024) == 0.0  # Less than 1 MB rounds to 0.0
        assert bytes_to_mb(10240) == 0.01


class TestResponseSizeErrorException(unittest.TestCase):
    """Test ResponseSizeError exception."""

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        error = ResponseSizeError(
            "Response too large",
            actual_size=20 * 1024 * 1024,
            max_size=10 * 1024 * 1024,
        )

        assert error.actual_size == 20 * 1024 * 1024
        assert error.max_size == 10 * 1024 * 1024
        assert "Response too large" in str(error)

    def test_error_without_actual_size(self):
        """Test error can be created without actual_size."""
        error = ResponseSizeError("Response too large", actual_size=None, max_size=10 * 1024 * 1024)

        assert error.actual_size is None
        assert error.max_size == 10 * 1024 * 1024

    def test_error_inheritance(self):
        """Test that ResponseSizeError inherits from ValueError."""
        error = ResponseSizeError("test", actual_size=100, max_size=50)
        assert isinstance(error, ValueError)


# Integration-style tests with more realistic scenarios
class TestResponseSizeValidationIntegration(unittest.TestCase):
    """Integration tests for response size validation."""

    async def test_firecrawl_response_validation(self):
        """Test validation with Firecrawl-like response size (50MB limit)."""
        max_size = 50 * 1024 * 1024  # 50 MB (Firecrawl default)

        # Simulate Firecrawl response with large markdown content
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(40 * 1024 * 1024)}  # 40 MB

        # Should not raise
        await validate_response_size(response, max_size, "Firecrawl")

    async def test_openrouter_response_validation(self):
        """Test validation with OpenRouter-like response size (10MB limit)."""
        max_size = 10 * 1024 * 1024  # 10 MB (OpenRouter default)

        # Simulate OpenRouter response (typically much smaller)
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(100 * 1024)}  # 100 KB

        # Should not raise
        await validate_response_size(response, max_size, "OpenRouter")

    async def test_malicious_response_blocked(self):
        """Test that maliciously large response is blocked."""
        max_size = 10 * 1024 * 1024  # 10 MB

        # Simulate malicious response claiming 1 GB
        response = Mock(spec=httpx.Response)
        response.status_code = 200
        response.headers = {"content-length": str(1024 * 1024 * 1024)}  # 1 GB

        # Should raise
        with pytest.raises(ResponseSizeError) as exc_info:
            await validate_response_size(response, max_size, "OpenRouter")

        error = exc_info.value
        assert error.actual_size == 1024 * 1024 * 1024
        assert "exceeds limit" in str(error)


if __name__ == "__main__":
    # Run async tests with pytest
    pytest.main([__file__, "-v"])
